from app.extensions import db
from datetime import datetime

class Consultation(db.Model):
    __tablename__ = 'consultations'

    id = db.Column(db.Integer, primary_key=True)
    
    # Siapa pasiennya? Siapa dokternya?
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Status Konsultasi
    # 'pending' (belum bayar), 'active' (sedang chat), 'completed' (selesai)
    status = db.Column(db.String(20), default='pending')

    expired_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relasi
    patient = db.relationship('User', foreign_keys=[patient_id], backref='patient_consultations')
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref='doctor_consultations')

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultations.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultations.id'), nullable=False)
    
    amount = db.Column(db.Integer, nullable=False) # Harga dalam Rupiah
    payment_method = db.Column(db.String(50), nullable=True) # 'gopay', 'bca', dll
    
    # Status Pembayaran: 'pending', 'success', 'failed'
    status = db.Column(db.String(20), default='pending')
    
    # ID Transaksi dari Payment Gateway (Misal: Order ID Midtrans)
    transaction_id = db.Column(db.String(100), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)