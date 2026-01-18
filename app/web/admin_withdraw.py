from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func
from app.extensions import db
from app.models.withdrawal import Withdrawal
from app.models.user import User

admin_withdraw_bp = Blueprint("admin_withdraw", __name__, url_prefix="/admin/withdrawals")

def _require_admin():
    return current_user.is_authenticated and getattr(current_user, "role", None) == "ADMIN"

@admin_withdraw_bp.route("/", methods=["GET"])
@login_required
def list_withdrawals():
    if not _require_admin():
        return "Unauthorized", 403

    status = request.args.get("status", "pending")
    q = Withdrawal.query

    if status in ["pending", "paid", "rejected"]:
        q = q.filter(Withdrawal.status == status)

    items = q.order_by(Withdrawal.created_at.desc()).all()
    return render_template("web/admin/withdrawals/list.html", withdrawals=items, status=status)

@admin_withdraw_bp.route("/<int:wid>/paid", methods=["POST"])
@login_required
def mark_paid(wid):
    if not _require_admin():
        return "Unauthorized", 403

    w = Withdrawal.query.get(wid)
    if not w:
        flash("Withdrawal tidak ditemukan.", "danger")
        return redirect(url_for("admin_withdraw.list_withdrawals"))

    if w.status != "pending":
        flash("Withdrawal sudah diproses.", "warning")
        return redirect(url_for("admin_withdraw.list_withdrawals"))

    doctor = User.query.get(w.doctor_id)
    if not doctor:
        flash("Dokter tidak ditemukan.", "danger")
        return redirect(url_for("admin_withdraw.list_withdrawals"))

    # Hitung available saldo dokter saat ini (saldo - pending lainnya)
    pending_other = db.session.query(func.coalesce(func.sum(Withdrawal.amount), 0))\
        .filter(Withdrawal.doctor_id == doctor.id,
                Withdrawal.status == "pending",
                Withdrawal.id != w.id)\
        .scalar()

    available = (doctor.balance or 0) - int(pending_other or 0)
    if w.amount > available:
        flash("Saldo dokter tidak cukup untuk memproses withdraw ini.", "danger")
        return redirect(url_for("admin_withdraw.list_withdrawals", status="pending"))

    # POTONG SALDO (sesuai pilihan 1B)
    doctor.balance = (doctor.balance or 0) - w.amount

    w.status = "paid"
    w.processed_at = datetime.utcnow()
    db.session.commit()

    flash("Withdraw ditandai PAID dan saldo dokter telah dipotong.", "success")
    return redirect(url_for("admin_withdraw.list_withdrawals", status="pending"))

@admin_withdraw_bp.route("/<int:wid>/reject", methods=["POST"])
@login_required
def reject(wid):
    if not _require_admin():
        return "Unauthorized", 403

    w = Withdrawal.query.get(wid)
    if not w:
        flash("Withdrawal tidak ditemukan.", "danger")
        return redirect(url_for("admin_withdraw.list_withdrawals"))

    if w.status != "pending":
        flash("Withdrawal sudah diproses.", "warning")
        return redirect(url_for("admin_withdraw.list_withdrawals"))

    note = request.form.get("note", "").strip()
    w.status = "rejected"
    w.note = note or None
    w.processed_at = datetime.utcnow()
    db.session.commit()

    flash("Withdraw ditolak.", "success")
    return redirect(url_for("admin_withdraw.list_withdrawals", status="pending"))
