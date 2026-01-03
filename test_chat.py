import socketio

# Pura-pura jadi Pasien
sio = socketio.Client()

@sio.event
def connect():
    print("✅ Terhubung ke Server Socket!")
    # Masuk ke Room Konsultasi ID 1 (Ganti angka 1 sesuai ID konsultasi Anda)
    sio.emit('join', {'room': 'consultation_2'})

@sio.event
def new_message(data):
    print("\n🔔 PING! ADA PESAN MASUK!")
    print(f"📩 Isi: {data['message']}")
    print(f"🕒 Jam: {data['timestamp']}")
    print("-" * 20)

# Connect ke Server Flask
sio.connect('http://localhost:5000')
sio.wait()