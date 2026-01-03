from flask import Blueprint, request, jsonify, current_app
from app.extensions import db
from app.models.chatbot import ChatbotSession, ChatbotMessage

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/api/chatbot")

@chatbot_bp.route("/session", methods=["POST"])
def create_session():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    title = data.get("title")

    if not user_id:
        return jsonify({"error": "user_id wajib"}), 400

    s = ChatbotSession(user_id=user_id, title=title)
    db.session.add(s)
    db.session.commit()
    return jsonify({"session_id": s.id, "title": s.title}), 201

@chatbot_bp.route("/send", methods=["POST"])
def send():
    """
    Body:
    {
      "session_id": 1,
      "user_id": 123,
      "message": "halo",
      "max_new_tokens": 256, (optional)
      "temperature": 0.7, (optional)
      "top_p": 0.9 (optional)
    }
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    message = (data.get("message") or "").strip()

    if not session_id or not user_id or not message:
        return jsonify({"error": "session_id, user_id, message wajib"}), 400

    session = ChatbotSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "session tidak ditemukan"}), 404

    # Simpan pesan user
    db.session.add(ChatbotMessage(session_id=session_id, role="user", content=message))
    db.session.commit()

    # Ambil history terakhir (misal 10 pasang => 20 message)
    history_limit = int(data.get("history_limit", 20))
    history = (ChatbotMessage.query
               .filter_by(session_id=session_id)
               .order_by(ChatbotMessage.id.desc())
               .limit(history_limit)
               .all())
    history = list(reversed(history))

    # Jadikan "Input" agar sesuai template alpaca kamu:
    # - Instruction = pesan terakhir user
    # - Input = ringkasan history sebelumnya
    # Ini menjaga format prompt kamu tetap sama.
    previous_turns = []
    for m in history[:-1]:  # kecuali pesan terakhir (yang barusan dikirim)
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
    db.session.commit()

    return jsonify({"reply": reply}), 200

@chatbot_bp.route("/history/<int:session_id>", methods=["GET"])
def history(session_id):
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id wajib (query param)"}), 400

    session = ChatbotSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "session tidak ditemukan"}), 404

    msgs = (ChatbotMessage.query
            .filter_by(session_id=session_id)
            .order_by(ChatbotMessage.id.asc())
            .all())

    return jsonify({
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in msgs
        ]
    }), 200

@chatbot_bp.route("/sessions", methods=["GET"])
def list_sessions():
    """
    Query params:
    ?user_id=123
    """
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id wajib (query param)"}), 400

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
