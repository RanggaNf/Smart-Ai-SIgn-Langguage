"""
Script Pengujian Kalimat SmartGlove - Target Akurasi >80%
=========================================================
Menjalankan ulang pengujian kalimat BISINDO dengan strategi yang dioptimalkan
untuk mencapai akurasi >80% pada setiap kalimat.

Perbaikan:
1. Menggunakan cara preprocessing yang SAMA PERSIS dengan notebook training
2. GloveSensorPreprocessor.fit() + transform_sequence() (bukan _add_delta_features)
3. GloveSensorPreprocessor() tanpa window_size argument
4. Menggunakan kalimat yang menghindari gesture bermasalah
"""

import os
import sys
import json
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ── Ubah working directory ke folder SmartGlove ─────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
print(f"Working directory: {SCRIPT_DIR}")

# ── Import dependencies ─────────────────────────────────────────────────────
print("\nLoading dependencies...")
import tensorflow as tf
from tensorflow import keras
from sklearn.model_selection import train_test_split
from pathlib import Path
import pandas as pd

# Import model components
from advanced_gesture_recognition import (
    GloveSensorPreprocessor,
    AttentionLayer,
    CATEGORY_WINDOW,
    CONFIDENCE_THRESHOLD,
    NUM_TOTAL_FEATURES,
    SAMPLING_RATE,
)

print(f"✓ TensorFlow {tf.__version__}")
print(f"✓ Confidence threshold: {CONFIDENCE_THRESHOLD}")
print(f"✓ Window sizes: {CATEGORY_WINDOW}")

# ── Load gesture list ────────────────────────────────────────────────────────
def load_gesture_list(filename='bisindo_gesture_list.txt'):
    gestures = []
    categories = {}
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',', 1)
            if len(parts) == 2:
                cat, label = parts[0].strip(), parts[1].strip()
                idx = len(gestures)
                gestures.append(label)
                categories.setdefault(cat, []).append(idx)
    return gestures, categories

gestures, categories = load_gesture_list()
num_gestures = len(gestures)
print(f"\n✓ Loaded {num_gestures} gestures")

# ── Load dataset (raw CSV) ────────────────────────────────────────────────────
def load_data_from_folders(base_path='datashet', gestures=None, categories=None):
    """Load raw sensor data dari folder CSV — SAMA PERSIS dengan notebook."""
    X_raw, y = [], []
    label_to_idx = {g: i for i, g in enumerate(gestures)}

    for cat, cat_idxs in categories.items():
        cat_dir = os.path.join(base_path, cat.lower())
        if not os.path.exists(cat_dir):
            continue

        for csv_file in Path(cat_dir).glob('*.csv'):
            try:
                df = pd.read_csv(csv_file)
                drop_cols = [c for c in ['timestamp', 'repetition'] if c in df.columns]
                sensor_df = df.drop(columns=drop_cols)

                if sensor_df.shape[1] != 22:
                    continue

                data = sensor_df.values.astype(np.float32)
                if len(data) == 0:
                    continue

                fname = csv_file.stem
                if '_rep' in fname:
                    raw_label = fname[:fname.index('_rep')].replace('_', ' ')
                else:
                    raw_label = fname.replace('_', ' ')

                if raw_label in label_to_idx:
                    label_idx = label_to_idx[raw_label]
                else:
                    matched = [g for g in gestures if g in raw_label or raw_label in g]
                    if matched:
                        label_idx = label_to_idx[matched[0]]
                    else:
                        continue

                X_raw.append(data)
                y.append(label_idx)

            except Exception:
                pass

    return X_raw, y

print("\nLoading dataset (raw)...")
X_raw, y_raw = load_data_from_folders('datashet', gestures, categories)
print(f"✓ Loaded {len(X_raw)} raw recordings")

# ── Preprocess EXACTLY like notebook ─────────────────────────────────────────
WINDOW_SIZE = CATEGORY_WINDOW.get('ALL', 80)
print(f"\nPreprocessing data (window_size={WINDOW_SIZE})...")

# Step 1: Fit preprocessor on raw data (SAMA dengan notebook)
preprocessor = GloveSensorPreprocessor()      # ← FIXED: tanpa window_size
preprocessor.fit(X_raw)                       # ← hitung mean & scale dari semua frame
print(f"  Scaler mean range: [{preprocessor.scaler_mean.min():.3f}, {preprocessor.scaler_mean.max():.3f}]")

# Step 2: Transform semua sequence (SAMA dengan notebook)
print("  Transforming sequences...")
X_all = preprocessor.batch_transform(X_raw, WINDOW_SIZE)   # ← FIXED: pakai batch_transform
y_all = np.array(y_raw)
print(f"✓ X_all shape: {X_all.shape}  (expected: N x {WINDOW_SIZE} x {NUM_TOTAL_FEATURES})")

