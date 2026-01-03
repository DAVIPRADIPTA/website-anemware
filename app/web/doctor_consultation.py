from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.consultation import Consultation, ChatMessage
from app.extensions import db, socketio

from app.web.firebase_guard import firebase_web_required


doctor_consult_bp = Blueprint("doctor_consult", __name__, url_prefix="/doctor/consultations")


# ===========================
# LIST KONSULTASI DOKTER
# ===========================
@doctor_consult_bp.route("/")
@firebase_web_required(roles=["DOKTER"])
def list_consultations():
    current_user = request.current_user

    if current_user.role != "DOKTER":
        return "Unauthorized", 403

    consultations = Consultation.query.filter_by(
        doctor_id=current_user.id
    ).order_by(Consultation.created_at.desc()).all()

    return render_template(
        "web/doctor/consultations/list.html",
        consultations=consultations,
        doctor=current_user
    )



# ===========================
# HALAMAN CHAT
# ===========================
@doctor_consult_bp.route("/<int:id>")
@firebase_web_required(roles=["DOKTER"])
def chat(id):
    current_user = request.current_user

    if current_user.role != "DOKTER":
        return "Unauthorized", 403

    consultation = Consultation.query.get_or_404(id)

    if consultation.doctor_id != current_user.id:
        return "Unauthorized", 403

    messages = ChatMessage.query.filter_by(
        consultation_id=id
    ).order_by(ChatMessage.created_at.asc()).all()

    return render_template(
        "web/doctor/consultations/chat.html",
        consultation=consultation,
        messages=messages,
        doctor=current_user
    )


# ===========================
# KIRIM PESAN DARI WEB DOKTER
# ===========================
@doctor_consult_bp.route("/<int:id>/send", methods=["POST"])
@login_required
def send_message_web(id):
    if current_user.role != "DOKTER":
        return {"status": "error", "message": "Unauthorized"}, 403

    consultation = Consultation.query.get_or_404(id)

    if consultation.doctor_id != current_user.id:
        return {"status": "error", "message": "Unauthorized"}, 403

    data = request.get_json()
    message_text = data.get("message", "").strip()

    if not message_text:
        return {"status": "error", "message": "Pesan kosong"}, 400

    # Simpan pesan
    new_msg = ChatMessage(
        consultation_id=id,
        sender_id=current_user.id,
        message=message_text
    )
    db.session.add(new_msg)
    db.session.commit()

    timestamp = new_msg.created_at.isoformat()

    # Broadcast lengkap
    socketio.emit("new_message", {
        "sender_id": current_user.id,
        "message": message_text,
        "timestamp": timestamp
    }, to=f"consultation_{id}")

    return {"status": "success", "message": "sent", "timestamp": timestamp}
