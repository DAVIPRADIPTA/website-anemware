import os
import numpy as np
from PIL import Image
import tensorflow as tf
import cv2  # Kita pakai OpenCV untuk image processing
from flask import current_app

class AnemiaPredictor:
    def __init__(self):
        self.eye_model = None
        self.nail_model = None
        self.is_loaded = False
        # MediaPipe dihapus, tidak perlu inisialisasi lagi

    def load_models(self):
        """Load model hanya sekali saat aplikasi dijalankan"""
        if not self.is_loaded:
            service_dir = os.path.dirname(os.path.abspath(__file__)) 
            app_dir = os.path.dirname(service_dir)
            model_dir = os.path.join(app_dir, 'model')
            
            # 1. Load Model Mata
            eye_filename = 'hb_multitask_model.keras' 
            eye_path = os.path.join(model_dir, eye_filename)
            print(f"🔍 Loading Model Mata: {eye_filename}...")
            try:
                self.eye_model = tf.keras.models.load_model(eye_path)
                print(f"✅ Model Mata BERHASIL dimuat!")
            except Exception as e:
                print(f"❌ Gagal memuat Model Mata: {e}")

            # 2. Load Model Kuku
            nail_filename = 'kuku.keras' 
            nail_path = os.path.join(model_dir, nail_filename)
            print(f"🔍 Loading Model Kuku: {nail_filename}...")
            try:
                self.nail_model = tf.keras.models.load_model(nail_path)
                print(f"✅ Model Kuku BERHASIL dimuat!")
            except Exception as e:
                print(f"❌ Gagal memuat Model Kuku: {e}")
            
            self.is_loaded = True

    def smart_crop_eye(self, image_path):
        """
        PENGGANTI MEDIAPIPE:
        Menggunakan Segmentasi Warna (LAB) untuk mencari area merah (konjungtiva).
        Cocok untuk foto close-up.
        """
        # 1. Load Image pakai OpenCV
        img = cv2.imread(image_path)
        if img is None: return None
        
        # 2. Pre-processing (Blur)
        blurred = cv2.GaussianBlur(img, (5, 5), 0)
        
        # 3. Konversi ke LAB Color Space (Channel A = Green-Red)
        lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # 4. Thresholding Otomatis (Otsu) pada channel A (Mencari warna merah dominan)
        _, mask = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 5. Rapikan Mask (Morphology)
        kernel = np.ones((3,3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2) # Hapus noise
        mask = cv2.dilate(mask, kernel, iterations=2) # Pertebal area merah

        # 6. Cari area merah terbesar (Kontur)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        final_mask = np.zeros_like(mask)
        
        # Default crop (jika gagal) adalah ambil tengah
        h_img, w_img = img.shape[:2]
        x, y, w, h = int(w_img*0.2), int(h_img*0.3), int(w_img*0.6), int(h_img*0.5) 

        if contours:
            # Ambil kontur terbesar
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Filter jika terlalu kecil (noise)
            if cv2.contourArea(largest_contour) > 500:
                cv2.drawContours(final_mask, [largest_contour], -1, 255, thickness=cv2.FILLED)
                x, y, w, h = cv2.boundingRect(largest_contour)
                print("✨ Segmentasi Warna Berhasil! Konjungtiva ditemukan.")
            else:
                print("⚠️ Area merah terlalu kecil, menggunakan crop tengah default.")

        # 7. Terapkan Masking (Background jadi hitam)
        masked_img = cv2.bitwise_and(img, img, mask=final_mask)

        # 8. Crop kotak fokus (dengan sedikit padding)
        pad = 10
        y1 = max(0, y - pad)
        y2 = min(h_img, y + h + pad)
        x1 = max(0, x - pad)
        x2 = min(w_img, x + w + pad)
        
        final_cropped = masked_img[y1:y2, x1:x2]
        
        # Cek jika hasil crop kosong
        if final_cropped.size == 0:
            return Image.open(image_path).convert('RGB')

        # Convert balik ke PIL Image (RGB) agar bisa masuk ke fungsi preprocess selanjutnya
        return Image.fromarray(cv2.cvtColor(final_cropped, cv2.COLOR_BGR2RGB))

    def preprocess_image(self, pil_image, target_size=(224, 224)):
        """Ubah gambar PIL jadi array AI"""
        img = pil_image.resize(target_size)
        img_array = np.array(img)
        img_array = img_array / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        return img_array

    def predict_single_model(self, model, img_path, model_name="Model", is_eye=False):
        # 1. Smart Crop (Khusus Mata pakai LAB Color)
        if is_eye:
            pil_img = self.smart_crop_eye(img_path)
        else:
            pil_img = Image.open(img_path).convert('RGB') # Kuku tidak perlu crop
            
        # 2. Preprocess
        processed_img = self.preprocess_image(pil_img)
        
        # 3. Predict
        predictions = model.predict(processed_img)

        # 4. Extract Output (Multitask logic)
        if isinstance(predictions, list) and len(predictions) >= 2:
            # Index 1 adalah Regresi Hb
            hb_pred = float(np.squeeze(predictions[1])) 
            print(f"📊 {model_name} Result -> Hb: {hb_pred:.2f}")
            return hb_pred
        else:
            val = float(np.squeeze(predictions))
            print(f"⚠️ {model_name} output tunggal: {val}")
            return val

    def predict(self, eye_image_path=None, nail_image_path=None):
        self.load_models() 
        
        hb_eye = None
        hb_nail = None

        if eye_image_path and self.eye_model:
            hb_eye = self.predict_single_model(self.eye_model, eye_image_path, "Mata", is_eye=True)

        if nail_image_path and self.nail_model:
            hb_nail = self.predict_single_model(self.nail_model, nail_image_path, "Kuku", is_eye=False)

        return hb_eye, hb_nail

ai_service = AnemiaPredictor()