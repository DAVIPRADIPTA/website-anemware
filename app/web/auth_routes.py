# app/web/auth_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.models.user import User

web_auth_bp = Blueprint("web_auth", __name__, url_prefix="/web")

@web_auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Kalau sudah login, lempar ke dashboard sesuai role
    if current_user.is_authenticated:
        if current_user.role == "ADMIN":
            return redirect(url_for("admin.dashboard"))
        elif current_user.role == "DOKTER":
            return redirect(url_for("doctor.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Email atau password salah", "danger")
            return redirect(url_for("web_auth.login"))

        # Batasi hanya Admin & Dokter yang boleh login ke panel web
        if user.role not in ["ADMIN", "DOKTER"]:
            flash("Akses hanya untuk Admin dan Dokter", "danger")
            return redirect(url_for("web_auth.login"))

        # Kalau dokter belum diverifikasi, boleh dipakai aturan yang sama
        # if user.role == "DOKTER" and not user.is_verified:
        #     flash("Akun dokter Anda belum diverifikasi Admin.", "warning")
        #     return redirect(url_for("web_auth.login"))

        login_user(user)

        # Redirect berdasarkan role
        if user.role == "ADMIN":
            return redirect(url_for("admin.dashboard"))
        else:
            return redirect(url_for("doctor.dashboard"))

    # GET → tampilkan form
    return render_template("web/auth/login.html")


@web_auth_bp.route("/logout")
def logout():
    logout_user()
    resp = redirect(url_for("web_auth.login"))
    resp.delete_cookie("session")
    return resp


