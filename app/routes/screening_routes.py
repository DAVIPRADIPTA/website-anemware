import os
import json
import time
from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models.medical import MedicalRecord
from app.services.ai_service import ai_service
from app.utils.response import success, error
from flask_jwt_extended import jwt_required, get_jwt_identity

screening_bp = Blueprint('screening', __name__, url_prefix='/api/screening')

# --- KONFIGURASI BOBOT GEJALA (REMAJA PUTRI) ---
BASE_WEIGHTS = {
    "lemas": 15, "pusing": 10, "fokus": 10, "pucat": 15, 
    "jantung": 10, "haid_banyak": 20, "haid_lama": 20
}

# 0=Tidak, 1=Kadang (50%), 2=Sering (100%)
SCORE_MULTIPLIER = { 0: 0.0, 1: 0.5, 2: 1.0 }

# --- FUNGSI BANTUAN ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

def calculate_weighted_symptoms(gejala_input):
    total_score = 0
    summary = []
    try:
        data = json.loads(gejala_input) if isinstance(gejala_input, str) else gejala_input
        for key, level in data.items():
            if key in BASE_WEIGHTS and int(level) in SCORE_MULTIPLIER:
                points = BASE_WEIGHTS[key] * SCORE_MULTIPLIER[int(level)]
                total_score += points
                if int(level) > 0:
                    ket = "Sering" if int(level) == 2 else "Kadang"
                    summary.append(f"{key} ({ket})")
    except: return 0, ""
    return min(total_score, 100), ", ".join(summary)

def calculate_hb_risk_score(hb):
    # Hb >= 14 Sehat (Risiko 0), Hb <= 6 Parah (Risiko 100)
    if hb >= 14: return 0
    elif hb <= 6: return 100
    else: return ((14 - hb) / (14 - 6)) * 100

def get_risk_level(score):
    if score <= 30: return "RENDAH"
    elif score <= 70: return "SEDANG"
    else: return "TINGGI"

# --- ENDPOINT UTAMA ---
@screening_bp.route('/', methods=['POST'])
@jwt_required()
def submit_screening():
    current_user_id = get_jwt_identity()
    
    # 1. PROSES GEJALA
    raw_symptoms = request.form.get('symptoms', '{}')
    score_gejala, text_gejala = calculate_weighted_symptoms(raw_symptoms)
    
    # 2. PROSES GAMBAR
    file_mata = request.files.get('eye_image')
    file_kuku = request.files.get('nail_image')

    if not file_mata and not file_kuku:
        return error("Harap upload minimal satu gambar", 400)

    path_mata, path_kuku, db_path_mata, db_path_kuku = None, None, None, None
    
    if file_mata and allowed_file(file_mata.filename):
        fname = f"eye_{int(time.time())}_{secure_filename(file_mata.filename)}"
        path_mata = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
        file_mata.save(path_mata)
        db_path_mata = f"static/uploads/{fname}"

    if file_kuku and allowed_file(file_kuku.filename):
        fname = f"nail_{int(time.time())}_{secure_filename(file_kuku.filename)}"
        path_kuku = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
        file_kuku.save(path_kuku)
        db_path_kuku = f"static/uploads/{fname}"

    # 3. PREDIKSI AI
    try:
        hb_mata, hb_kuku = ai_service.predict(path_mata, path_kuku)
    except Exception as e:
        return error(f"Error AI: {str(e)}", 500)

    # 4. HITUNG RATA-RATA HB
    final_hb = 0
    if hb_mata and hb_kuku: final_hb = (hb_mata + hb_kuku) / 2
    elif hb_mata: final_hb = hb_mata
    elif hb_kuku: final_hb = hb_kuku

    # 5. HITUNG SKOR AKHIR (60% Fisik + 40% Gejala)
    risk_score_hb = calculate_hb_risk_score(final_hb)
    final_score = (risk_score_hb * 0.6) + (score_gejala * 0.4)
    risk_level = get_risk_level(final_score)

    # 6. SIMPAN DB
    rec = MedicalRecord(
        user_id=current_user_id,
        eye_image_path=db_path_mata, nail_image_path=db_path_kuku,
        hb_prediction=round(final_hb, 2),
        symptoms_list=text_gejala, symptoms_score=score_gejala,
        final_score=round(final_score, 2), risk_level=risk_level
    )
    db.session.add(rec)
    db.session.commit()

    return success({
        "hb": round(final_hb, 2),
        "risk": risk_level,
        "score": round(final_score, 2),
        "symptoms": text_gejala
    }, "Skrining Selesai")

@screening_bp.route('/history', methods=['GET'])
@jwt_required()
def get_my_screening_history():
    current_user_id = get_jwt_identity()

    # Ambil data record milik user yang sedang login
    # Urutkan dari yang paling baru (descending)
    records = MedicalRecord.query.filter_by(user_id=current_user_id)\
        .order_by(MedicalRecord.created_at.desc()).all()

    output = []
    for rec in records:
        # Generate Full URL untuk gambar (agar bisa diload di HP)
        eye_url = request.host_url + rec.eye_image_path if rec.eye_image_path else None
        nail_url = request.host_url + rec.nail_image_path if rec.nail_image_path else None

        output.append({
            "id": rec.id,
            "hb_prediction": rec.hb_prediction,   # Kadar Hb
            "risk_level": rec.risk_level,         # TINGGI/SEDANG/RENDAH
            "final_score": rec.final_score,       # Skor 0-100
            "symptoms_list": rec.symptoms_list,   # Text gejala
            "images": {
                "eye": eye_url,
                "nail": nail_url
            },
            "created_at": rec.created_at
        })

    return success(output, "Berhasil mengambil riwayat skrining")