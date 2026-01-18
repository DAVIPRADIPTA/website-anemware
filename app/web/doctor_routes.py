# app/web/doctor_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db

import os, time

from sqlalchemy import func
from datetime import datetime

from app.models.withdrawal import Withdrawal  # sesuaikan path file model
from app.models.article import Article
from app.models.consultation import Consultation
from app.models.medical import MedicalRecord
from app.models.user import User



doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


def _require_doctor() -> bool:
    """Pastikan user yang login adalah DOKTER."""
    return current_user.is_authenticated and getattr(current_user, "role", None) == "DOKTER"


@doctor_bp.route("/dashboard")
@login_required
def dashboard():
    if not _require_doctor():
        return "Unauthorized", 403

    # Hitung artikel dokter
    total_articles = Article.query.filter_by(author_id=current_user.id).count()

    # Hitung konsultasi yang pernah dilakukan
    total_consultations = Consultation.query.filter_by(doctor_id=current_user.id).count()

    return render_template(
        "web/doctor/dashboard.html",
        doctor=current_user,
        total_articles=total_articles,
        total_consultations=total_consultations
    )


@doctor_bp.route("/verification", methods=["GET", "POST"])
@login_required
def verification():
    if not _require_doctor():
        return "Unauthorized", 403

    if request.method == "POST":
        # KUNCI: key harus sama dengan name di HTML: verification_doc
        file = request.files.get("verification_doc")

        if not file or file.filename == "":
            flash("Harap pilih file STR/SIP terlebih dahulu.", "danger")
            return redirect(url_for("doctor.verification"))

        allowed_ext = {"png", "jpg", "jpeg", "pdf"}
        ext = file.filename.rsplit(".", 1)[-1].lower()

        if ext not in allowed_ext:
            flash("Format file tidak diizinkan (hanya PNG, JPG, JPEG, PDF).", "danger")
            return redirect(url_for("doctor.verification"))

        filename = f"verification_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        save_path = os.path.join(upload_folder, filename)
        file.save(save_path)

        # Hapus file lama jika ada
        if getattr(current_user, "verification_doc", None):
            try:
                old_path = os.path.join(
                    current_app.config.get("BASE_DIR", os.getcwd()),
                    current_user.verification_doc
                )
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass

        current_user.verification_doc = f"static/uploads/{filename}"
        db.session.commit()

        flash("Dokumen verifikasi berhasil di-upload. Menunggu persetujuan admin.", "success")
        return redirect(url_for("doctor.dashboard"))

    return render_template("web/doctor/verification.html", doctor=current_user)

@doctor_bp.route("/toggle-online", methods=["POST"])
@login_required
def toggle_online():
    if not _require_doctor():
        return "Unauthorized", 403

    # Checkbox: kalau dicentang, browser akan kirim field "is_online"
    new_state = bool(request.form.get("is_online"))

    current_user.is_online = new_state
    db.session.commit()

    flash(f"Status berhasil diubah: {'Online' if new_state else 'Offline'}", "success")

    # balik ke halaman sebelumnya kalau ada
    next_url = request.form.get("next") or url_for("doctor.dashboard")
    return redirect(next_url)

@doctor_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if not _require_doctor():
        return "Unauthorized", 403

    if request.method == "POST":
        # Ambil data form
        full_name = request.form.get("full_name", "").strip()
        specialization = request.form.get("specialization", "").strip()
        consultation_price = request.form.get("consultation_price", "0").strip()
        bio = request.form.get("bio", "").strip()

        # Validasi minimal
        if not full_name:
            flash("Nama lengkap wajib diisi.", "danger")
            return redirect(url_for("doctor.profile"))

        # Parse int aman
        try:
            consultation_price_int = int(consultation_price or 0)
            if consultation_price_int < 0:
                consultation_price_int = 0
        except ValueError:
            consultation_price_int = 0

        # Update field user
        current_user.full_name = full_name
        current_user.specialization = specialization or None
        current_user.consultation_price = consultation_price_int
        current_user.bio = bio or None

        # Upload foto (opsional)
        file = request.files.get("profile_image")
        if file and file.filename:
            allowed_ext = {"png", "jpg", "jpeg"}
            ext = file.filename.rsplit(".", 1)[-1].lower()

            if ext not in allowed_ext:
                flash("Foto profil harus PNG/JPG/JPEG.", "danger")
                return redirect(url_for("doctor.profile"))

            filename = f"profile_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"

            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)

            save_path = os.path.join(upload_folder, filename)
            file.save(save_path)

            # hapus foto lama kalau ada
            if getattr(current_user, "profile_image", None):
                try:
                    old_path = os.path.join(
                        current_app.config.get("BASE_DIR", os.getcwd()),
                        current_user.profile_image
                    )
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass

            current_user.profile_image = f"static/uploads/{filename}"

        db.session.commit()
        flash("Profil berhasil diperbarui.", "success")
        return redirect(url_for("doctor.profile"))

    return render_template("web/doctor/profile.html", doctor=current_user)

