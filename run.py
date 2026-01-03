from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Gunakan socketio.run, bukan app.run agar fitur chat jalan nanti
    socketio.run(app, debug=True, port=5000)