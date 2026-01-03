from app.extensions import db
from datetime import datetime

class MedicalRecord(db.Model):
    __tablename__ = 'medical_records'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # --- GAMBAR (Bisa Null jika user cuma upload salah satu) ---
    eye_image_path = db.Column(db.String(255), nullable=True)
    nail_image_path = db.Column(db.String(255), nullable=True)

    # --- HASIL AI ---
    hb_prediction = db.Column(db.Float, nullable=False)   # Nilai Hb Medis (g/dL)
    
    # --- GEJALA ---
    symptoms_list = db.Column(db.Text, nullable=True)     # Teks: "Pusing (Sering), Pucat (Kadang)"
    symptoms_score = db.Column(db.Float, nullable=False)  # Skor Angka: 45.0
    
    # --- HASIL AKHIR ---
    final_score = db.Column(db.Float, nullable=False)     # Skor Kombinasi (0-100)
    risk_level = db.Column(db.String(20), nullable=False) # RENDAH / SEDANG / TINGGI
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('records', lazy=True))

    def __repr__(self):
        return f"<MedicalRecord ID: {self.id} - Risk: {self.risk_level}>"