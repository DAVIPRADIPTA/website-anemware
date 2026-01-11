from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.feedback import Feedback
from app.utils.response import success, error

feedback_bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")


def _current_user_id() -> int:
    try:
        return int(get_jwt_identity())
    except Exception:
        return 0


@feedback_bp.route("", methods=["POST"])
@jwt_required()
def create_feedback():
    """
    POST /api/feedback
    Body JSON:
    {
      "rating": 5,
      "comment": "Aplikasinya membantu banget",
    }
    """
    user_id = _current_user_id()
    if not user_id:
        return error("Unauthorized", 401)

    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    comment = (data.get("comment") or "").strip()

    # validasi rating
    if rating is None:
        return error("rating wajib diisi", 400)
    try:
        rating = int(rating)
    except Exception:
        return error("rating harus berupa angka", 400)

    if rating < 1 or rating > 5:
        return error("rating harus 1 sampai 5", 400)

    # comment opsional, tapi kalau ada batasi panjang biar aman
    if comment and len(comment) > 2000:
        return error("comment terlalu panjang (max 2000 karakter)", 400)

    fb = Feedback(
        user_id=user_id,
        rating=rating,
        comment=comment if comment else None,
    )

    db.session.add(fb)
    db.session.commit()

    return success(
        {
            "id": fb.id,
            "rating": fb.rating,
            "comment": fb.comment,
            "created_at": fb.created_at.isoformat(),
        },
        "Feedback berhasil dikirim",
        201,
    )


@feedback_bp.route("/me", methods=["GET"])
@jwt_required()
def list_my_feedback():
    """
    GET /api/feedback/me?limit=20&offset=0
    """
    user_id = _current_user_id()
    if not user_id:
        return error("Unauthorized", 401)

    limit = request.args.get("limit", default=20, type=int)
    offset = request.args.get("offset", default=0, type=int)

    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    rows = (
        Feedback.query
        .filter_by(user_id=user_id)
        .order_by(Feedback.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return success(
        [
            {
                "id": r.id,
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "Berhasil mengambil feedback saya",
    )


@feedback_bp.route("/me/summary", methods=["GET"])
@jwt_required()
def my_feedback_summary():
    """
    GET /api/feedback/me/summary
    -> ringkasan sederhana untuk user (avg rating, count)
    """
    user_id = _current_user_id()
    if not user_id:
        return error("Unauthorized", 401)

    # hitung sederhana tanpa sqlalchemy func biar gampang
    rows = Feedback.query.filter_by(user_id=user_id).all()
    if not rows:
        return success({"count": 0, "avg_rating": None}, "Ringkasan feedback")

    count = len(rows)
    avg = sum(r.rating for r in rows) / count

    return success(
        {"count": count, "avg_rating": round(avg, 2)},
        "Ringkasan feedback",
    )
