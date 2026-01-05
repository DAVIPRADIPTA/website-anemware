from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models.article import Article
from app.models.user import User
from app.extensions import db
from app.web.firebase_guard import firebase_web_required
import os, time

admin_article_bp = Blueprint("admin_article", __name__, url_prefix="/admin/articles")

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
# LIST SEMUA ARTIKEL (ADMIN)
# ===========================
@admin_article_bp.route("/")
@login_required
def list_articles():
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    # join biar bisa tampilkan nama dokter (author)
    articles = (
        Article.query
        .join(User, User.id == Article.author_id)
        .order_by(Article.created_at.desc())
        .all()
    )

    return render_template("web/admin/articles/list.html", articles=articles)

# ===========================
# EDIT ARTIKEL (ADMIN)
# ===========================
@admin_article_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_article(id):
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    article = Article.query.get_or_404(id)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()
        tags = (request.form.get("tags") or "").strip()

        if not title or not content:
            flash("Judul dan konten wajib diisi.", "danger")
            return redirect(url_for("admin_article.edit_article", id=id))

        article.title = title
        article.content = content
        article.tags = tags if tags else None

        file = request.files.get("image")
        if file and file.filename:
            if not _allowed_file(file.filename):
                flash("Format gambar harus jpg/jpeg/png.", "danger")
                return redirect(url_for("admin_article.edit_article", id=id))

            # hapus gambar lama
            if article.image_url:
                _delete_file_if_exists(article.image_url)

            filename = f"article_admin_{int(time.time())}_{secure_filename(file.filename)}"
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)

            save_path = os.path.join(upload_folder, filename)
            file.save(save_path)
            article.image_url = f"static/uploads/{filename}"

        db.session.commit()
        flash("Artikel berhasil diperbarui oleh admin.", "success")
        return redirect(url_for("admin_article.list_articles"))

    return render_template("web/admin/articles/edit.html", article=article)

# ===========================
# DELETE ARTIKEL (ADMIN)
# ===========================
@admin_article_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete_article(id):
    if current_user.role != "ADMIN":
        return "Unauthorized", 403

    article = Article.query.get_or_404(id)

    if article.image_url:
        _delete_file_if_exists(article.image_url)

    db.session.delete(article)
    db.session.commit()

    flash("Artikel berhasil dihapus oleh admin.", "success")
    return redirect(url_for("admin_article.list_articles"))