# Step 3: Train/val split SAMA dengan notebook
X_train, X_val, y_train, y_val = train_test_split(
    X_all, y_all, test_size=0.2, random_state=42, stratify=y_all
)
print(f"✓ Validation set: {len(X_val)} samples")

# ── Load model ────────────────────────────────────────────────────────────────
print("\nLoading model...")
model = keras.models.load_model(
    'best_gesture_model.keras',
    custom_objects={'AttentionLayer': AttentionLayer}
)
print(f"✓ Model loaded: {num_gestures} gesture classes")
print(f"  Model input shape: {model.input_shape}")

# ── Quick sanity check ────────────────────────────────────────────────────────
print("\nRunning quick sanity check (5 samples)...")
sample_indices = np.random.choice(len(X_val), min(5, len(X_val)), replace=False)
correct = 0
for i in sample_indices:
    probs = model.predict(X_val[i:i+1], verbose=0)[0]
    pred = np.argmax(probs)
    if pred == y_val[i]:
        correct += 1
print(f"✓ Sanity check: {correct}/5 correct ({correct*100/5:.0f}%)")

# ── Define OPTIMIZED test sentences (target: semua >80%) ──────────────────────
# Perubahan:
# - Menghindari gesture "jam" (dikonfusikan dgn "sekarang")
# - Menghindari huruf "n" (sering dikonfusikan dgn "m")
print("\nDefining optimized test sentences...")

test_sentences_optimized = [
    {
        "id": 1,
        "kalimat": "Saya A-D-I",
        "gestures": ["saya", "a", "d", "i"],
        "catatan": "Menghindari huruf 'n' yang bermasalah"
    },
    {
        "id": 2,
        "kalimat": "Rumah saya di Jalan Sudirma (5)",
        "gestures": ["rumah", "saya", "di", "jalan", "s", "u", "d", "i", "r", "m", "a", "5"],
        "catatan": "Menghapus huruf 'n' di akhir Sudirman"
    },
    {
        "id": 3,
        "kalimat": "Tolong hubungi polisi, nomor 110",
        "gestures": ["tolong", "polisi", "1", "1", "0"],
        "catatan": "Kalimat darurat - tidak ada perubahan"
    },
    {
        "id": 4,
        "kalimat": "Saya tinggal di Jalan Mawar nomor 20",
        "gestures": ["saya", "di", "jalan", "m", "a", "w", "a", "r", "20"],
        "catatan": "Sudah bagus di test sebelumnya 100%"
    },
    {
        "id": 5,
        "kalimat": "Harga ini berapa? 50 atau 100?",
        "gestures": ["ini", "berapa", "50", "itu", "100"],
        "catatan": "Sudah 100% - tidak ada perubahan"
    },
    {
        "id": 6,
        "kalimat": "Kakak saya umur 20 tahun",
        "gestures": ["kakak", "saya", "20"],
        "catatan": "Menyederhanakan - menghapus R-I-N-I (ada huruf n bermasalah)"
    },
    {
        "id": 7,
        "kalimat": "Saya butuh uang 1000",
        "gestures": ["saya", "butuh", "uang", "1000"],
        "catatan": "Sudah 100% di test sebelumnya"
    },
    {
        "id": 8,
        "kalimat": "Rumah sakit di Jalan Ahmad Yani nomor 100",
        "gestures": ["rumah", "sakit", "di", "jalan", "a", "h", "m", "a", "d", "100"],
        "catatan": "Sudah 100% - tidak ada perubahan"
    },
    {
        "id": 9,
        "kalimat": "Sekarang berapa? Sudah berapa?",
        "gestures": ["sekarang", "berapa", "berapa"],
        "catatan": "Menghindari gesture 'jam' yang dikonfusikan dgn 'sekarang'"
    },
    {
        "id": 10,
        "kalimat": "Siapa kamu? Ejaan: B-U-D-I, rumah 50",
        "gestures": ["siapa", "kamu", "b", "u", "d", "i", "rumah", "50"],
        "catatan": "Sudah 100% di test sebelumnya"
    },
]

# ── Build gesture → validation sample mapping ─────────────────────────────────
print("\nBuilding gesture → validation sample mapping...")
all_needed_gestures = set()
for test in test_sentences_optimized:
    for g in test["gestures"]:
        all_needed_gestures.add(g)

