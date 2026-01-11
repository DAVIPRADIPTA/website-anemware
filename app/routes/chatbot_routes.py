from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.chatbot import ChatbotSession, ChatbotMessage

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/api/chatbot")


def _current_user_id() -> int:
    """Ambil user_id dari JWT identity (yang kamu set sebagai str(user.id))."""
    try:
        return int(get_jwt_identity())
    except Exception:
        return 0


@chatbot_bp.route("/session", methods=["POST"])
@jwt_required()
def create_session():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip() or None

    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    s = ChatbotSession(user_id=user_id, title=title)
    db.session.add(s)
    db.session.commit()

    return jsonify({"session_id": s.id, "title": s.title}), 201


@chatbot_bp.route("/send", methods=["POST"])
@jwt_required()
def send():
    """
    Body:
    {
      "session_id": 1,
      "message": "halo",
      "history_limit": 20, (optional)
      "max_new_tokens": 256, (optional)
      "temperature": 0.7, (optional)
      "top_p": 0.9 (optional)
    }
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    message = (data.get("message") or "").strip()

    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    if not session_id or not message:
        return jsonify({"error": "session_id dan message wajib"}), 400

    session = ChatbotSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "session tidak ditemukan"}), 404

    # Simpan pesan user
    db.session.add(ChatbotMessage(session_id=session_id, role="user", content=message))
    db.session.commit()

    # Ambil history terakhir
    history_limit = int(data.get("history_limit", 20))
    history = (
        ChatbotMessage.query
        .filter_by(session_id=session_id)
        .order_by(ChatbotMessage.id.desc())
        .limit(history_limit)
        .all()
    )
    history = list(reversed(history))

    # Susun input history
    previous_turns = []
    for m in history[:-1]:
        previous_turns.append(f"{m.role.upper()}: {m.content}")
    input_text = "\n".join(previous_turns)

    engine = current_app.extensions["llm_engine"]

    max_new_tokens = int(data.get("max_new_tokens", 256))
    temperature = float(data.get("temperature", 0.7))
    top_p = float(data.get("top_p", 0.9))

    reply = engine.generate(
        instruction=message,
        input_text=input_text,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
    )

    db.session.add(ChatbotMessage(session_id=session_id, role="assistant", content=reply))

    # (Opsional) kalau model ChatbotSession punya updated_at auto-update lewat trigger,
    # ini tidak perlu. Kalau tidak, kamu bisa set manual:
    # session.updated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({"reply": reply}), 200


@chatbot_bp.route("/history/<int:session_id>", methods=["GET"])
@jwt_required()
def history(session_id):
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    session = ChatbotSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "session tidak ditemukan"}), 404

    msgs = (
        ChatbotMessage.query
        .filter_by(session_id=session_id)
        .order_by(ChatbotMessage.id.asc())
        .all()
    )

    return jsonify({
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in msgs
        ]
    }), 200


@chatbot_bp.route("/sessions", methods=["GET"])
@jwt_required()
def list_sessions():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    sessions = (
        ChatbotSession.query
        .filter_by(user_id=user_id)
        .order_by(ChatbotSession.updated_at.desc())
        .all()
    )

    return jsonify({
        "sessions": [
            {
                "session_id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat()
            }
            for s in sessions
        ]
    }), 200
