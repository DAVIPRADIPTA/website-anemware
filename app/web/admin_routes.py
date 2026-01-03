# app/web/admin_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.user import User
from app.models.article import Article
from app.models.consultation import Consultation
from app.models.consultation import Payment     # kalau tabel Payment ada
                                                  # sesuaikan importnya kalau beda
from app.extensions import db   # ← HARUS ADA INI

from flask import request
from app.web.firebase_guard import firebase_web_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/dashboard")
@login_required
def dashboard():
    # Hanya admin boleh membuka halaman ini
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    total_users = User.query.count()
    total_doctors = User.query.filter_by(role="DOKTER").count()
    unverified_doctors = User.query.filter_by(role="DOKTER", is_verified=False).count()
    total_patients = User.query.filter_by(role="PASIEN").count()

    total_articles = Article.query.count()
    total_consultations = Consultation.query.count()

    # Jika ada tabel payments:
    try:
        total_payments_success = Payment.query.filter_by(status="success").count()
    except:
        total_payments_success = None  # kalau belum siap

    return render_template(
        "web/admin/dashboard.html",
        total_users=total_users,
        total_doctors=total_doctors,
        unverified_doctors=unverified_doctors,
        total_patients=total_patients,
        total_articles=total_articles,
        total_consultations=total_consultations,
        total_payments_success=total_payments_success,
    )

# ======================
# LIST DOKTER
# ======================
@admin_bp.route("/doctors")
@login_required
def doctors():
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    # Ambil semua dokter
    doctors = User.query.filter_by(role="DOKTER").all()

    return render_template(
        "web/admin/doctors.html",
        doctors=doctors
    )

# ======================
# VERIFIKASI DOKTER
# ======================
@admin_bp.route("/doctors/<int:doctor_id>/verify", methods=["POST"])
@login_required
def verify_doctor(doctor_id):
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    doctor = User.query.get_or_404(doctor_id)

    doctor.is_verified = True
    db.session.commit()

    flash(f"Dokter {doctor.full_name} berhasil diverifikasi!", "success")

    return redirect(url_for("admin.doctors"))

@admin_bp.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
@login_required
def edit_doctor(doctor_id):
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    doctor = User.query.get_or_404(doctor_id)

    if request.method == "POST":
        # Ambil data form
        doctor.full_name = request.form.get("full_name", doctor.full_name)
        doctor.email = request.form.get("email", doctor.email)
        doctor.specialization = request.form.get("specialization", doctor.specialization)
        doctor.consultation_price = request.form.get("consultation_price", doctor.consultation_price)
        doctor.bio = request.form.get("bio", doctor.bio)

        # Optional: ubah status verifikasi
        doctor.is_verified = True if request.form.get("is_verified") == "on" else False

        db.session.commit()
        flash("Data dokter berhasil diperbarui.", "success")
        return redirect(url_for("admin.doctors"))

    return render_template(
        "web/admin/edit_doctor.html",
        doctor=doctor
    )
