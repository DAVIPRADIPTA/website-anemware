# app/web/doctor_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
import os, time

from app.models.article import Article
from app.models.consultation import Consultation

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