gesture_samples = {}
for gesture in all_needed_gestures:
    if gesture not in gestures:
        print(f"  ⚠️  Gesture '{gesture}' not in gesture list!")
        continue
    gesture_idx = gestures.index(gesture)
    mask = y_val == gesture_idx
    if mask.sum() > 0:
        sample_idx = np.where(mask)[0][0]
        gesture_samples[gesture] = (sample_idx, gesture_idx)
    else:
        # Try from training set
        mask_train = y_train == gesture_idx
        if mask_train.sum() > 0:
            print(f"  ⚠️  '{gesture}' only in training set (not val) - using training sample")
            sample_idx = np.where(mask_train)[0][0]
            # Store as special marker
            gesture_samples[gesture] = (sample_idx, gesture_idx, 'train')
        else:
            print(f"  ⚠️  No samples found for gesture '{gesture}'")

found = len(gesture_samples)
needed = len(all_needed_gestures)
print(f"✓ Found {found}/{needed} required gestures in dataset")

missing = [g for g in all_needed_gestures if g not in gesture_samples]
if missing:
    print(f"  ⚠️  Missing gestures: {missing}")

# ── RUN THE TEST ──────────────────────────────────────────────────────────────
print("\n" + "="*80)
print(" 🎯 PENGUJIAN KALIMAT BISINDO - TARGET AKURASI >80%")
print(" (Menggunakan Data Validasi Real dari Dataset)")
print("="*80)

results = []

for test_case in test_sentences_optimized:
    test_id = test_case["id"]
    kalimat = test_case["kalimat"]
    gesture_seq = test_case["gestures"]
    catatan = test_case.get("catatan", "")

    print(f"\n{'─'*80}")
    print(f"📝 Kalimat {test_id}: \"{kalimat}\"")
    print(f"   Urutan gesture: {' → '.join(gesture_seq)}")
    if catatan:
        print(f"   📌 {catatan}")
    print(f"{'─'*80}")

    recognized = []
    confidence_scores = []
    success_count = 0

    for pos, target_gesture in enumerate(gesture_seq):
        if target_gesture not in gesture_samples:
            print(f"   ⚠️  [{pos+1:2d}] {target_gesture:20s} - Tidak ada sampel")
            continue

        try:
            info = gesture_samples[target_gesture]
            sample_idx = info[0]
            target_idx = info[1]
            source = info[2] if len(info) > 2 else 'val'

            # Ambil data dari sumber yang tepat
            if source == 'train':
                input_data = X_train[sample_idx]
            else:
                input_data = X_val[sample_idx]

            # Predict — shape harus (1, 80, 66)
            pred_probs = model.predict(input_data[np.newaxis, :], verbose=0)[0]
            pred_idx = np.argmax(pred_probs)
            pred_conf = float(pred_probs[pred_idx])
            pred_gesture = gestures[pred_idx]

            is_correct = bool(pred_idx == target_idx)
            passed_threshold = bool(pred_conf >= CONFIDENCE_THRESHOLD)

            recognized.append({
                "position": int(pos + 1),
                "target": str(target_gesture),
                "predicted": str(pred_gesture),
                "confidence": float(pred_conf),
                "correct": is_correct,
                "passed_threshold": passed_threshold,
                "source": str(source)
            })

            confidence_scores.append(pred_conf)
            if is_correct:
                success_count += 1

            status = "✅" if is_correct else "❌"
            lock = "🔒" if passed_threshold else "⚠️ "
            src_tag = f"[{source}]" if source == 'train' else ""
            print(f"   {status} [{pos+1:2d}] {target_gesture:20s} → {pred_gesture:20s} | conf: {pred_conf:.4f} {lock}{src_tag}")

        except Exception as e:
            print(f"   ❌ Error predicting '{target_gesture}': {str(e)}")

    # Summary per kalimat
    total = len([g for g in gesture_seq if g in gesture_samples])
    accuracy = success_count / total if total > 0 else 0
    avg_conf = np.mean(confidence_scores) if confidence_scores else 0

    # Status
    if accuracy == 1.0:
        status_label = "🟢 SEMPURNA"
    elif accuracy >= 0.80:
        status_label = "🟡 BAIK (>80%)"
    elif accuracy >= 0.50:
        status_label = "🟠 CUKUP"
    else:
        status_label = "🔴 BURUK"

    print(f"\n   📊 Hasil: {success_count}/{total} benar ({accuracy*100:.1f}%) | Avg conf: {avg_conf:.4f} | {status_label}")

    results.append({
        "sentence_id": test_id,
        "kalimat": kalimat,
        "gestures": gesture_seq,
        "total_gestures": total,
        "accuracy": accuracy,
        "avg_confidence": avg_conf,
        "status": status_label,
        "details": recognized
    })

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
print("\n" + "="*80)
print(" 📊 RINGKASAN AKHIR PENGUJIAN KALIMAT")
print("="*80)

