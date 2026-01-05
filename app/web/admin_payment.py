# app/web/admin_payment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models.consultation import Consultation, Payment
from app.models.user import User
import requests

admin_payment_bp = Blueprint("admin_payment", __name__, url_prefix="/admin/payments")

def _admin_only():
    if current_user.role != "ADMIN":
        return False
    return True

def _midtrans_base_url() -> str:
    is_prod = bool(current_app.config.get("MIDTRANS_IS_PRODUCTION", False))
    return "https://api.midtrans.com" if is_prod else "https://api.sandbox.midtrans.com"

def _midtrans_server_key() -> str:
    key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not key:
        raise RuntimeError("MIDTRANS_SERVER_KEY belum diset di config.")
    return key

def _midtrans_get_status(order_id: str) -> dict:
    """
    Panggil Midtrans Status API:
    GET /v2/{order_id}/status
    """
    url = f"{_midtrans_base_url()}/v2/{order_id}/status"
    resp = requests.get(url, auth=(_midtrans_server_key(), ""), timeout=15)
    # 200 biasanya sukses, 404 kalau tidak ketemu order_id
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    return {"http_status": resp.status_code, "data": data}

def _map_midtrans_to_local_status(midtrans_status: str) -> str:
    """
    Map transaction_status dari Midtrans → Payment.status lokal:
    - pending → pending
    - settlement/capture → success
    - deny/cancel/expire → failed
    - lainnya: pending (aman)
    """
    s = (midtrans_status or "").lower()
    if s in ["settlement", "capture"]:
        return "success"
    if s in ["deny", "cancel", "expire"]:
        return "failed"
    if s in ["pending"]:
        return "pending"
    return "pending"

# ===========================
# LIST PAYMENTS (ADMIN)
# ===========================
@admin_payment_bp.route("/", methods=["GET"])
@login_required
def list_payments():
    if not _admin_only():
        return "Unauthorized", 403

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()   # pending/success/failed
    method = (request.args.get("method") or "").strip()   # gopay/bca/etc
    date_from = (request.args.get("from") or "").strip()  # YYYY-MM-DD
    date_to = (request.args.get("to") or "").strip()      # YYYY-MM-DD

    # query dasar: join ke Consultation, patient, doctor
    query = (
        Payment.query
        .join(Consultation, Consultation.id == Payment.consultation_id)
        .join(User, User.id == Consultation.patient_id)
        .join(User, User.id == Consultation.doctor_id)  # ini join dobel kalau pakai alias; kita handle dengan alias di bawah
    )

    # Karena join User 2 kali, lebih aman pakai alias
    from sqlalchemy.orm import aliased
    Patient = aliased(User)
    Doctor = aliased(User)

    query = (
        Payment.query
        .join(Consultation, Consultation.id == Payment.consultation_id)
        .join(Patient, Patient.id == Consultation.patient_id)
        .join(Doctor, Doctor.id == Consultation.doctor_id)
    )

    if status in ["pending", "success", "failed"]:
        query = query.filter(Payment.status == status)

    if method:
        query = query.filter(Payment.payment_method.ilike(f"%{method}%"))

    if q:
        # search transaction_id / consultation_id / patient/doctor name/email
        # consultation_id numeric: coba parse
        conds = [
            Payment.transaction_id.ilike(f"%{q}%"),
            Patient.full_name.ilike(f"%{q}%"),
            Patient.email.ilike(f"%{q}%"),
            Doctor.full_name.ilike(f"%{q}%"),
            Doctor.email.ilike(f"%{q}%"),
        ]
        if q.isdigit():
            conds.append(Payment.consultation_id == int(q))
            conds.append(Payment.id == int(q))

        from sqlalchemy import or_
        query = query.filter(or_(*conds))

    # filter tanggal (created_at payment)
    # (simple) gunakan string compare via cast date di DB kalau perlu;
    # di sini pakai BETWEEN datetime via SQLAlchemy text (lebih aman kalau DB postgres/mysql)
    from datetime import datetime, timedelta
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Payment.created_at >= dt_from)
        except:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Payment.created_at < dt_to)
        except:
            pass

    payments = query.order_by(Payment.created_at.desc()).all()

    return render_template(
        "web/admin/payments/list.html",
        payments=payments,
        q=q, status=status, method=method, date_from=date_from, date_to=date_to
    )

# ===========================
# DETAIL PAYMENT (ADMIN)
# ===========================
@admin_payment_bp.route("/<int:payment_id>", methods=["GET"])
@login_required
def payment_detail(payment_id):
    if not _admin_only():
        return "Unauthorized", 403

    payment = Payment.query.get_or_404(payment_id)
    consultation = Consultation.query.get(payment.consultation_id)

    # eager data patient/doctor
    patient = consultation.patient if consultation else None
    doctor = consultation.doctor if consultation else None

    return render_template(
        "web/admin/payments/detail.html",
        payment=payment,
        consultation=consultation,
        patient=patient,
        doctor=doctor,
    )

# ===========================
# SYNC/REFRESH STATUS (ADMIN)
# ===========================
@admin_payment_bp.route("/<int:payment_id>/refresh", methods=["POST"])
@login_required
def refresh_payment(payment_id):
    if not _admin_only():
        return "Unauthorized", 403

    payment = Payment.query.get_or_404(payment_id)

    if not payment.transaction_id:
        flash("Transaction ID belum ada, tidak bisa cek ke Midtrans.", "warning")
        return redirect(url_for("admin_payment.payment_detail", payment_id=payment_id))

    try:
        res = _midtrans_get_status(payment.transaction_id)
        http_status = res["http_status"]
        data = res["data"]

        if http_status != 200:
            # contoh response error midtrans biasanya ada status_code & status_message
            msg = data.get("status_message") if isinstance(data, dict) else str(data)
            flash(f"Gagal cek status Midtrans (HTTP {http_status}): {msg}", "danger")
            return redirect(url_for("admin_payment.payment_detail", payment_id=payment_id))

        midtrans_status = data.get("transaction_status")
        mapped = _map_midtrans_to_local_status(midtrans_status)

        # update status lokal (bukan manual, ini dari gateway)
        payment.status = mapped

        # optional: update payment_method dari midtrans bila ada
        if not payment.payment_method:
            pm = data.get("payment_type")
            if pm:
                payment.payment_method = pm

        db.session.commit()

        flash(f"Status berhasil disinkron: Midtrans='{midtrans_status}' → Lokal='{mapped}'", "success")
        return redirect(url_for("admin_payment.payment_detail", payment_id=payment_id))

    except Exception as e:
        flash(f"Error saat cek status Midtrans: {str(e)}", "danger")
        return redirect(url_for("admin_payment.payment_detail", payment_id=payment_id))
