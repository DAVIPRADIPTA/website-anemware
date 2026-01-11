# app/routes/auth_routes.py  (versi clean)

import os
import re
import time
from datetime import timedelta

from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from firebase_admin import auth as fb_auth

from app.models.user import User
from app.extensions import db
from app.utils.response import success, error


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# =========================
# CONFIG
# =========================
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg"}
ALLOWED_VERIFY_EXT = {"png", "jpg", "jpeg", "pdf"}
EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"

# Kalau project kamu memang mobile hanya untuk PASIEN, biarkan True.
MOBILE_PATIENT_ONLY = True

MOBILE_TOKEN_EXPIRES = timedelta(days=30)
WEB_TOKEN_EXPIRES = timedelta(days=1)


# =========================
# HELPERS
# =========================
def _allowed_ext(filename: str, allowed: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _full_image_url(profile_image: str | None) -> str | None:
    """Support profile_image berupa URL (http/https) atau path lokal (static/uploads/...)."""
    if not profile_image:
        return None
    if profile_image.startswith("http://") or profile_image.startswith("https://"):
        return profile_image
    return request.host_url.rstrip("/") + "/" + profile_image.lstrip("/")


def _validate_register_input(data: dict) -> list[str]:
    errors: list[str] = []

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    role = (data.get("role") or "PASIEN").strip().upper()

    if not email:
        errors.append("Email wajib diisi.")
    elif not re.match(EMAIL_REGEX, email):
        errors.append("Format email tidak valid.")

    if not password:
        errors.append("Password wajib diisi.")
    elif len(password) < 8:
        errors.append("Password minimal 8 karakter.")

    if not full_name:
        errors.append("Nama lengkap wajib diisi.")
    elif len(full_name) < 3:
        errors.append("Nama lengkap terlalu pendek (min 3 huruf).")
    elif len(full_name) > 100:
        errors.append("Nama lengkap terlalu panjang (max 100 huruf).")

    if role not in {"PASIEN", "DOKTER", "ADMIN"}:
        errors.append("Role tidak valid.")

    return errors


def _issue_token(user: User, is_mobile: bool) -> tuple[str, str]:
    expires = MOBILE_TOKEN_EXPIRES if is_mobile else WEB_TOKEN_EXPIRES
    expire_msg = "30 Days" if is_mobile else "1 Day"
    token = create_access_token(identity=str(user.id), expires_delta=expires)
    return token, expire_msg


def _enforce_mobile_patient_only(user: User):
    if MOBILE_PATIENT_ONLY and user.role != "PASIEN":
        # kamu bisa ubah message sesuai UX kamu
        return error("Akun ini hanya bisa login lewat web. Mobile khusus pasien.", 403)
    return None


def _get_user_or_none(user_id_str: str):
    try:
        return User.query.get(int(user_id_str))
    except Exception:
        return None


# =========================
# ROUTES
# =========================

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    if not data:
        return error("Tidak ada data yang dikirim", 400)

    validation_errors = _validate_register_input(data)
    if validation_errors:
        return error(validation_errors[0], 400)

    email = data["email"].strip().lower()
    full_name = data["full_name"].strip()
    role = (data.get("role") or "PASIEN").strip().upper()

    if User.query.filter_by(email=email).first():
        return error("Email sudah terdaftar, silakan login.", 400)

    try:
        new_user = User(email=email, full_name=full_name, role=role)
        new_user.set_password(data["password"])

        db.session.add(new_user)
        db.session.commit()

        return success(
            {
                "email": new_user.email,
                "full_name": new_user.full_name,
                "role": new_user.role,
            },
            "Registrasi berhasil",
            201,
        )
    except Exception as e:
        db.session.rollback()
        return error(f"Terjadi kesalahan server: {str(e)}", 500)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    is_mobile = bool(data.get("is_mobile", True))  # default True untuk mobile

    if not email or not password:
        return error("Email dan password wajib diisi", 400)

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return error("Email atau password salah", 401)

    # Enforce mobile-only patient
    mobile_block = _enforce_mobile_patient_only(user) if is_mobile else None
    if mobile_block:
        return mobile_block

    # Cek verifikasi dokter (kalau suatu saat mobile dokter dibuka)
    if user.role == "DOKTER" and not getattr(user, "is_verified", True):
        return error("Akun Anda sedang dalam proses verifikasi Admin.", 403)

    token, expire_msg = _issue_token(user, is_mobile=is_mobile)

    return success(
        {
            "token": token,
            "expires_in": expire_msg,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "profile_image": _full_image_url(getattr(user, "profile_image", None)),
            },
        },
        "Login berhasil",
    )


