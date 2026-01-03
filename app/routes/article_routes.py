import os
from flask import Blueprint, request, jsonify, current_app, url_for
from werkzeug.utils import secure_filename
from app.models.article import Article
from app.extensions import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import User
from app.utils.response import success, error # <--- Import ini
from sqlalchemy import or_

article_bp = Blueprint('article_api', __name__, url_prefix='/api')


# Fungsi bantuan cek ekstensi file
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 1. CREATE ARTICLE (Hanya Dokter) ---
@article_bp.route('/articles/create', methods=['POST'])
@jwt_required()
def create_article():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    # Cek apakah user adalah DOKTER
    if user.role != 'DOKTER':
        return error("Hanya dokter yang boleh menulis artikel", 403)

    # === MULAI DEBUGGING ===
    print("\n=== DEBUG UPLOAD ===")
    print("1. Files yang diterima:", request.files)
    
    if 'image' in request.files:
        file = request.files['image']
        print(f"2. Filename: {file.filename}")
        
        # Cek apakah lolos filter ekstensi
        is_allowed = allowed_file(file.filename)
        print(f"3. Apakah ekstensi allowed? {is_allowed}")
        
        if not is_allowed:
            print("   -> GAGAL DI FILTER EKSTENSI (Cek fungsi allowed_file)")
    else:
        print("2. KEY 'image' TIDAK DITEMUKAN DI REQUEST.FILES")
        
    print("====================\n")
    # === SELESAI DEBUGGING ===

    # Ambil data text (Form Data)
    title = request.form.get('title')
    content = request.form.get('content')
    tags = request.form.get('tags')

    if not title or not content:
        return error("Judul dan konten wajib diisi", 400)

    # Handle Upload Gambar
    image_url = None
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Tambahkan timestamp agar nama file unik
            import time
            filename = f"{int(time.time())}_{filename}"
            
            # Simpan ke folder
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Simpan URL relative untuk diakses frontend
            # url_for akan generate link: http://localhost:5000/static/uploads/namafile.jpg
            image_url = f"static/uploads/{filename}" 

    # Simpan ke DB
    new_article = Article(
        title=title,
        content=content,
        tags=tags,
        image_url=image_url,
        author_id=user.id
    )
    
    db.session.add(new_article)
    db.session.commit()

    result_data = {
        "id": new_article.id,
        "title": new_article.title,
        "image_url": image_url
    }
    
    return success(result_data, "Artikel berhasil dibuat", 201)

# --- 2. GET ALL ARTICLES ---
@article_bp.route('/articles', methods=['GET'])
def get_articles():
    # Ambil parameter 'q' dari URL (misal: ?q=anemia)
    search_query = request.args.get('q')
    
    query = Article.query
    
    # Jika ada pencarian, filter berdasarkan Judul atau Tags
    if search_query:
        search_pattern = f"%{search_query}%" # SQL LIKE syntax
        query = query.filter(
            or_(
                Article.title.ilike(search_pattern), # ilike = case insensitive (huruf besar/kecil sama aja)
                Article.tags.ilike(search_pattern)
            )
        )
    
    # Urutkan dari yang terbaru
    articles = query.order_by(Article.created_at.desc()).all()
    
    output = []
    for art in articles:
        full_image_url = request.host_url + art.image_url if art.image_url else None
        
        output.append({
            "id": art.id,
            "title": art.title,
            "content": art.content[:100] + "...",
            "image": full_image_url,
            "author": art.author.full_name,
            "tags": art.tags,
            "created_at": art.created_at
        })
    
    return success(output, "Berhasil mengambil daftar artikel")

# --- 3. GET MY ARTICLES (Dashboard Dokter) ---
@article_bp.route('/articles/me', methods=['GET'])
@jwt_required()
def get_my_articles():
    current_user_id = get_jwt_identity()
    
    # Cari artikel milik dokter yang sedang login
    my_articles = Article.query.filter_by(author_id=current_user_id)\
        .order_by(Article.created_at.desc()).all()
    
    output = []
    for art in my_articles:
        full_image_url = request.host_url + art.image_url if art.image_url else None
        output.append({
            "id": art.id,
            "title": art.title,
            "content": art.content[:100] + "...", # Preview pendek
            "image": full_image_url,
            "created_at": art.created_at
        })
    
    return success(output, "Berhasil mengambil artikel saya")