@doctor_bp.route("/patients/<int:patient_id>/screenings")
@login_required
def patient_screenings(patient_id):
    if not _require_doctor():
        return "Unauthorized", 403

    # SECURITY: dokter hanya boleh lihat pasien yang pernah konsultasi dengannya
    allowed = Consultation.query.filter_by(
        doctor_id=current_user.id,
        patient_id=patient_id
    ).first()

    if not allowed:
        flash("Anda tidak memiliki akses ke riwayat skrining pasien ini.", "danger")
        return redirect(url_for("doctor_consult.list_consultations"))

    patient = User.query.get(patient_id)

    records = MedicalRecord.query.filter_by(user_id=patient_id)\
        .order_by(MedicalRecord.created_at.desc())\
        .all()

    return render_template(
        "web/doctor/screenings/list.html",
        doctor=current_user,
        patient=patient,
        records=records
    )

@doctor_bp.route("/withdrawals", methods=["GET", "POST"])
@login_required
def withdrawals():
    if not _require_doctor():
        return "Unauthorized", 403

    if not current_user.is_verified:
        flash("Withdraw aktif setelah akun diverifikasi.", "warning")
        return redirect(url_for("doctor.dashboard"))

    # Hitung total pending withdraw
    pending_total = db.session.query(func.coalesce(func.sum(Withdrawal.amount), 0))\
        .filter(Withdrawal.doctor_id == current_user.id, Withdrawal.status == "pending")\
        .scalar()

    available = (current_user.balance or 0) - int(pending_total or 0)
    if available < 0:
        available = 0

    if request.method == "POST":
        amount = request.form.get("amount", "0").strip()
        bank_name = request.form.get("bank_name", "").strip()
        account_number = request.form.get("account_number", "").strip()

        try:
            amount_int = int(amount)
        except ValueError:
            amount_int = 0

        if amount_int <= 0:
            flash("Nominal withdraw tidak valid.", "danger")
            return redirect(url_for("doctor.withdrawals"))

        if not bank_name or not account_number:
            flash("Nama bank dan nomor rekening wajib diisi.", "danger")
            return redirect(url_for("doctor.withdrawals"))

        # Karena saldo dipotong saat admin paid (1B),
        # kita batasi request maksimal = available (saldo - pending)
        if amount_int > available:
            flash(f"Nominal melebihi saldo tersedia. Tersedia: Rp {available:,}".replace(",", "."), "danger")
            return redirect(url_for("doctor.withdrawals"))

        w = Withdrawal(
            doctor_id=current_user.id,
            amount=amount_int,
            bank_name=bank_name,
            account_number=account_number,
            status="pending"
        )
        db.session.add(w)
        db.session.commit()

        flash("Request withdraw berhasil dibuat. Menunggu admin.", "success")
        return redirect(url_for("doctor.withdrawals"))

    # List riwayat withdraw dokter
    items = Withdrawal.query.filter_by(doctor_id=current_user.id)\
        .order_by(Withdrawal.created_at.desc())\
        .all()

    return render_template(
        "web/doctor/withdrawals/list.html",
        doctor=current_user,
        withdrawals=items,
        pending_total=int(pending_total or 0),
        available=available
    )
