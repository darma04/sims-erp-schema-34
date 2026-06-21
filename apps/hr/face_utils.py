"""
==========================================================================
 HR FACE UTILS - Utilitas Face Recognition & Validasi Lokasi GPS
==========================================================================
 File ini berisi utility functions untuk fitur absensi biometrik:

 1. LOCATION UTILITIES (Validasi GPS):
    - haversine_distance() → Hitung jarak 2 titik GPS (meter)
    - validate_location()  → Cek apakah user dalam radius kantor

 2. FACE DETECTION (Deteksi Wajah):
    - detect_face()         → Deteksi wajah dalam gambar (Haar Cascade)
    - image_to_array()      → Konversi file gambar → numpy array
    - base64_to_array()     → Konversi base64 → numpy array

 3. FACE ENCODING (Encoding Wajah):
    - encode_face()         → Generate encoding dari gambar wajah
    - encode_face_from_file()    → Encode dari file upload
    - encode_face_from_base64()  → Encode dari base64 string

 4. FACE COMPARISON (Perbandingan Wajah):
    - compare_faces()           → Bandingkan 2 encoding (LBPH + Multi-Strategy)
    - find_matching_karyawan()  → Cari karyawan yang cocok dari wajah
    - validate_face_exists()    → Validasi ada wajah di gambar

 Teknologi:
 - OpenCV (cv2) → Haar Cascade + LBPH + ORB Feature Descriptor
 - Multi-Strategy Comparison (LBPH + Histogram + ORB) untuk akurasi tinggi
 - Haversine Formula untuk kalkulasi jarak GPS

 Strategi Pengenalan (v2 - Robust):
 - LBPH Histogram: 50% bobot — pola tekstur lokal wajah, tahan perubahan cahaya
 - Histogram Correlation: 25% bobot — distribusi kecerahan global
 - ORB Feature Matching: 25% bobot — fitur titik kunci wajah
 - Multi-foto averaging: Score terbaik dari semua foto terdaftar
 - Face crop padding: Margin 20% untuk menghindari noise dari pakaian/latar

 Terhubung dengan:
 - hr/models.py → Karyawan, FotoWajah (model data wajah)
 - hr/views.py → API endpoint absensi
==========================================================================
"""
import cv2
import numpy as np
import base64
import json
import os
import math
from io import BytesIO
from PIL import Image
import logging

logger = logging.getLogger(__name__)


