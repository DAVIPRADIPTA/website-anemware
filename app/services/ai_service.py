import os
import numpy as np
from PIL import Image
import tensorflow as tf
import cv2

from tensorflow.keras.applications.mobilenet_v2 import preprocess_input


# =========================
# CUSTOM METRIC (WAJIB)
# =========================
def tolerance_accuracy(y_true, y_pred):
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    diff = tf.abs(y_true - y_pred)
    return tf.reduce_mean(tf.cast(diff < 1.0, tf.float32))


class AnemiaPredictor:
    def __init__(self):
        self.eye_model = None
        self.nail_model = None
        self.is_loaded = False

        # model file names
        self.eye_filename = "model_konjungtiva.h5"
        self.nail_filename = "model_kuku.h5"

    def _get_model_dir(self) -> str:
        service_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(service_dir)
        return os.path.join(app_dir, "model")

    def load_models(self):
        """Load model hanya sekali"""
        if self.is_loaded:
            return

        model_dir = self._get_model_dir()

        # 1) Load Model Mata
        eye_path = os.path.join(model_dir, self.eye_filename)
        print(f"🔍 Loading Model Mata: {eye_path}")
        try:
            self.eye_model = tf.keras.models.load_model(
                eye_path,
                custom_objects={"tolerance_accuracy": tolerance_accuracy},
                compile=False,  # lebih aman lintas versi TF
            )
            print("✅ Model Mata dimuat!")
        except Exception as e:
            print(f"❌ Gagal memuat Model Mata: {e}")
            self.eye_model = None

        # 2) Load Model Kuku
        nail_path = os.path.join(model_dir, self.nail_filename)
        print(f"🔍 Loading Model Kuku: {nail_path}")
        try:
            self.nail_model = tf.keras.models.load_model(
                nail_path,
                custom_objects={"tolerance_accuracy": tolerance_accuracy},
                compile=False,
            )
            print("✅ Model Kuku dimuat!")
        except Exception as e:
            print(f"❌ Gagal memuat Model Kuku: {e}")
            self.nail_model = None

        self.is_loaded = True

    # =========================
    # SMART CROP EYE (punyamu)
    # =========================
    def smart_crop_eye(self, image_path: str):
        img = cv2.imread(image_path)
        if img is None:
            return None

        blurred = cv2.GaussianBlur(img, (5, 5), 0)
        lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB)
        _, a, _ = cv2.split(lab)

        _, mask = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        final_mask = np.zeros_like(mask)
        h_img, w_img = img.shape[:2]
        x, y, w, h = int(w_img * 0.2), int(h_img * 0.3), int(w_img * 0.6), int(h_img * 0.5)

        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest_contour) > 500:
                cv2.drawContours(final_mask, [largest_contour], -1, 255, thickness=cv2.FILLED)
                x, y, w, h = cv2.boundingRect(largest_contour)
                print("✨ Konjungtiva ditemukan (segmentasi LAB).")
            else:
                print("⚠️ Area merah kecil, pakai crop default.")

        masked_img = cv2.bitwise_and(img, img, mask=final_mask)

        pad = 10
        y1 = max(0, y - pad)
        y2 = min(h_img, y + h + pad)
        x1 = max(0, x - pad)
        x2 = min(w_img, x + w + pad)

        cropped = masked_img[y1:y2, x1:x2]
        if cropped.size == 0:
            return Image.open(image_path).convert("RGB")

        return Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))

    # =========================
    # PREPROCESS (DIUBAH!)
    # =========================
    def preprocess_image(self, pil_image: Image.Image, target_size=(224, 224)):
        """
        MobileNetV2 preprocess:
        - Input float32
        - preprocess_input => skala ke [-1..1]
        """
        img = pil_image.resize(target_size)
        arr = np.array(img).astype("float32")
        arr = np.expand_dims(arr, axis=0)   # (1,224,224,3)
        arr = preprocess_input(arr)         # IMPORTANT
        return arr

    def _extract_hb(self, predictions):
        """
        Aman untuk:
        - output array (1,1)
        - output list multitask
        """
        if isinstance(predictions, list):
            # Kalau multitask, Hb sering ada di output terakhir atau index tertentu.
            # Di kode lama kamu pakai index [1].
            # Kita coba: kalau ada >=2, ambil [1]; kalau tidak, ambil terakhir.
            if len(predictions) >= 2:
                return float(np.squeeze(predictions[1]))
            return float(np.squeeze(predictions[-1]))

        return float(np.squeeze(predictions))

    def predict_single_model(self, model, img_path: str, model_name="Model", is_eye=False):
        if is_eye:
            pil_img = self.smart_crop_eye(img_path)
            if pil_img is None:
                pil_img = Image.open(img_path).convert("RGB")
        else:
            pil_img = Image.open(img_path).convert("RGB")

        x = self.preprocess_image(pil_img)
        preds = model.predict(x, verbose=0)

        hb = self._extract_hb(preds)
        print(f"📊 {model_name} Hb: {hb:.2f}")
        return hb

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
