from flask import Blueprint, request
from datetime import datetime, timedelta
from app.extensions import db
from app.models.consultation import Consultation, Payment, ChatMessage
from app.models.user import User
from app.utils.response import success, error
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, socketio # <--- Tambahkan socketio
from app.services.payment_service import payment_service
from sqlalchemy import or_

consultation_bp = Blueprint('consultation_api', __name__, url_prefix='/api/consultation')

# --- 1. BOOKING DOKTER (Membuat Tagihan) ---
@consultation_bp.route('/book', methods=['POST'])
@jwt_required()
def book_consultation():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id) # Ambil data user buat dikirim ke Midtrans
    
    data = request.get_json()
    doctor_id = data.get('doctor_id')
    
    if not doctor_id:
        return error("Doctor ID wajib diisi", 400)
        
    doctor = User.query.get(doctor_id)
    if not doctor or doctor.role != 'DOKTER':
        return error("Dokter tidak ditemukan", 404)

    # 1. Buat Data Konsultasi
    new_consultation = Consultation(
        patient_id=current_user_id,
        doctor_id=doctor_id,
        status='pending'
    )
    db.session.add(new_consultation)
    db.session.flush()

    # 2. Buat Order ID Unik (PENTING: Midtrans menolak ID yang sama dipakai 2x)
    # Format: ORDER-{timestamp}-{consultation_id}
    order_id = f"ORDER-{int(datetime.now().timestamp())}-{new_consultation.id}"

    # 3. Buat Data Payment di Database Kita
    new_payment = Payment(
        consultation_id=new_consultation.id,
        amount=doctor.consultation_price,
        status='pending',
        payment_method='midtrans',
        transaction_id=order_id # Simpan Order ID ini
    )
    db.session.add(new_payment)
    
    # 4. Panggil Midtrans (Minta Link Bayar)
    customer_info = {
        "first_name": user.full_name,
        "email": user.email,
    }
    
    midtrans_resp = payment_service.create_transaction(
        order_id=order_id,
        amount=doctor.consultation_price,
        customer_details=customer_info
    )
    
    if not midtrans_resp:
        db.session.rollback()
        return error("Gagal menghubungi gateway pembayaran", 500)

    db.session.commit()
    
    return success({
        "consultation_id": new_consultation.id,
        "payment_id": new_payment.id,
        "amount": new_payment.amount,
        "status": "Menunggu Pembayaran",
        # INI YANG PENTING:
        "payment_url": midtrans_resp['redirect_url'], 
        "payment_token": midtrans_resp['token']
    }, "Booking berhasil, silakan akses payment_url untuk membayar")

# --- 2. PEMBAYARAN MOCK (Pura-pura Bayar Langsung Lunas) ---
# Nanti endpoint ini diganti dengan Webhook Midtrans
@consultation_bp.route('/pay/<int:payment_id>', methods=['POST'])
@jwt_required()
def mock_payment_success(payment_id):
    payment = Payment.query.get(payment_id)
    
    if not payment:
        return error("Tagihan tidak ditemukan", 404)
        
    # 1. Update Status Pembayaran
    payment.status = 'success'
    payment.transaction_id = f"MOCK-{datetime.now().timestamp()}"
    
    # 2. Aktifkan Sesi Konsultasi
    consultation = Consultation.query.get(payment.consultation_id)
    consultation.status = 'active'
    
    # 3. Set Durasi 1 JAM dari sekarang
    consultation.expired_at = datetime.utcnow() + timedelta(hours=1)
    
    db.session.commit()
    
    return success({
        "consultation_id": consultation.id,
        "expired_at": consultation.expired_at,
        "status": "active"
    }, "Pembayaran Berhasil! Sesi Chat dimulai (Berlaku 1 Jam).")

# --- WEBHOOK MIDTRANS (PENTING) ---
# Endpoint ini dipanggil oleh Server Midtrans, bukan oleh User!
@consultation_bp.route('/notification', methods=['POST'])
def midtrans_notification():
    # Ambil data JSON yang dikirim Midtrans
    notification_data = request.get_json()
    
    order_id = notification_data.get('order_id')
    transaction_status = notification_data.get('transaction_status')
    fraud_status = notification_data.get('fraud_status')
    
    print(f"🔔 Midtrans Notification: {order_id} -> {transaction_status}")

    # Cari Payment di Database kita berdasarkan order_id
    payment = Payment.query.filter_by(transaction_id=order_id).first()
    if not payment:
        return error("Order ID not found", 404)

    # Logika Status Midtrans
    # Settlement / Capture = Sukses (Uang masuk)
    # Pending = Menunggu
    # Deny / Cancel / Expire = Gagal
    
    if transaction_status == 'capture':
        if fraud_status == 'challenge':
            payment.status = 'challenge'
        else:
            payment.status = 'success'
            activate_consultation(payment) # Fungsi helper (lihat bawah)
            
    elif transaction_status == 'settlement':
        payment.status = 'success'
        activate_consultation(payment)
        
    elif transaction_status in ['cancel', 'deny', 'expire']:
        payment.status = 'failed'
        
    elif transaction_status == 'pending':
        payment.status = 'pending'

    db.session.commit()
    return success(None, "Notification processed")

