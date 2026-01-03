from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models.article import Article
from app.extensions import db
import os, time
from app.web.firebase_guard import firebase_web_required


doctor_article_bp = Blueprint("doctor_article", __name__, url_prefix="/doctor/articles")

# ===========================
# LIST ARTIKEL DOKTER
# ===========================
@doctor_article_bp.route("/")
@firebase_web_required(roles=["DOKTER"])
def list_articles():
    current_user = request.current_user

    if current_user.role != "DOKTER":
        return "Unauthorized", 403

    articles = Article.query.filter_by(author_id=current_user.id).all()

    return render_template("web/doctor/articles/list.html", articles=articles)


# ===========================
# CREATE ARTIKEL
# ===========================
@doctor_article_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_article():
    if current_user.role != "DOKTER":
        return "Unauthorized", 403

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        tags = request.form.get("tags")
        file = request.files.get("image")

        if not title or not content:
            flash("Judul dan konten wajib diisi.", "danger")
            return redirect(url_for("doctor_article.create_article"))

        image_url = None
        if file and file.filename != "":
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ["jpg", "jpeg", "png"]:
                flash("Format gambar tidak valid.", "danger")
                return redirect(url_for("doctor_article.create_article"))

            filename = f"article_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"
            save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            image_url = f"static/uploads/{filename}"

        new_article = Article(
            title=title,
            content=content,
            tags=tags,
            image_url=image_url,
            author_id=current_user.id
        )

        db.session.add(new_article)
        db.session.commit()

        flash("Artikel berhasil dibuat.", "success")
        return redirect(url_for("doctor_article.list_articles"))

    return render_template("web/doctor/articles/create.html")


# ===========================
# EDIT ARTIKEL
# ===========================
@doctor_article_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_article(id):
    if current_user.role != "`DOKTER":
        return "Unauthorized", 403

    article = Article.query.get_or_404(id)

    if article.author_id != current_user.id:
        return "Unauthorized", 403

    if request.method == "POST":
        article.title = request.form.get("title")
        article.content = request.form.get("content")
        article.tags = request.form.get("tags")

        file = request.files.get("image")
        if file and file.filename != "":
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ["jpg", "jpeg", "png"]:
                flash("Format gambar tidak valid.", "danger")
                return redirect(url_for("doctor_article.edit_article", id=id))

            # Hapus file lama
            if article.image_url:
                old_path = os.path.join(current_app.config["BASE_DIR"], article.image_url)
                if os.path.exists(old_path):
                    os.remove(old_path)

            filename = f"article_{current_user.id}_{int(time.time())}_{secure_filename(file.filename)}"
            save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            article.image_url = f"static/uploads/{filename}"

        db.session.commit()
        flash("Artikel berhasil diperbarui.", "success")
        return redirect(url_for("doctor_article.list_articles"))

    return render_template("web/doctor/articles/edit.html", article=article)


# ===========================
# DELETE ARTIKEL
# ===========================
@doctor_article_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete_article(id):
    if current_user.role != "DOKTER":
        return "Unauthorized", 403

    article = Article.query.get_or_404(id)

    if article.author_id != current_user.id:
        return "Unauthorized", 403

    # Hapus file fisik
    if article.image_url:
        old_path = os.path.join(current_app.config["BASE_DIR"], article.image_url)
        if os.path.exists(old_path):
            os.remove(old_path)

    db.session.delete(article)
    db.session.commit()

    flash("Artikel berhasil dihapus.", "success")
    return redirect(url_for("doctor_article.list_articles"))
