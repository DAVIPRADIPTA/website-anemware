# app/web/firebase_session.py  (atau file tempat web_session_bp ini berada)
from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user
from firebase_admin import auth as fb_auth

from app.models.user import User
from app.extensions import db

web_session_bp = Blueprint("web_session", __name__)

@web_session_bp.post("/sessionLogin")
def session_login():
    """
    Web Google Login:
    - Frontend web login via Firebase Client SDK -> dapat idToken
    - Kirim idToken ke endpoint ini
    - Backend verify idToken
    - Mapping user di DB
    - login_user(user) -> masuk ke session Flask-Login
    """
    body = request.get_json(silent=True) or {}
    id_token = body.get("idToken")
    role_hint = body.get("role")  # 'ADMIN' / 'DOKTER' dari tombol (opsional)

    if not id_token:
        return jsonify({"error": "Missing idToken"}), 400

    try:
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        uid = decoded["uid"]
        email = (decoded.get("email") or "").lower()
        name = decoded.get("name") or decoded.get("displayName") or ""
        picture = decoded.get("picture")

        if not email:
            return jsonify({"error": "Email tidak ditemukan dari Google"}), 400

        # 1) Cari user (prioritas firebase_uid -> email)
        user = User.query.filter_by(firebase_uid=uid).first()
        if not user:
            user = User.query.filter_by(email=email).first()

        # 2) RULE WEB:
        # - ADMIN tidak auto-create
        # - DOKTER boleh auto-create tapi is_verified=False
        if not user:
            if role_hint == "ADMIN":
                return jsonify({"error": "Akun admin belum terdaftar. Hubungi super admin."}), 403

            if role_hint == "DOKTER":
                user = User(
                    email=email,
                    full_name=name.strip() if name else email.split("@")[0],
                    role="DOKTER",
                    is_verified=False,
                    firebase_uid=uid,
                    auth_provider="firebase",
                )
                if picture and hasattr(User, "profile_image"):
                    user.profile_image = picture
                db.session.add(user)
                db.session.commit()
            else:
                return jsonify({"error": "Role tidak diizinkan."}), 403
        else:
            # 3) Sink uid/provider bila belum ada
            changed = False
            if getattr(user, "firebase_uid", None) != uid:
                # kalau sebelumnya kosong atau beda, set ke uid sekarang
                user.firebase_uid = uid
                changed = True

            if not getattr(user, "auth_provider", None):
                user.auth_provider = "firebase"
                changed = True

            # Hanya isi foto kalau user belum punya
            if picture and hasattr(User, "profile_image") and not user.profile_image:
                user.profile_image = picture
                changed = True

            if changed:
                db.session.commit()

        # 4) Role wajib dari DB (bukan role_hint)
        if user.role not in ["ADMIN", "DOKTER"]:
            return jsonify({"error": "Akses hanya untuk Admin & Dokter"}), 403

        # Kalau mau aktifkan verifikasi dokter:
        # if user.role == "DOKTER" and not user.is_verified:
        #     return jsonify({"error": "Akun dokter belum diverifikasi admin."}), 403

        # 5) INI INTINYA: Login ke Flask-Login session
        login_user(user)

        # Return JSON agar frontend bisa redirect sendiri
        return jsonify({
            "status": "ok",
            "role": user.role,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
            }
        }), 200

    except Exception:
        # Sebaiknya log exception detail di server log
        return jsonify({"error": "Unauthorized"}), 401


@web_session_bp.post("/sessionLogout")
def session_logout():
    """
    Logout untuk web session Flask-Login.
    Endpoint tetap dipertahankan agar frontend yang sudah ada tidak perlu diubah banyak.
    """
    logout_user()
    return jsonify({"status": "ok"}), 200
