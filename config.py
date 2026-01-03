import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Konfigurasi Upload
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app/static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # Batas max file 16MB
    

    # Cookie secure hanya TRUE di HTTPS production
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


     # Firebase Admin SDK (download dari Firebase Console -> Service accounts)
    FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "serviceAccountKey.json")

    # === Chatbot / Unsloth ===
    BASE_MODEL_NAME = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
    LORA_PATH = "lora_adapter_3b"   # path folder adapter kamu
    MAX_NEW_TOKENS = 256
    TEMPERATURE = 0.7
    TOP_P = 0.9