# ==================== LOCATION UTILITIES ====================

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Menghitung jarak antara dua koordinat GPS menggunakan rumus Haversine
    Args:
        lat1, lon1: Koordinat titik pertama (latitude, longitude dalam derajat)
        lat2, lon2: Koordinat titik kedua (latitude, longitude dalam derajat)
    Returns:
        Jarak dalam meter
    """
    # Radius bumi dalam meter
    R = 6371000
    
    # Konversi ke radian
    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))
    delta_lat = math.radians(float(lat2) - float(lat1))
    delta_lon = math.radians(float(lon2) - float(lon1))
    
    # Formula Haversine
    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance


def validate_location(user_lat, user_lon, office_lat, office_lon, radius_meters):
    """
    Validasi apakah lokasi user dalam radius kantor
    Args:
        user_lat, user_lon: Koordinat user
        office_lat, office_lon: Koordinat kantor
        radius_meters: Radius maksimal dalam meter
    Returns:
        (is_valid: bool, distance: float, message: str)
    """
    try:
        if not all([user_lat, user_lon, office_lat, office_lon]):
            return True, 0, "Koordinat tidak lengkap, validasi dilewati"
        
        distance = haversine_distance(user_lat, user_lon, office_lat, office_lon)
        distance_rounded = round(distance, 1)
        
        if distance <= radius_meters:
            return True, distance_rounded, f"Lokasi valid, jarak {distance_rounded}m dari kantor"
        else:
            return False, distance_rounded, f"Lokasi di luar jangkauan! Jarak {distance_rounded}m, maksimal {radius_meters}m"
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error validasi lokasi: {e}")
        return True, 0, f"Error validasi lokasi: {str(e)}"


# ==================== FACE DETECTION UTILITIES ====================

# Path ke Haar Cascade untuk deteksi wajah
CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
# Cascade alternatif untuk deteksi yang lebih toleran
CASCADE_ALT_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'

# Ukuran standar face crop untuk encoding (lebih besar = lebih detail)
FACE_SIZE = (160, 160)


def get_face_cascade():
    """Mengambil face cascade classifier"""
    return cv2.CascadeClassifier(CASCADE_PATH)


def get_face_cascade_alt():
    """Mengambil face cascade classifier alternatif (lebih toleran)"""
    return cv2.CascadeClassifier(CASCADE_ALT_PATH)


def image_to_array(image_file):
    """Konversi file gambar ke numpy array"""
    try:
        # Baca file gambar
        if hasattr(image_file, 'read'):
            image_data = image_file.read()
            image_file.seek(0)  # Reset pointer
        else:
            with open(image_file, 'rb') as f:
                image_data = f.read()
        
        # Konversi ke numpy array
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error konversi gambar: {e}")
        return None


def base64_to_array(base64_string):
    """Konversi base64 string ke numpy array"""
    try:
        # Hapus header data URI jika ada
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        image_data = base64.b64decode(base64_string)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error konversi base64: {e}")
        return None


def _preprocess_face(face_gray):
    """
    Preprocessing wajah untuk normalisasi pencahayaan dan kontras.
    Mengurangi pengaruh kondisi pencahayaan yang berbeda.
    """
    # CLAHE (Contrast Limited Adaptive Histogram Equalization)
    # Lebih baik dari equalizeHist biasa karena bekerja per-region
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(face_gray)
    
    # Gaussian blur ringan untuk mengurangi noise
    blurred = cv2.GaussianBlur(equalized, (3, 3), 0)
    
    return blurred


def detect_face(image):
    """
    Mendeteksi wajah dalam gambar dengan multi-cascade fallback.
    
    Strategi:
    1. Coba cascade default terlebih dahulu
    2. Jika gagal, coba cascade alternatif (lebih toleran)
    3. Crop wajah dengan padding 20% untuk menghindari noise dari leher/pakaian
    
    Returns: (face_image, face_rect) atau (None, None) jika tidak ada wajah
    """
    if image is None:
        return None, None
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Coba cascade default dulu
    face_cascade = get_face_cascade()
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80)  # Perkecil minimum agar lebih toleran jarak kamera
    )
    
    # Fallback ke cascade alternatif jika default gagal
    if len(faces) == 0:
        face_cascade_alt = get_face_cascade_alt()
        faces = face_cascade_alt.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(60, 60)
        )
    
    if len(faces) == 0:
        return None, None
    
    # Ambil wajah terbesar
    largest_face = max(faces, key=lambda f: f[2] * f[3])
    x, y, w, h = largest_face
    
    # Padding 20% — potong sedikit lebih lebar agar mencakup seluruh fitur wajah
    # tapi TIDAK mencakup baju/leher terlalu banyak
    pad_w = int(w * 0.15)
    pad_h_top = int(h * 0.2)    # Lebih banyak padding atas (dahi)
    pad_h_bottom = int(h * 0.05)  # Sedikit padding bawah (cukup sampai dagu)
    
    # Clamp ke batas gambar
    img_h, img_w = gray.shape
    x1 = max(0, x - pad_w)
    y1 = max(0, y - pad_h_top)
    x2 = min(img_w, x + w + pad_w)
    y2 = min(img_h, y + h + pad_h_bottom)
    
    # Crop dan preprocess
    face_img = gray[y1:y2, x1:x2]
    face_img = cv2.resize(face_img, FACE_SIZE)
    face_img = _preprocess_face(face_img)
    
    return face_img, largest_face


def _compute_lbph_histogram(face_img, grid_x=8, grid_y=8):
    """
    Hitung Local Binary Pattern Histogram (LBPH) manual.
    
    LBPH menganalisis POLA TEKSTUR LOKAL wajah — bukan brightness global.
    Ini membuatnya sangat tahan terhadap:
    - Perubahan pencahayaan
    - Perubahan pakaian
    - Perubahan latar belakang
    
    Cara kerja:
    1. Untuk setiap piksel, bandingkan dengan 8 tetangga
    2. Encode pola binary (lebih terang = 1, lebih gelap = 0)
    3. Hitung histogram per region grid
    4. Concatenate semua histogram
    """
    h, w = face_img.shape
    lbp_image = np.zeros_like(face_img, dtype=np.uint8)
    
    # Compute LBP untuk setiap piksel (kecuali border)
    for i in range(1, h - 1):
        for j in range(1, w - 1):
            center = face_img[i, j]
            code = 0
            # 8 tetangga searah jarum jam
            code |= (1 << 7) if face_img[i-1, j-1] >= center else 0
            code |= (1 << 6) if face_img[i-1, j]   >= center else 0
            code |= (1 << 5) if face_img[i-1, j+1] >= center else 0
            code |= (1 << 4) if face_img[i,   j+1] >= center else 0
            code |= (1 << 3) if face_img[i+1, j+1] >= center else 0
            code |= (1 << 2) if face_img[i+1, j]   >= center else 0
            code |= (1 << 1) if face_img[i+1, j-1] >= center else 0
            code |= (1 << 0) if face_img[i,   j-1] >= center else 0
            lbp_image[i, j] = code
    
    # Hitung histogram per grid region
    cell_h = h // grid_y
    cell_w = w // grid_x
    histograms = []
    
    for gy in range(grid_y):
        for gx in range(grid_x):
            cell = lbp_image[gy*cell_h:(gy+1)*cell_h, gx*cell_w:(gx+1)*cell_w]
            hist = cv2.calcHist([cell], [0], None, [256], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            histograms.append(hist)
    
    return np.concatenate(histograms)


def encode_face(image):
    """
    Generate encoding multi-strategy dari gambar wajah.
    
    Menyimpan 3 jenis encoding:
    1. lbph_histogram — pola tekstur lokal (robust, primary)
    2. histogram — distribusi kecerahan (fallback)
    3. descriptors — ORB feature keypoints (secondary)
    
    Returns: JSON string encoding atau None jika gagal
    """
    try:
        face_img, rect = detect_face(image)
        if face_img is None:
            return None
        
        # 1. LBPH Histogram — pola tekstur lokal (PRIMARY, paling robust)
        lbph_hist = _compute_lbph_histogram(face_img, grid_x=8, grid_y=8)
        
        # 2. Standard Histogram — distribusi kecerahan global
        hist = cv2.calcHist([face_img], [0], None, [256], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        
        # 3. ORB Features — titik kunci fitur wajah
        orb = cv2.ORB_create(nfeatures=200)
        keypoints, descriptors = orb.detectAndCompute(face_img, None)
        
        encoding = {
            'lbph_histogram': lbph_hist.tolist(),
            'histogram': hist.tolist(),
            'descriptors': descriptors.tolist() if descriptors is not None else None,
            'face_size': list(face_img.shape),
            'version': 2  # Marker versi encoding
        }
        
        return json.dumps(encoding)
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error encoding wajah: {e}")
        return None


def encode_face_from_file(image_file):
    """Encode wajah dari file upload"""
    img = image_to_array(image_file)
    if img is None:
        return None
    return encode_face(img)


def encode_face_from_base64(base64_string):
    """Encode wajah dari base64 string"""
    img = base64_to_array(base64_string)
    if img is None:
        return None
    return encode_face(img)


def compare_faces(encoding1_json, encoding2_json, threshold=0.45):
    """
    Membandingkan dua encoding wajah dengan multi-strategy scoring.
    
    Strategi perbandingan:
    - LBPH Histogram Correlation: 50% bobot (primary — paling robust)
    - Standard Histogram Correlation: 25% bobot (secondary)
    - ORB Feature Matching: 25% bobot (tertiary)
    
    Threshold diturunkan ke 0.45 (dari 0.65) karena multi-strategy scoring
    menghasilkan distribusi score yang lebih spread.
    
    Returns: (match: bool, confidence: float)
    """
    try:
        if not encoding1_json or not encoding2_json:
            return False, 0.0
        
        enc1 = json.loads(encoding1_json)
        enc2 = json.loads(encoding2_json)
        
        scores = []
        weights = []
        
        # === STRATEGY 1: LBPH Histogram Correlation (50% bobot) ===
        # Paling robust — tahan perubahan cahaya dan pakaian
        if enc1.get('lbph_histogram') and enc2.get('lbph_histogram'):
            lbph1 = np.array(enc1['lbph_histogram'], dtype=np.float32)
            lbph2 = np.array(enc2['lbph_histogram'], dtype=np.float32)
            
            if len(lbph1) == len(lbph2):
                lbph_corr = cv2.compareHist(lbph1, lbph2, cv2.HISTCMP_CORREL)
                # Normalize: correlation range [-1, 1] → [0, 1]
                lbph_score = max(0, (lbph_corr + 1) / 2)
                scores.append(lbph_score)
                weights.append(0.50)
        
        # === STRATEGY 2: Standard Histogram Correlation (25% bobot) ===
        if enc1.get('histogram') and enc2.get('histogram'):
            hist1 = np.array(enc1['histogram'], dtype=np.float32)
            hist2 = np.array(enc2['histogram'], dtype=np.float32)
            
            correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            hist_score = max(0, correlation)
            scores.append(hist_score)
            weights.append(0.25)
        
        # === STRATEGY 3: ORB Feature Matching (25% bobot) ===
        desc_score = 0.3  # Default baseline
        if enc1.get('descriptors') and enc2.get('descriptors'):
            desc1 = np.array(enc1['descriptors'], dtype=np.uint8)
            desc2 = np.array(enc2['descriptors'], dtype=np.uint8)
            
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            try:
                matches = bf.match(desc1, desc2)
                if len(matches) > 0:
                    # Hitung good matches (distance < 60, lebih toleran)
                    good_matches = [m for m in matches if m.distance < 60]
                    total_possible = min(len(desc1), len(desc2))
                    desc_score = len(good_matches) / total_possible if total_possible > 0 else 0
                    desc_score = min(1.0, desc_score * 2)  # Scale up
            except Exception as e:
                logger.warning("Error tidak terduga: %s", e)
        
        scores.append(desc_score)
        weights.append(0.25)
        
        # === GABUNGKAN SCORE ===
        if not scores:
            return False, 0.0
        
        # Weighted average
        total_weight = sum(weights)
        confidence = sum(s * w for s, w in zip(scores, weights)) / total_weight
        confidence = max(0, min(1, confidence))
        
        return confidence >= threshold, confidence
        
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error comparing faces: {e}")
        return False, 0.0


def find_matching_karyawan(image, karyawan_list, threshold=0.45):
    """
    Mencari karyawan yang cocok dari gambar wajah.
    
    Strategi multi-foto:
    - Membandingkan input terhadap SEMUA foto wajah terdaftar per karyawan
    - Mengambil score TERBAIK dari semua foto (bukan rata-rata)
    - Ini memastikan cukup 1 foto yang match dari 3 foto terdaftar
    
    Args:
        image: numpy array gambar atau base64 string
        karyawan_list: QuerySet karyawan dengan foto_wajah_set
        threshold: minimum confidence untuk match (default: 0.45)
    Returns:
        (karyawan, confidence) atau (None, 0.0)
    """
    try:
        # Konversi image jika perlu
        if isinstance(image, str):
            img = base64_to_array(image)
        else:
            img = image
        
        if img is None:
            return None, 0.0
        
        # Encode wajah dari gambar input
        input_encoding = encode_face(img)
        if not input_encoding:
            return None, 0.0
        
        best_match = None
        best_confidence = 0.0
        
        # Loop semua karyawan dan wajah terdaftar
        for karyawan in karyawan_list:
            foto_wajah_list = karyawan.foto_wajah_set.filter(aktif=True)
            
            # Ambil score TERBAIK dari semua foto karyawan ini
            karyawan_best_score = 0.0
            
            for foto_wajah in foto_wajah_list:
                if foto_wajah.encoding:
                    match, confidence = compare_faces(
                        input_encoding, 
                        foto_wajah.encoding, 
                        threshold
                    )
                    
                    if confidence > karyawan_best_score:
                        karyawan_best_score = confidence
            
            # Gunakan score terbaik untuk karyawan ini
            if karyawan_best_score >= threshold and karyawan_best_score > best_confidence:
                best_match = karyawan
                best_confidence = karyawan_best_score
        
        return best_match, best_confidence
        
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error finding matching karyawan: {e}")
        return None, 0.0


def validate_face_exists(image):
    """
    Validasi apakah ada wajah di gambar
    Returns: (has_face: bool, face_rect: tuple or None)
    """
    if isinstance(image, str):
        img = base64_to_array(image)
    else:
        img = image
    
    if img is None:
        return False, None
    
    face_img, rect = detect_face(img)
    return face_img is not None, rect
