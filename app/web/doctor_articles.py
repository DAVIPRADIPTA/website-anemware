from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models.article import Article
from app.extensions import db
import os, time

doctor_article_bp = Blueprint("doctor_article", __name__, url_prefix="/doctor/articles")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def _require_doctor() -> bool:
    """Pastikan user yang login adalah DOKTER."""
    return current_user.is_authenticated and getattr(current_user, "role", None) == "DOKTER"


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
@login_required
def list_articles():
    if not _require_doctor():
        return "Unauthorized", 403

    articles = (
        Article.query
        .filter_by(author_id=current_user.id)
        .order_by(Article.created_at.desc())
        .all()
    )

    return render_template(
        "web/doctor/articles/list.html",
        articles=articles,
        doctor=current_user
    )


# ===========================
# CREATE ARTIKEL
# ===========================
@doctor_article_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_article():
    if not _require_doctor():
        return "Unauthorized", 403

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
            if not _allowed_file(file.filename):
                flash("Format gambar harus jpg/jpeg/png.", "danger")
                return redirect(url_for("doctor_article.create_article"))

            filename = f"article_doctor_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            image_url = f"static/uploads/{filename}"

        new_article = Article(
            title=title,
            content=content,
            tags=tags if tags else None,
            image_url=image_url,
            author_id=current_user.id
        )

        db.session.add(new_article)
        db.session.commit()

        flash("Artikel berhasil dibuat.", "success")
        return redirect(url_for("doctor_article.list_articles"))

    return render_template("web/doctor/articles/create.html", doctor=current_user)


# ===========================
# EDIT ARTIKEL
# ===========================
@doctor_article_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_article(id):
    if not _require_doctor():
        return "Unauthorized", 403

    article = Article.query.get_or_404(id)

    if article.author_id != current_user.id:
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
            if not _allowed_file(file.filename):
                flash("Format gambar harus jpg/jpeg/png.", "danger")
                return redirect(url_for("doctor_article.edit_article", id=id))

            # hapus gambar lama
            if article.image_url:
                _delete_file_if_exists(article.image_url)

            filename = f"article_doctor_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            article.image_url = f"static/uploads/{filename}"

        db.session.commit()
        flash("Artikel berhasil diperbarui.", "success")
        return redirect(url_for("doctor_article.list_articles"))

    return render_template(
        "web/doctor/articles/edit.html",
        article=article,
        doctor=current_user
    )


# ===========================
# DELETE ARTIKEL
# ===========================
@doctor_article_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete_article(id):
    if not _require_doctor():
        return "Unauthorized", 403

    article = Article.query.get_or_404(id)

    if article.author_id != current_user.id:
        return "Unauthorized", 403

    if article.image_url:
        _delete_file_if_exists(article.image_url)

    db.session.delete(article)
    db.session.commit()

    flash("Artikel berhasil dihapus.", "success")
    return redirect(url_for("doctor_article.list_articles"))
