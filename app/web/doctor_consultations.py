from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models.consultation import Consultation, ChatMessage
from app.extensions import db, socketio

doctor_consult_bp = Blueprint("doctor_consult", __name__, url_prefix="/doctor/consultations")


def _require_doctor():
    """Helper: pastikan user yang login adalah DOKTER."""
    if not current_user.is_authenticated:
        return False
    return getattr(current_user, "role", None) == "DOKTER"


# ===========================
# LIST KONSULTASI DOKTER
# ===========================
@doctor_consult_bp.route("/")
@login_required
def list_consultations():
    if not _require_doctor():
        return "Unauthorized", 403

    consultations = (
        Consultation.query
        .filter_by(doctor_id=current_user.id)
        .order_by(Consultation.created_at.desc())
        .all()
    )

    return render_template(
        "web/doctor/consultations/list.html",
        consultations=consultations,
        doctor=current_user
    )


# ===========================
# HALAMAN CHAT
# ===========================
@doctor_consult_bp.route("/<int:id>")
@login_required
def chat(id):
    if not _require_doctor():
        return "Unauthorized", 403

    consultation = Consultation.query.get_or_404(id)

    if consultation.doctor_id != current_user.id:
        return "Unauthorized", 403

    messages = (
        ChatMessage.query
        .filter_by(consultation_id=id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

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
    if not _require_doctor():
        return {"status": "error", "message": "Unauthorized"}, 403

    consultation = Consultation.query.get_or_404(id)

    if consultation.doctor_id != current_user.id:
        return {"status": "error", "message": "Unauthorized"}, 403

    data = request.get_json(silent=True) or {}
    message_text = (data.get("message") or "").strip()

    if not message_text:
        return {"status": "error", "message": "Pesan kosong"}, 400

    new_msg = ChatMessage(
        consultation_id=id,
        sender_id=current_user.id,
        message=message_text
    )
    db.session.add(new_msg)
    db.session.commit()

    timestamp = new_msg.created_at.isoformat()

    socketio.emit(
        "new_message",
        {
            "sender_id": current_user.id,
            "message": message_text,
            "timestamp": timestamp
        },
        to=f"consultation_{id}"
    )

    return {"status": "success", "message": "sent", "timestamp": timestamp}, 200
