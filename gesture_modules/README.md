# Gesture Modules — GloveSpeak Core Library

Folder ini menyimpan **semua modul dependensi** untuk SmartGlove gesture recognition system.

## Struktur

```
gesture_modules/
├── advanced_gesture_recognition.py  # Model & inference engine utama
├── sensor_augmentation.py           # Data augmentation (8 teknik)
└── README.md                        # File ini
```

## File-File

### 1. `advanced_gesture_recognition.py` (~850 lines)

**Komponen Utama:**

- `AttentionLayer` — Custom Keras layer (Bahdanau attention)
- `build_bilstm_attention_model()` — Model BiLSTM + Self-Attention (rekomendasi)
- `build_tcn_model()` — Model TCN (Temporal Convolutional Network) — 3x lebih cepat
- `GloveSensorPreprocessor` — Normalisasi + delta + acceleration features
- `AdaptiveGestureSegmenter` — Deteksi gesture batas awal/akhir (adaptive threshold)
- `GrammarPostprocessor` — Post-process prediksi → kalimat TTS
- `RealtimeInferenceEngine` — Sliding window inference untuk realtime
- `ProductionInferenceEngine` — Wrapper offline testing dengan model file

**Konstanta:**

```python
SAMPLING_RATE = 100              # Hz (sensor sampling rate ESP32)
NUM_TOTAL_FEATURES = 66          # raw(22) + delta(22) + accel(22)
CATEGORY_WINDOW = {              # per-kategori (frames @ 100Hz)
    'HURUF': 50,    # 500ms
    'ANGKA': 50,
    'KATA':  70,    # 700ms
    'FRASA': 120,   # 1200ms
    'ALL':   80,    # universal single model
}
CONFIDENCE_THRESHOLD = 0.72      # min probabilitas valid prediksi
STABILITY_WINDOW = 3             # gesture harus konsisten 3x frame
INFERENCE_STRIDE = 15            # prediksi setiap 150ms
```

### 2. `sensor_augmentation.py` (~450 lines)

**Teknik Augmentasi (8 per sample):**

1. `gaussian_noise()` — Noise SNR 28dB (halus)
2. `gaussian_noise()` — Noise SNR 18dB (keras)
3. `magnitude_scale()` — 0.88x amplitudo
4. `magnitude_scale()` — 1.12x amplitudo
5. `time_warp()` — 0.90x kecepatan (cepat)
6. `time_warp()` — 1.10x kecepatan (lambat)
7. `combo_noise_scale()` — Noise + scale
8. `_full_augment()` — Kombinasi semua teknik

**Augmentor Utama:**

- `SensorDataAugmenter` — Main class untuk augmentasi
  - `augment_one()` — 8 augmentasi dari 1 sequence
  - `augment_dataset()` — Augmentasi seluruh dataset (~9x)
  - `augment_balanced()` — Augmentasi dengan target per-class yang seimbang
- `validate_augmentation()` — Validasi visual augmentasi

**Result:** 5 rekaman × 9 (original+aug) = **45 sampel per gesture**

## Cara Import

### Dari notebook/script di root SmartGlove:

**Setup awal (di cell pertama):**
```python
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'gesture_modules'))
```

**Kemudian import normal:**
```python
from advanced_gesture_recognition import (
    build_bilstm_attention_model,
    GloveSensorPreprocessor,
    RealtimeInferenceEngine,
    AttentionLayer,
    CATEGORY_WINDOW,
    CONFIDENCE_THRESHOLD,
    NUM_TOTAL_FEATURES,
    SAMPLING_RATE,
)
from sensor_augmentation import SensorDataAugmenter, validate_augmentation
```

## Workflow Tipikal

### 1. Load Data

```python
from gesture_modules import GloveSensorPreprocessor
X_raw, y = load_data_from_folders('datashet', gestures, categories)
```

### 2. Augmentasi (5 rep → 45 sampel)

```python
from gesture_modules import SensorDataAugmenter
augmenter = SensorDataAugmenter(seed=42)
X_aug, y_aug = augmenter.augment_balanced(X_raw, y, target_per_class=45)
```

### 3. Preprocessing

```python
from gesture_modules import GloveSensorPreprocessor
preprocessor = GloveSensorPreprocessor()
preprocessor.fit(X_aug)
X_processed = preprocessor.batch_transform(X_aug, window_size=80)
```

### 4. Build & Train Model

```python
from gesture_modules import build_bilstm_attention_model
model = build_bilstm_attention_model(
    num_gestures=len(gestures),
    window_size=80,
    num_features=66,
    lstm_units=128,
    dropout_rate=0.35,
)
model.compile(...)
model.fit(X_train, y_train, ...)
```

### 5. Realtime Inference (simulasi/testing)

```python
from gesture_modules import RealtimeInferenceEngine, AdaptiveGestureSegmenter

segmenter = AdaptiveGestureSegmenter()
segmenter.calibrate(first_30_frames)

engine = RealtimeInferenceEngine(
    model=model,
    preprocessor=preprocessor,
    segmenter=segmenter,
    gesture_labels=gestures,
    window_size=80,
)

# Push frame satu-satu (simulasi ESP32 UDP)
for frame in sensor_stream:
    engine.push_frame(frame, timestamp_ms=t)
```

## Catatan Penting

- **Post-Padding:** Model menggunakan post-padding (nol di akhir), bukan pre-padding
- **Delta + Acceleration:** 22 raw → 66 features (raw + Δ + ΔΔ)
- **Adaptive Segmenter:** Threshold otomatis berdasarkan baseline kalibrasi
- **Confidence Gating:** No output saat tangan diam (energy < threshold)
- **Stability Check:** Gesture harus konsisten 3x prediksi berturut-turut
- **Android Ready:** TFLite int8 quantization siap pakai di Kotlin

## Kompatibilitas

✓ Python 3.8+ (tensorflow 2.10+)
✓ NumPy, Pandas, Scikit-learn
✓ TensorFlow Keras (dari `tensorflow.keras`)
✓ Folder standalone — tidak perlu package initialization
✓ Direct import dari file modul menggunakan `sys.path.insert()`

---

**Version:** 2.0.0  
**Last Update:** 2026-04-06  
**Author:** GloveSpeak Team