# --- 4. GET ARTICLE DETAIL (Baca 1 Artikel Full) ---
@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article_detail(article_id):
    article = Article.query.get(article_id)
    
    if not article:
        return error("Artikel tidak ditemukan", 404)
    
    full_image_url = request.host_url + article.image_url if article.image_url else None
    
    detail_data = {
        "id": article.id,
        "title": article.title,
        "content": article.content, # Konten full
        "image": full_image_url,
        "author": article.author.full_name,
        "tags": article.tags,
        "created_at": article.created_at
    }
    
    return success(detail_data, "Detail artikel ditemukan")

# --- 5. UPDATE ARTICLE (Edit & Ganti Gambar) ---
@article_bp.route('/articles/<int:article_id>', methods=['PUT'])
@jwt_required()
def update_article(article_id):
    current_user_id = get_jwt_identity()
    article = Article.query.get(article_id)

    if not article:
        return error("Artikel tidak ditemukan", 404)

    # Validasi Kepemilikan: Cuma penulis asli yang boleh edit
    if int(current_user_id) != article.author_id:
        return error("Anda tidak memiliki izin mengedit artikel ini", 403)

    # Update Data Teks (Jika dikirim)
    article.title = request.form.get('title', article.title)
    article.content = request.form.get('content', article.content)
    article.tags = request.form.get('tags', article.tags)

    # Handle Ganti Gambar
    if 'image' in request.files:
        file = request.files['image']
        # Pastikan fungsi allowed_file sudah didefinisikan di atas
        from app.routes.article_routes import allowed_file 
        
        if file and allowed_file(file.filename):
            # A. Hapus gambar lama biar server gak penuh sampah
            if article.image_url:
                # Path absolut: /home/user/project/app/static/uploads/lama.jpg
                old_file_path = os.path.join(current_app.config['BASE_DIR'], article.image_url)
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            # B. Simpan gambar baru
            filename = secure_filename(file.filename)
            import time
            filename = f"{int(time.time())}_{filename}"
            
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # C. Update database path
            article.image_url = f"static/uploads/{filename}"

    try:
        db.session.commit()
        
        # Kembalikan data terbaru
        updated_data = {
            "id": article.id,
            "title": article.title,
            "image_url": request.host_url + article.image_url if article.image_url else None
        }
        return success(updated_data, "Artikel berhasil diupdate")
        
    except Exception as e:
        db.session.rollback()
        return error(f"Gagal update artikel: {str(e)}", 500)

# --- 6. DELETE ARTICLE (Hapus) ---
@article_bp.route('/articles/<int:article_id>', methods=['DELETE'])
@jwt_required()
def delete_article(article_id):
    current_user_id = get_jwt_identity()
    article = Article.query.get(article_id)

    if not article:
        return error("Artikel tidak ditemukan", 404)

    # Validasi Kepemilikan
    if int(current_user_id) != article.author_id:
        return error("Anda tidak memiliki izin menghapus artikel ini", 403)

    try:
        # 1. Hapus File Fisik Gambar
        if article.image_url:
            full_path = os.path.join(current_app.config['BASE_DIR'], article.image_url)
            if os.path.exists(full_path):
                os.remove(full_path)

        # 2. Hapus Record Database
        db.session.delete(article)
        db.session.commit()

        return success(None, "Artikel berhasil dihapus")
        
    except Exception as e:
        db.session.rollback()
        return error(f"Gagal menghapus artikel: {str(e)}", 500)


# --- 7. ROUTE TEST BROWSER (Public / No JWT) ---
@article_bp.route('/', methods=['GET'])
def get_articles_public_root():
    # Query semua artikel, urutkan terbaru
    articles = Article.query.order_by(Article.created_at.desc()).all()
    
    output = []
    for art in articles:
        # Buat link gambar full
        full_image_url = request.host_url + art.image_url if art.image_url else None
        
        output.append({
            "id": art.id,
            "title": art.title,
            # Kita potong konten biar tidak kepanjangan di browser
            "content_preview": art.content[:200] + "...", 
            "image": full_image_url,
            "author": art.author.full_name if art.author else "Unknown",
            "photo": request.host_url + art.author.profile_image if art.author.profile_image else None,
            "tags": art.tags,
            "created_at": art.created_at
        })
    
    # Return JSON standar
    return success(output, "Berhasil mengambil data artikel (Mode Browser/Public)")