def activate_consultation(payment):
    """Mengaktifkan sesi konsultasi (Durasi 1 Jam)"""
    consultation = Consultation.query.get(payment.consultation_id)
    # Pastikan kita cuma proses kalau status sebelumnya belum active (biar saldo gak nambah 2x)
    if consultation and consultation.status == 'pending':
        # 1. Aktifkan Sesi
        consultation.status = 'active'
        consultation.expired_at = datetime.utcnow() + timedelta(hours=1)
        
        # 2. LOGIKA BAGI HASIL (Revenue Sharing)
        doctor = User.query.get(consultation.doctor_id)
        
        # Contoh: Admin ambil 10%, Dokter dapat 90%
        admin_fee = int(payment.amount * 0.10) 
        doctor_income = int(payment.amount - admin_fee)
        
        # Update Saldo Dokter
        doctor.balance += doctor_income
        
        print(f"💰 Payment Lunas! Saldo Dr. {doctor.full_name} bertambah Rp {doctor_income}")


# --- 3. KIRIM PESAN (Chatting) ---
@consultation_bp.route('/send', methods=['POST'])
@jwt_required()
def send_message():
    current_user_id = int(get_jwt_identity())
    
    data = request.get_json()
    consultation_id = data.get('consultation_id')
    message_text = data.get('message')
    
    if not consultation_id or not message_text:
        return error("Data tidak lengkap", 400)
        
    consultation = Consultation.query.get(consultation_id)
    
    # Validasi Sesi
    if not consultation:
        return error("Sesi tidak ditemukan", 404)
        
    # Cek apakah user terlibat dalam sesi ini (Safety)
    if current_user_id not in [consultation.patient_id, consultation.doctor_id]:
        return error("Anda tidak memiliki akses ke sesi ini", 403)
        
    # Cek Status Aktif
    if consultation.status != 'active':
        return error("Sesi chat belum aktif (belum bayar) atau sudah selesai.", 400)
        
    # Cek Kedaluwarsa Waktu (1 Jam tadi)
    if datetime.utcnow() > consultation.expired_at:
        consultation.status = 'completed' # Tutup otomatis
        db.session.commit()
        return error("Waktu konsultasi telah habis.", 400)

    # Simpan Pesan
    new_chat = ChatMessage(
        consultation_id=consultation_id,
        sender_id=current_user_id,
        message=message_text
    )
    db.session.add(new_chat)
    db.session.commit()
    
    # --- UPDATE: KIRIM SINYAL REAL-TIME ---
    # 1. Tentukan nama room (misal: consultation_10)
    room_id = f"consultation_{consultation_id}"
    
    # 2. Siapkan data pesan yang mau dikirim ke layar lawan bicara
    message_data = {
        "id": new_chat.id,
        "sender_id": new_chat.sender_id,
        "message": new_chat.message,
        "timestamp": new_chat.created_at.isoformat(),
        # Flag ini nanti diatur frontend, tapi kita kirim false defaultnya
        "is_me": False 
    }
    
    # 3. Teriakkan ke Room!
    print(f"📢 Mengirim notifikasi ke room: {room_id}")
    socketio.emit('new_message', message_data, to=room_id)
    # --------------------------------------
    
    return success(None, "Pesan terkirim")

# --- 4. LIHAT RIWAYAT CHAT ---
@consultation_bp.route('/<int:consultation_id>/messages', methods=['GET'])
@jwt_required()
def get_chat_history(consultation_id):
    current_user_id = int(get_jwt_identity())
    consultation = Consultation.query.get(consultation_id)
    
    if not consultation:
        return error("Sesi tidak ditemukan", 404)
        
    # Validasi Akses
    if current_user_id not in [consultation.patient_id, consultation.doctor_id]:
        return error("Akses ditolak", 403)
        
    # --- LOGIKA BARU: Ambil Info Lawan Bicara ---
    # Jika yang request adalah Pasien, maka lawannya Dokter (dan sebaliknya)
    if current_user_id == consultation.patient_id:
        opponent = consultation.doctor
    else:
        opponent = consultation.patient

    opponent_photo = None
    if opponent and opponent.profile_image:
        opponent_photo = request.host_url + opponent.profile_image

    # Info Header Chat
    chat_info = {
        "consultation_id": consultation.id,
        "status": consultation.status,
        "expired_at": consultation.expired_at,
        "opponent": {
            "id": opponent.id,
            "name": opponent.full_name,
            "role": opponent.role,
            "image": opponent_photo,  # <--- Foto untuk Header Chat
            "specialization": getattr(opponent, 'specialization', None) # Jika dokter, tampilkan spesialisasi
        }
    }

    # Ambil pesan urut dari yang terlama ke terbaru
    messages = ChatMessage.query.filter_by(consultation_id=consultation_id)\
        .order_by(ChatMessage.created_at.asc()).all()
        
    list_pesan = []
    for msg in messages:
        # Opsional: Jika ingin setiap bubble chat ada fotonya juga
        # (Tapi biasanya cukup di header saja biar hemat data)
        list_pesan.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "message": msg.message,
            "timestamp": msg.created_at.isoformat(), # <--- Tambahkan .isoformat()
            "is_me": msg.sender_id == current_user_id 
        })
    
    # Gabungkan info header dan list pesan
    result = {
        "info": chat_info,
        "messages": list_pesan
    }
        
    return success(result, "Riwayat chat berhasil diambil")

