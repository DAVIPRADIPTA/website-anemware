from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from app.models.article import Article
from app.extensions import db
from app.web.firebase_guard import firebase_web_required
import os, time

doctor_article_bp = Blueprint("doctor_article", __name__, url_prefix="/doctor/articles")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS

def _delete_file_if_exists(relative_path: str):
    if not relative_path:
        return
    base_dir = current_app.config.get("BASE_DIR", os.getcwd())
    abs_path = os.path.join(base_dir, relative_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)

# ===========================
# LIST ARTIKEL DOKTER
# ===========================
@doctor_article_bp.route("/")
@firebase_web_required(roles=["DOKTER"])
def list_articles():
    doctor = request.current_user

    articles = (
        Article.query
        .filter_by(author_id=doctor.id)
        .order_by(Article.created_at.desc())
        .all()
    )

    return render_template("web/doctor/articles/list.html", articles=articles, doctor=doctor)

@doctor_article_bp.route("/create", methods=["GET", "POST"])
@firebase_web_required(roles=["DOKTER"])
def create_article():
    doctor = request.current_user

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()
        tags = (request.form.get("tags") or "").strip()

        if not title or not content:
            flash("Judul dan konten wajib diisi.", "danger")
            return redirect(url_for("doctor_article.create_article"))

        image_url = None
        file = request.files.get("image")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ["jpg", "jpeg", "png"]:
                flash("Format gambar harus jpg/jpeg/png.", "danger")
                return redirect(url_for("doctor_article.create_article"))

            filename = f"article_doctor_{doctor.id}_{int(time.time())}_{secure_filename(file.filename)}"
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            image_url = f"static/uploads/{filename}"

        new_article = Article(
            title=title,
            content=content,
            tags=tags if tags else None,
            image_url=image_url,
            author_id=doctor.id
        )

        db.session.add(new_article)
        db.session.commit()

        flash("Artikel berhasil dibuat.", "success")
        return redirect(url_for("doctor_article.list_articles"))

    return render_template("web/doctor/articles/create.html", doctor=doctor)


@doctor_article_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@firebase_web_required(roles=["DOKTER"])
def edit_article(id):
    doctor = request.current_user
    article = Article.query.get_or_404(id)

    if article.author_id != doctor.id:
        return "Unauthorized", 403

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()
        tags = (request.form.get("tags") or "").strip()

        if not title or not content:
            flash("Judul dan konten wajib diisi.", "danger")
            return redirect(url_for("doctor_article.edit_article", id=id))

        article.title = title
        article.content = content
        article.tags = tags if tags else None

        file = request.files.get("image")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ["jpg", "jpeg", "png"]:
                flash("Format gambar harus jpg/jpeg/png.", "danger")
                return redirect(url_for("doctor_article.edit_article", id=id))

            if article.image_url:
                old_path = os.path.join(current_app.config.get("BASE_DIR", os.getcwd()), article.image_url)
                if os.path.exists(old_path):
                    os.remove(old_path)

            filename = f"article_doctor_{doctor.id}_{int(time.time())}_{secure_filename(file.filename)}"
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            article.image_url = f"static/uploads/{filename}"

        db.session.commit()
        flash("Artikel berhasil diperbarui.", "success")
        return redirect(url_for("doctor_article.list_articles"))

    return render_template("web/doctor/articles/edit.html", article=article, doctor=doctor)


@doctor_article_bp.route("/<int:id>/delete", methods=["POST"])
@firebase_web_required(roles=["DOKTER"])
def delete_article(id):
    doctor = request.current_user
    article = Article.query.get_or_404(id)

    if article.author_id != doctor.id:
        return "Unauthorized", 403

    if article.image_url:
        old_path = os.path.join(current_app.config.get("BASE_DIR", os.getcwd()), article.image_url)
        if os.path.exists(old_path):
            os.remove(old_path)

    db.session.delete(article)
    db.session.commit()

    flash("Artikel berhasil dihapus.", "success")
    return redirect(url_for("doctor_article.list_articles"))
