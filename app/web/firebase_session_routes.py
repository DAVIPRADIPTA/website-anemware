from flask import Blueprint, request, jsonify, make_response, current_app
from firebase_admin import auth as fb_auth
from app.models.user import User
from app.extensions import db

web_session_bp = Blueprint("web_session", __name__)

@web_session_bp.post("/sessionLogin")
def session_login():
    body = request.get_json(silent=True) or {}
    id_token = body.get("idToken")
    role_hint = body.get("role")  # 'ADMIN' / 'DOKTER' dari tombol

    if not id_token:
        return jsonify({"error": "Missing idToken"}), 400

    try:
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        uid = decoded["uid"]
        email = (decoded.get("email") or "").lower()
        name = decoded.get("name") or decoded.get("displayName")
        picture = decoded.get("picture")

        if not email:
            return jsonify({"error": "Email tidak ditemukan dari Google"}), 400

        # Cari user (prioritas firebase_uid)
        user = User.query.filter_by(firebase_uid=uid).first()
        if not user:
            user = User.query.filter_by(email=email).first()

        # RULE WEB:
        # - ADMIN tidak auto-create
        # - DOKTER boleh auto-create tapi is_verified=False
        if not user:
            if role_hint == "ADMIN":
                return jsonify({"error": "Akun admin belum terdaftar. Hubungi super admin."}), 403

            if role_hint == "DOKTER":
                user = User(
                    email=email,
                    full_name=name,
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
            # Sink uid/provider bila belum ada
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

        # Role wajib dari DB (bukan role_hint)
        if user.role not in ["ADMIN", "DOKTER"]:
            return jsonify({"error": "Akses hanya untuk Admin & Dokter"}), 403

        # if user.role == "DOKTER" and not user.is_verified:
        #     return jsonify({"error": "Akun dokter belum diverifikasi admin."}), 403

        # Buat session cookie
        expires_in = 60 * 60 * 24 * 5  # 5 hari
        session_cookie = fb_auth.create_session_cookie(id_token, expires_in=expires_in)

        resp = make_response(jsonify({"status": "ok", "role": user.role}))
        resp.set_cookie(
            "session",
            session_cookie,
            max_age=expires_in,
            httponly=True,
            secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
            samesite="Lax",
        )
        return resp

    except Exception:
        return jsonify({"error": "Unauthorized"}), 401


@web_session_bp.post("/sessionLogout")
def session_logout():
    resp = make_response(jsonify({"status": "ok"}))
    resp.delete_cookie("session")
    return resp