# --- TAMBAHAN BARU: 1. GET MY CONSULTATION LIST (Inbox Chat) ---
@consultation_bp.route('/mine', methods=['GET'])
@jwt_required()
def get_my_consultations():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)

    # Ambil konsultasi dimana user bertindak sebagai PASIEN atau DOKTER
    consultations = Consultation.query.filter(
        or_(
            Consultation.patient_id == current_user_id,
            Consultation.doctor_id == current_user_id
        )
    ).order_by(Consultation.updated_at.desc()).all()

    output = []
    for c in consultations:
        # Tentukan Lawan Bicara (Opponent)
        if user.role == 'PASIEN':
            opponent = c.doctor
        else:
            opponent = c.patient
            
        # Siapkan URL foto lawan bicara
        opponent_photo = None
        if opponent and opponent.profile_image:
            opponent_photo = request.host_url + opponent.profile_image

        output.append({
            "id": c.id,
            "status": c.status,
            "updated_at": c.updated_at,
            # Data Lawan Bicara (Untuk ditampilkan di List)
            "opponent": {
                "id": opponent.id if opponent else 0,
                "name": opponent.full_name if opponent else "User Terhapus",
                "role": opponent.role if opponent else "-",
                "image": opponent_photo, # <--- Foto Profil Muncul Disini
                "is_online": opponent.is_online if opponent and hasattr(opponent, 'is_online') else False
            }
        })

    return success(output, "Berhasil mengambil daftar konsultasi")

# --- 5. GET LIST DOCTORS (Cari Dokter) ---
@consultation_bp.route('/doctors', methods=['GET'])
@jwt_required()
def get_list_doctors():
    # Ambil parameter query dari URL (misal: ?q=budi&spec=anak)
    search_query = request.args.get('q')
    spec_query = request.args.get('spec')
    
    # 1. Base Query: Cari User Role DOKTER yang SUDAH DIVERIFIKASI
    # (Penting: Jangan tampilkan dokter yang belum di-approve admin)
    query = User.query.filter_by(role='DOKTER', is_verified=True)
    
    # 2. Filter Search Nama (Jika ada input)
    if search_query:
        query = query.filter(User.full_name.ilike(f"%{search_query}%"))
        
    # 3. Filter Spesialisasi (Jika ada input)
    if spec_query:
        query = query.filter(User.specialization.ilike(f"%{spec_query}%"))
        
    # 4. Urutkan: Yang Online duluan, baru sisanya
    doctors = query.order_by(User.is_online.desc(), User.full_name.asc()).all()
    
    output = []
    for doc in doctors:
        # Generate URL Foto
        full_image_url = request.host_url + doc.profile_image if doc.profile_image else None
        
        output.append({
            "id": doc.id,
            "full_name": doc.full_name,
            "specialization": doc.specialization or "Dokter Umum", # Default jika kosong
            "price": doc.consultation_price or 0,
            "is_online": doc.is_online,
            "image": full_image_url,
            "bio": doc.bio
        })
        
    return success(output, "Berhasil mengambil daftar dokter")


# Tambahkan ini di backend Flask kamu untuk testing
@consultation_bp.route('/start', methods=['POST'])
@jwt_required()
def start_consultation_direct():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    doctor_id = data.get('doctor_id')

    # Cek apakah sudah ada sesi chat aktif/pending dengan dokter ini?
    existing = Consultation.query.filter_by(
        patient_id=current_user_id, 
        doctor_id=doctor_id
    ).order_by(Consultation.created_at.desc()).first()

    if existing:
        # Jika ada, kembalikan ID yang lama saja (Resume chat)
        return success({"consultation_id": existing.id}, "Melanjutkan chat")

    # Jika belum ada, buat baru (Bypass Payment untuk Testing)
    new_chat = Consultation(
        patient_id=current_user_id,
        doctor_id=doctor_id,
        status='active', # Langsung aktif
        expired_at=datetime.utcnow() + timedelta(days=1)
    )
    db.session.add(new_chat)
    db.session.commit()

    return success({"consultation_id": new_chat.id}, "Chat dimulai")