from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, bcrypt
from flask_login import UserMixin  # <--- 1. TAMBAHKAN INI


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True) # Perbesar panjang karakter jaga-jaga
    full_name = db.Column(db.String(100), nullable=True)

    firebase_uid = db.Column(db.String(128), unique=True, nullable=True)
    auth_provider = db.Column(db.String(20), nullable=True)  # 'firebase' / 'password'


    role = db.Column(db.String(20), nullable=True) # 'PASIEN', 'DOKTER', 'ADMIN'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Kolom ini akan NULL (kosong) jika usernya adalah Pasien
    specialization = db.Column(db.String(100), nullable=True)
    consultation_price = db.Column(db.Integer, default=0) # Harga dalam Rupiah
    is_online = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text, nullable=True)

    profile_image = db.Column(db.String(255), nullable=True)

    # --- KOLOM BARU (YANG HILANG DI SCREENSHOT) ---
    # 1. Status Verifikasi (Agar Admin bisa ACC dokter)
    is_verified = db.Column(db.Boolean, default=False) 
    
    # 2. Dompet Digital (Untuk menampung uang hasil praktek)
    balance = db.Column(db.Integer, default=0)

    verification_doc = db.Column(db.String(255), nullable=True)


    # Update Fungsi Set Password
    def set_password(self, password):
        # Generate hash Bcrypt (hasilnya bytes, jadi perlu decode ke utf-8 biar jadi string)
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    # Update Fungsi Cek Password
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"