# app/web/doctor_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
import os, time
from app.models.article import Article
from app.models.consultation import Consultation

from app.web.firebase_guard import firebase_web_required

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


@doctor_bp.route("/dashboard")
@firebase_web_required(roles=["DOKTER"])
def dashboard():
    current_user = request.current_user
    if current_user.role != "DOKTER":
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
@firebase_web_required(roles=["DOKTER"])
def verification():
    current_user = request.current_user
    if current_user.role != "DOKTER":
        return "Unauthorized", 403

    if request.method == "POST":
        file = request.files.get("file")

        if not file or file.filename == "":
            flash("Harap pilih file STR/SIP terlebih dahulu.", "danger")
            return redirect(url_for("doctor.verification"))

        # Validasi ekstensi
        allowed_ext = {"png", "jpg", "jpeg", "pdf"}
        ext = file.filename.rsplit(".", 1)[-1].lower()

        if ext not in allowed_ext:
            flash("Format file tidak diizinkan (hanya PNG, JPG, JPEG, PDF).", "danger")
            return redirect(url_for("doctor.verification"))

        # Simpan file
        filename = f"verification_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"

        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)

        save_path = os.path.join(upload_folder, filename)
        file.save(save_path)

        # Hapus file lama jika ada
        if current_user.verification_doc:
            try:
                old_path = os.path.join(current_app.config['BASE_DIR'], current_user.verification_doc)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except:
                pass

        # Simpan path relatif di DB
        current_user.verification_doc = f"static/uploads/{filename}"
        db.session.commit()

        flash("Dokumen verifikasi berhasil di-upload. Menunggu persetujuan admin.", "success")
        return redirect(url_for("doctor.dashboard"))

    # GET → tampilkan form
    return render_template("web/doctor/verification.html", doctor=current_user)
