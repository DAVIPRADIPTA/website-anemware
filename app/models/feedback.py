from datetime import datetime
from app.extensions import db

class Feedback(db.Model):
    __tablename__ = "feedbacks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # rating 1-5
    rating = db.Column(db.Integer, nullable=False)

    # saran/komentar optional
    comment = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # relasi opsional (kalau mau gampang akses user)
    user = db.relationship("User", backref=db.backref("feedbacks", lazy=True))
