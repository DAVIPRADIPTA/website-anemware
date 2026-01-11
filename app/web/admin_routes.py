# app/web/admin_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.user import User
from app.models.article import Article
from app.models.consultation import Consultation
from app.models.consultation import Payment  
from flask import jsonify, current_app
from app.models.feedback import Feedback
from sqlalchemy import func
import numpy as np

   # kalau tabel Payment ada
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

@admin_bp.route("/sentiment-data", methods=["GET"])
@login_required
def sentiment_data():
    if current_user.role != "ADMIN":
        return jsonify({"error": "Unauthorized"}), 403

    model = current_app.extensions.get("sentiment_model")
    if not model:
        return jsonify({"error": "sentiment model not loaded"}), 500

    rows = (
        Feedback.query
        .with_entities(Feedback.comment)
        .filter(Feedback.comment.isnot(None))
        .all()
    )

    counts = {"positif": 0, "netral": 0, "negatif": 0}
    conf_sum = {"positif": 0.0, "netral": 0.0, "negatif": 0.0}

    for (comment,) in rows:
        label, conf = predict_sentiment_id(comment, model)
        counts[label] += 1
        conf_sum[label] += conf

    total = sum(counts.values())
    avg_conf = {
        k: (conf_sum[k] / counts[k]) if counts[k] else 0.0
        for k in counts
    }

    return jsonify({
        "counts": counts,
        "total": total,
        "avg_confidence": avg_conf
    }), 200
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
        "web/admin/doctor/list.html",
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
        "web/admin/doctor/edit.html",
        doctor=doctor
    )

def predict_sentiment_id(text: str, model):
    """
    Mengembalikan:
    - label_id: 'positif' / 'netral' / 'negatif'
    - confidence: float (0-100)
    """
    text = (text or "").strip()
    if not text:
        return "netral", 0.0

    # label dari model (temanmu)
    label = model.predict([text])[0]

    # confidence
    confidence = 0.0
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba([text])[0]
        confidence = float(np.max(proba) * 100)

    # pastikan string konsisten
    label = str(label).strip().lower()
    if label not in ("positif", "netral", "negatif"):
        label = "netral"

    return label, confidence