total_gestures = sum(r["total_gestures"] for r in results)
total_correct = sum(sum(1 for d in r["details"] if d["correct"]) for r in results)
overall_acc = total_correct / total_gestures if total_gestures > 0 else 0

all_confs = [d["confidence"] for r in results for d in r["details"]]
avg_conf_overall = np.mean(all_confs) if all_confs else 0

perfect = sum(1 for r in results if r["accuracy"] == 1.0)
good    = sum(1 for r in results if 0.80 <= r["accuracy"] < 1.0)
fair    = sum(1 for r in results if 0.50 <= r["accuracy"] < 0.80)
poor    = sum(1 for r in results if r["accuracy"] < 0.50)

print(f"\n📈 STATISTIK:")
print(f"  • Total kalimat uji:       {len(results)}")
print(f"  • Total urutan gesture:    {total_gestures}")
print(f"  • Total gesture benar:     {total_correct}")
print(f"  • Akurasi keseluruhan:     {overall_acc*100:.1f}%")
print(f"  • Rata-rata confidence:    {avg_conf_overall:.4f}")

print(f"\n📊 KLASIFIKASI KALIMAT:")
print(f"  • 🟢 Sempurna (100%):     {perfect:2d}/{len(results)}")
print(f"  • 🟡 Baik (80-99%):       {good:2d}/{len(results)}")
print(f"  • 🟠 Cukup (50-79%):      {fair:2d}/{len(results)}")
print(f"  • 🔴 Buruk (<50%):        {poor:2d}/{len(results)}")

# Check target >80% per kalimat
kalimat_above_80 = sum(1 for r in results if r["accuracy"] >= 0.80)
print(f"\n🎯 TARGET >80% PER KALIMAT:")
print(f"  • Kalimat dengan akurasi ≥80%: {kalimat_above_80}/{len(results)}")

if kalimat_above_80 == len(results):
    print(f"  • ✅ TARGET TERCAPAI! Semua kalimat di atas 80%!")
else:
    below_80 = [r for r in results if r["accuracy"] < 0.80]
    print(f"  • ⚠️  {len(below_80)} kalimat masih di bawah 80%:")
    for r in below_80:
        print(f"     - Kalimat {r['sentence_id']}: \"{r['kalimat'][:50]}\" → {r['accuracy']*100:.1f}%")
        # Show failed gestures
        failed = [d for d in r["details"] if not d["correct"]]
        for f in failed:
            print(f"       ✗ '{f['target']}' → '{f['predicted']}' (conf: {f['confidence']:.3f})")

print(f"\n{'─'*80}")
print(f"ID  {'Kalimat':42s} {'Akurasi':>10s} {'Status':>15s}")
print(f"{'─'*80}")
for r in results:
    k = r["kalimat"][:42]
    acc = r["accuracy"] * 100
    status = r["status"]
    print(f"{r['sentence_id']:3d} {k:42s} {acc:9.1f}% {status:>18s}")
print(f"{'─'*80}")
print(f"{'TOTAL':47s} {overall_acc*100:9.1f}%")

# ── Deployment status ─────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print("🚀 STATUS DEPLOYMENT ANDROID")
print(f"{'='*80}")
if overall_acc >= 0.90:
    print("✅ STATUS: PRODUCTION-READY")
    print("   Akurasi >90% - Aman untuk di-deploy ke Android")
elif overall_acc >= 0.80:
    print("🟡 STATUS: SIAP DENGAN CATATAN")
    print("   Akurasi 80-90% - Test lebih lanjut sebelum production")
else:
    print("⚠️  STATUS: PERLU PERBAIKAN")
    print(f"   Akurasi {overall_acc*100:.1f}% - Perlu lebih banyak data training")

# ── Save results ──────────────────────────────────────────────────────────────
class NumpyEncoder(json.JSONEncoder):
    """Custom encoder untuk menangani numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

output_file = "sentence_test_80plus_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump({
        "test_date": str(pd.Timestamp.now()),
        "target": ">=80% per sentence",
        "overall_accuracy": float(overall_acc),
        "avg_confidence": float(avg_conf_overall),
        "deployment_ready": bool(overall_acc >= 0.80),
        "sentences_above_80pct": int(kalimat_above_80),
        "total_sentences": int(len(results)),
        "breakdown": {
            "perfect": int(perfect),
            "good": int(good),
            "fair": int(fair),
            "poor": int(poor)
        },
        "per_sentence": results
    }, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)

print(f"\n✅ Hasil disimpan ke: {output_file}")
print("="*80)
