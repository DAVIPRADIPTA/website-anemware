from app.extensions import db
from datetime import datetime

class Article(db.Model):
    __tablename__ = 'articles'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(255), nullable=True) # Menyimpan path gambar
    tags = db.Column(db.String(100), nullable=True) # Misal: "Anemia,Tips"
    
    # Siapa penulisnya? (Harus Dokter)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relasi ke user
    author = db.relationship('User', backref=db.backref('articles', lazy=True))

    def __repr__(self):
        return f"<Article {self.title}>"