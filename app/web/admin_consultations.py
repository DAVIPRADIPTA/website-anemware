# app/web/admin_consultations.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import aliased
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta

from app.extensions import db
from app.models.consultation import Consultation, ChatMessage, Payment
from app.models.user import User

admin_consult_bp = Blueprint("admin_consult", __name__, url_prefix="/admin/consultations")


def _admin_only():
    return getattr(current_user, "role", None) == "ADMIN"


def _parse_date_yyyy_mm_dd(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


# ===========================
# LIST CONSULTATIONS (ADMIN)
# ===========================
@admin_consult_bp.route("/", methods=["GET"])
@login_required
def list_consultations():
    if not _admin_only():
        return "Unauthorized", 403

    q = (request.args.get("q") or "").strip()
    c_status = (request.args.get("status") or "").strip()          # pending/active/completed
    p_status = (request.args.get("pay_status") or "").strip()      # pending/success/failed
    expired = (request.args.get("expired") or "").strip()          # yes/no/"" (all)
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()

    Patient = aliased(User)
    Doctor = aliased(User)

    # Subquery: ambil payment terbaru per consultation (kalau ada)
    latest_payment_subq = (
        db.session.query(
            Payment.consultation_id.label("c_id"),
            func.max(Payment.created_at).label("max_created_at"),
        )
        .group_by(Payment.consultation_id)
        .subquery()
    )

    LatestPay = aliased(Payment)

    # Query utama: consultation + patient + doctor + latest payment (outer join)
    query = (
        db.session.query(Consultation, Patient, Doctor, LatestPay)
        .join(Patient, Patient.id == Consultation.patient_id)
        .join(Doctor, Doctor.id == Consultation.doctor_id)
        .outerjoin(latest_payment_subq, latest_payment_subq.c.c_id == Consultation.id)
        .outerjoin(
            LatestPay,
            and_(
                LatestPay.consultation_id == Consultation.id,
                LatestPay.created_at == latest_payment_subq.c.max_created_at,
            ),
        )
    )

    # Filters
    if c_status in ["pending", "active", "completed"]:
        query = query.filter(Consultation.status == c_status)

    if p_status in ["pending", "success", "failed"]:
        # hanya yang punya payment latest dan status cocok
        query = query.filter(LatestPay.status == p_status)

    now = datetime.utcnow()
    if expired == "yes":
        query = query.filter(Consultation.expired_at.isnot(None), Consultation.expired_at < now)
    elif expired == "no":
        # dianggap belum expired jika expired_at kosong atau masih di masa depan
        query = query.filter(or_(Consultation.expired_at.is_(None), Consultation.expired_at >= now))

    # Date range (created_at)
    dt_from = _parse_date_yyyy_mm_dd(date_from)
    dt_to = _parse_date_yyyy_mm_dd(date_to)
    if dt_from:
        query = query.filter(Consultation.created_at >= dt_from)
    if dt_to:
        query = query.filter(Consultation.created_at < (dt_to + timedelta(days=1)))

    # Search
    if q:
        conds = [
            Patient.full_name.ilike(f"%{q}%"),
            Patient.email.ilike(f"%{q}%"),
            Doctor.full_name.ilike(f"%{q}%"),
            Doctor.email.ilike(f"%{q}%"),
            LatestPay.transaction_id.ilike(f"%{q}%"),
        ]
        if q.isdigit():
            conds += [
                Consultation.id == int(q),
                Consultation.patient_id == int(q),
                Consultation.doctor_id == int(q),
            ]
        query = query.filter(or_(*conds))

    rows = query.order_by(Consultation.created_at.desc()).all()

    return render_template(
        "web/admin/consultations/list.html",
        rows=rows,
        q=q, c_status=c_status, p_status=p_status, expired=expired,
        date_from=date_from, date_to=date_to,
        now=now
    )


# ===========================
# DETAIL CONSULTATION (ADMIN)
# ===========================
@admin_consult_bp.route("/<int:consultation_id>", methods=["GET"])
@login_required
def consultation_detail(consultation_id):
    if not _admin_only():
        return "Unauthorized", 403

    consult = Consultation.query.get_or_404(consultation_id)

    patient = consult.patient
    doctor = consult.doctor

    # latest payment (kalau ada)
    latest_payment = (
        Payment.query
        .filter(Payment.consultation_id == consult.id)
        .order_by(Payment.created_at.desc())
        .first()
    )

    # chat transcript
    Sender = aliased(User)
    messages = (
        db.session.query(ChatMessage, Sender)
        .join(Sender, Sender.id == ChatMessage.sender_id)
        .filter(ChatMessage.consultation_id == consult.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    now = datetime.utcnow()

    return render_template(
        "web/admin/consultations/detail.html",
        consult=consult,
        patient=patient,
        doctor=doctor,
        latest_payment=latest_payment,
        messages=messages,
        now=now
    )