@auth_bp.route("/firebase", methods=["POST"])
def firebase_login_mobile():
    """
    Mobile Google Login:
    - Mobile dapat Firebase ID token
    - Kirim via Authorization: Bearer <id_token>
    - Backend verify -> mapping user -> keluarkan JWT backend
    """
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return error("Missing Firebase token", 401)

    id_token = h.split(" ", 1)[1].strip()
    if not id_token:
        return error("Missing Firebase token", 401)

    try:
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        uid = decoded.get("uid")
        email = (decoded.get("email") or "").lower()
        name = decoded.get("name") or decoded.get("displayName") or ""
        picture = decoded.get("picture")

        if not uid:
            return error("Firebase token invalid", 401)
        if not email:
            return error("Email tidak ditemukan dari Google", 400)

        # Cari user: uid dulu, lalu email (untuk link account)
        user = User.query.filter_by(firebase_uid=uid).first()
        if not user:
            user = User.query.filter_by(email=email).first()

        # Mobile default: auto-create PASIEN
        if not user:
            user = User(
                email=email,
                full_name=name.strip() if name else email.split("@")[0],
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
            # link uid/provider/picture
            changed = False
            if not getattr(user, "firebase_uid", None):
                user.firebase_uid = uid
                changed = True
            if not getattr(user, "auth_provider", None):
                user.auth_provider = "firebase"
                changed = True
            if picture and hasattr(User, "profile_image") and not getattr(user, "profile_image", None):
                user.profile_image = picture
                changed = True
            if changed:
                db.session.commit()

        # Enforce mobile-only patient
        mobile_block = _enforce_mobile_patient_only(user)
        if mobile_block:
            return mobile_block

        # Token mobile selalu 30 hari
        token, expire_msg = _issue_token(user, is_mobile=True)

        return success(
            {
                "token": token,
                "expires_in": expire_msg,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "profile_image": _full_image_url(getattr(user, "profile_image", None)),
                },
            },
            "Login Google berhasil",
        )

    except Exception:
        return error("Firebase token invalid/expired", 401)


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_my_profile():
    user_id = get_jwt_identity()
    user = _get_user_or_none(user_id)

    if not user:
        return error("User tidak ditemukan", 404)

    return success(
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "joined_at": user.created_at,
            "profile_image": _full_image_url(getattr(user, "profile_image", None)),
            "specialization": getattr(user, "specialization", None),
            "consultation_price": getattr(user, "consultation_price", None),
            "is_online": getattr(user, "is_online", None),
            "bio": getattr(user, "bio", None),
            "is_verified": getattr(user, "is_verified", None),
            "balance": getattr(user, "balance", None),
        },
        "Berhasil mengambil data profil",
    )


@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = _get_user_or_none(user_id)

    if not user:
        return error("User tidak ditemukan", 404)

    # Update nama
    full_name = request.form.get("full_name")
    if full_name is not None:
        full_name = full_name.strip()
        if len(full_name) < 3:
            return error("Nama lengkap minimal 3 karakter", 400)
        user.full_name = full_name

    # Update password
    password = request.form.get("password")
    if password:
        if len(password) < 8:
            return error("Password baru minimal 8 karakter", 400)
        user.set_password(password)

    # Upload foto profile
    file = request.files.get("image")
    if file and file.filename:
        if not _allowed_ext(file.filename, ALLOWED_IMAGE_EXT):
            return error("Format file tidak diizinkan. Gunakan PNG, JPG, atau JPEG", 400)

        # hapus foto lama (hanya kalau itu path lokal)
        old_img = getattr(user, "profile_image", None)
        if old_img and not (old_img.startswith("http://") or old_img.startswith("https://")):
            old_path = os.path.join(current_app.config.get("BASE_DIR", os.getcwd()), old_img)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass

        filename = secure_filename(file.filename)
        unique_filename = f"profile_{user.id}_{int(time.time())}_{filename}"

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)

        user.profile_image = f"static/uploads/{unique_filename}"

    # Kalau mobile khusus pasien, biasanya bagian dokter ini tidak dipakai.
    # Tapi tetap aman bila suatu saat diperlukan.
    if user.role == "DOKTER":
        price_input = request.form.get("consultation_price")
        if price_input:
            try:
                price = int(price_input)
                if price < 0:
                    return error("Harga konsultasi tidak boleh negatif", 400)
                user.consultation_price = price
            except ValueError:
                return error("Harga konsultasi harus berupa angka", 400)

        if request.form.get("specialization"):
            user.specialization = request.form.get("specialization").strip()
        if request.form.get("bio"):
            user.bio = request.form.get("bio").strip()

        is_online_input = request.form.get("is_online")
        if is_online_input is not None:
            user.is_online = str(is_online_input).lower() == "true"

    try:
        db.session.commit()
        return success(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "profile_image": _full_image_url(getattr(user, "profile_image", None)),
                "specialization": getattr(user, "specialization", None),
                "consultation_price": getattr(user, "consultation_price", None),
                "bio": getattr(user, "bio", None),
                "is_online": getattr(user, "is_online", None),
            },
            "Profil berhasil diperbarui",
        )
    except Exception as e:
        db.session.rollback()
        return error(f"Gagal update profil: {str(e)}", 500)


# =========================
# NOTE: Route dokter ini sebaiknya dipindah ke blueprint khusus dokter/admin,
# karena mobile kamu hanya pasien. Kalau kamu mau tetap ada, minimal role-check ketat.
# =========================
@auth_bp.route("/verify-doc", methods=["PUT"])
@jwt_required()
def upload_verification_doc():
    user_id = get_jwt_identity()
    user = _get_user_or_none(user_id)

    if not user:
        return error("User tidak ditemukan", 404)

    if user.role != "DOKTER":
        return error("Hanya dokter yang bisa mengunggah dokumen verifikasi", 403)

    file = request.files.get("file")
    if not file or not file.filename:
        return error("Harap upload file STR/SIP", 400)

    if not _allowed_ext(file.filename, ALLOWED_VERIFY_EXT):
        return error("Format file tidak diizinkan (hanya png, jpg, jpeg, pdf)", 400)

    filename = f"verification_{user.id}_{int(time.time())}_{secure_filename(file.filename)}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    save_path = os.path.join(upload_folder, filename)
    file.save(save_path)

    user.verification_doc = f"static/uploads/{filename}"
    db.session.commit()

    return success(
        {"verification_doc": request.host_url.rstrip("/") + "/" + user.verification_doc},
        "Dokumen verifikasi berhasil diunggah",
    )
