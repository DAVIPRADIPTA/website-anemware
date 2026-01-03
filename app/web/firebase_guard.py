from functools import wraps
from flask import request, redirect, url_for
from firebase_admin import auth as fb_auth
from app.models.user import User

def firebase_web_required(roles=None):
    roles = roles or []

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            session_cookie = request.cookies.get("session")
            if not session_cookie:
                return redirect(url_for("web_auth.login"))

            try:
                decoded = fb_auth.verify_session_cookie(session_cookie, check_revoked=True)
            except Exception:
                return redirect(url_for("web_auth.login"))

            uid = decoded.get("uid")
            user = User.query.filter_by(firebase_uid=uid).first()
            if not user:
                return redirect(url_for("web_auth.login"))

            if roles and user.role not in roles:
                return "Unauthorized", 403

            # if user.role == "DOKTER" and not user.is_verified:
            #     return redirect(url_for("web_auth.login"))

            request.current_user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator
