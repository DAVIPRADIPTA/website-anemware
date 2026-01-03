from flask_socketio import join_room, leave_room
from app.extensions import socketio
from flask import request

# 1. Saat ada HP/Browser yang connect ke Socket
@socketio.on('connect')
def handle_connect():
    print(f"⚡ Client Connected: {request.sid}")

# 2. Saat User masuk ke halaman chat konsultasi tertentu
# Frontend harus kirim event 'join' dengan data {'room': 'consultation_1'}
@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        print(f"➡️ Client {request.sid} masuk ke room: {room}")

# 3. Saat User keluar dari halaman chat
@socketio.on('leave')
def handle_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)
        print(f"⬅️ Client {request.sid} keluar dari room: {room}")