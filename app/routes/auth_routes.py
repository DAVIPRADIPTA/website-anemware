import os
import time
import re  # <--- Import Regex untuk validasi email
from datetime import timedelta
from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

from app.models.user import User
from app.extensions import db
from app.utils.response import success, error

from firebase_admin import auth as fb_auth
from datetime import timedelta
from flask_jwt_extended import create_access_token

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# --- CONFIG VALIDASI ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'

# --- HELPER FUNCTIONS ---

def allowed_file(filename):
    """Cek ekstensi file gambar"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_register_input(data):
    """Validasi ketat untuk registrasi"""
    errors = []
    
    # 1. Validasi Email
    email = data.get('email', '').strip()
    if not email:
        errors.append("Email wajib diisi.")
    elif not re.match(EMAIL_REGEX, email):
        errors.append("Format email tidak valid.")
        
    # 2. Validasi Password
    password = data.get('password', '')
    if not password:
        errors.append("Password wajib diisi.")
    elif len(password) < 8:
        errors.append("Password minimal 6 karakter.")
        
    # 3. Validasi Nama Lengkap
    full_name = data.get('full_name', '').strip()
    if not full_name:
        errors.append("Nama lengkap wajib diisi.")
    elif len(full_name) < 3:
        errors.append("Nama lengkap terlalu pendek (min 3 huruf).")
    elif len(full_name) > 100:
        errors.append("Nama lengkap terlalu panjang (max 100 huruf).")

    # 4. Validasi Role
    role = data.get('role', 'PASIEN')
    if role not in ['PASIEN', 'DOKTER', 'ADMIN']:
        errors.append("Role tidak valid.")

    return errors

# --- ROUTES ---

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return error("Tidak ada data yang dikirim", 400)

    # 1. Lakukan Validasi Input
    validation_errors = validate_register_input(data)
    if validation_errors:
        # Mengembalikan error pertama yang ditemukan
        return error(validation_errors[0], 400)
    
    # 2. Sanitasi Input (Bersihkan spasi)
    email = data['email'].strip().lower()
    full_name = data['full_name'].strip()
    role = data.get('role', 'PASIEN')
    
    # 3. Cek Duplikasi Email di Database
    if User.query.filter_by(email=email).first():
        return error("Email sudah terdaftar, silakan login.", 400)
    
    # 4. Simpan ke Database
    try:
        new_user = User(
            email=email,
            full_name=full_name,
            role=role
        )
        new_user.set_password(data['password'])
        
        db.session.add(new_user)
        db.session.commit()
        
        user_data = {
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role
        }
        return success(user_data, "Registrasi berhasil", 201)
        
    except Exception as e:
        db.session.rollback()
        return error(f"Terjadi kesalahan server: {str(e)}", 500)


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return error("Data tidak valid", 400)

    # Validasi dasar kehadiran data
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return error("Email dan password wajib diisi", 400)
    
    # Cek User
    user = User.query.filter_by(email=email).first()
    
    if user and user.check_password(password):
        # # Cek Verifikasi Dokter
        if user.role == 'DOKTER' and not user.is_verified:
            return error("Akun Anda sedang dalam proses verifikasi Admin.", 403)
            
        # Tentukan Durasi Token
        is_mobile = data.get('is_mobile', False)
        expires = timedelta(days=30) if is_mobile else timedelta(days=1)
        expire_msg = "30 Days" if is_mobile else "1 Day"

        access_token = create_access_token(identity=str(user.id), expires_delta=expires)
        
        # Buat URL Foto Profil jika ada
        full_image_url = None
        if user.profile_image:
            full_image_url = request.host_url + user.profile_image

        login_data = {
            "token": access_token,
            "expires_in": expire_msg,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "profile_image": full_image_url
            }
        }
        return success(login_data, "Login berhasil")
    
    return error("Email atau password salah", 401)


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_my_profile():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return error("User tidak ditemukan", 404)
        
    full_image_url = request.host_url + user.profile_image if user.profile_image else None
    
    profile_data = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "joined_at": user.created_at,
        "profile_image": full_image_url,
        # Data Dokter (Akan null jika user biasa)
        "specialization": user.specialization,
        "consultation_price": user.consultation_price,
        "is_online": user.is_online,
        "bio": user.bio,
        "is_verified": user.is_verified,
        "balance": user.balance
    }
    
    return success(profile_data, "Berhasil mengambil data profil")


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return error("User tidak ditemukan", 404)

    # --- VALIDASI & SANITASI DATA ---
    
    # 1. Validasi Nama (Jika dikirim)
    full_name = request.form.get('full_name')
    if full_name is not None:
        full_name = full_name.strip()
        if len(full_name) < 3:
            return error("Nama lengkap minimal 3 karakter", 400)
        user.full_name = full_name
    
    # 2. Validasi Password (Jika dikirim)
    password = request.form.get('password')
    if password:
        if len(password) < 6:
            return error("Password baru minimal 6 karakter", 400)
        user.set_password(password)

    # 3. Validasi & Handle Upload Gambar
    if 'image' in request.files:
        file = request.files['image']
        if file.filename != '':
            if not allowed_file(file.filename):
                return error("Format file tidak diizinkan. Gunakan PNG, JPG, atau JPEG", 400)
            
            # Hapus foto lama
            if user.profile_image:
                old_path = os.path.join(current_app.config['BASE_DIR'], user.profile_image)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except:
                        pass # Abaikan jika gagal hapus file lama

            # Simpan foto baru
            filename = secure_filename(file.filename)
            unique_filename = f"profile_{user.id}_{int(time.time())}_{filename}"
            
            upload_folder = current_app.config['UPLOAD_FOLDER']
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            file_path = os.path.join(upload_folder, unique_filename)
            file.save(file_path)
            
            user.profile_image = f"static/uploads/{unique_filename}"

    # 4. Validasi Khusus DOKTER
    if user.role == 'DOKTER':
        # Validasi Harga (Harus Angka & Tidak Negatif)
        price_input = request.form.get('consultation_price')
        if price_input:
            try:
                price = int(price_input)
                if price < 0:
                    return error("Harga konsultasi tidak boleh negatif", 400)
                user.consultation_price = price
            except ValueError:
                return error("Harga konsultasi harus berupa angka", 400)
        
        # Update data string lainnya
        if request.form.get('specialization'):
            user.specialization = request.form.get('specialization').strip()
        
        if request.form.get('bio'):
            user.bio = request.form.get('bio').strip()
            
        is_online_input = request.form.get('is_online')
        if is_online_input:
            user.is_online = is_online_input.lower() == 'true'

    try:
        db.session.commit()
        
        full_image_url = request.host_url + user.profile_image if user.profile_image else None

        updated_data = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "profile_image": full_image_url,
            "specialization": user.specialization,
            "consultation_price": user.consultation_price,
            "bio": user.bio,
            "is_online": user.is_online
        }
        return success(updated_data, "Profil berhasil diperbarui")
        
    except Exception as e:
        db.session.rollback()
        return error(f"Gagal update profil: {str(e)}", 500)

@auth_bp.route('/verify-doc', methods=['PUT'])
@jwt_required()
def upload_verification_doc():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return error("User tidak ditemukan", 404)

    if user.role != "DOKTER":
        return error("Hanya dokter yang bisa mengunggah dokumen verifikasi", 403)

    if 'file' not in request.files:
        return error("Harap upload file STR/SIP", 400)

    file = request.files['file']
    
    # Validasi format file
    allowed_ext = {'png', 'jpg', 'jpeg', 'pdf'}
    if file.filename.split('.')[-1].lower() not in allowed_ext:
        return error("Format file tidak diizinkan (hanya png, jpg, jpeg, pdf)", 400)

    # Simpan file
    filename = f"verification_{user.id}_{int(time.time())}_{file.filename}"
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    user.verification_doc = f"static/uploads/{filename}"

    db.session.commit()

    return success({
        "verification_doc": request.host_url + user.verification_doc
    }, "Dokumen verifikasi berhasil diunggah")

@auth_bp.route("/firebase", methods=["POST"])
def firebase_login_mobile():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return error("Missing Firebase token", 401)

    id_token = h.split(" ", 1)[1]

    try:
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        uid = decoded["uid"]
        email = (decoded.get("email") or "").lower()
        name = decoded.get("name") or decoded.get("displayName")
        picture = decoded.get("picture")

        if not email:
            return error("Email tidak ditemukan dari Google", 400)

        # Cari user: uid dulu, lalu email
        user = User.query.filter_by(firebase_uid=uid).first()
        if not user:
            user = User.query.filter_by(email=email).first()

        # Mobile default PASIEN auto-create
        if not user:
            user = User(
                email=email,
                full_name=name,
                role="PASIEN",
                is_verified=True,
                firebase_uid=uid,
                auth_provider="firebase",
            )
            if picture and hasattr(User, "profile_image"):
                user.profile_image = picture
            db.session.add(user)
            db.session.commit()
        else:
            # sink uid/provider
            changed = False
            if not getattr(user, "firebase_uid", None):
                user.firebase_uid = uid
                changed = True
            if not getattr(user, "auth_provider", None):
                user.auth_provider = "firebase"
                changed = True
            if picture and hasattr(User, "profile_image") and not user.profile_image:
                user.profile_image = picture
                changed = True
            if changed:
                db.session.commit()

        # Cek verifikasi dokter kalau suatu saat dokter login dari mobile
        if user.role == "DOKTER" and not user.is_verified:
            return error("Akun dokter belum diverifikasi admin.", 403)

        expires = timedelta(days=30)
        access_token = create_access_token(identity=str(user.id), expires_delta=expires)

        # profile_image bisa url google (http) atau lokal
        full_image_url = None
        if user.profile_image:
            if user.profile_image.startswith("http"):
                full_image_url = user.profile_image
            else:
                full_image_url = request.host_url + user.profile_image

        return success({
            "token": access_token,
            "expires_in": "30 Days",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "profile_image": full_image_url
            }
        }, "Login Firebase berhasil")

    except Exception:
        return error("Firebase token invalid/expired", 401)