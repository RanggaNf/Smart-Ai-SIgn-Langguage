"""
MINI EVALUATION — Test model dengan data angka 0-4
Jalankan ini SEBELUM rekam semua gesture.
Tujuan: cek apakah sensor + pipeline sudah layak untuk training penuh.

Cara pakai:
  1. Pastikan folder datashet/angka/ sudah ada CSV angka 0-4
  2. Set DATA_PATH di bawah sesuai path Anda
  3. Jalankan: python mini_eval.py
  4. Baca laporan di akhir — ada rekomendasi lanjut atau tidak
"""

import os, sys, warnings
import numpy as np
import pandas as pd
from glob import glob
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
warnings.filterwarnings('ignore')

# ─── KONFIGURASI ──────────────────────────────────────────────────────────────
DATA_PATH   = r"C:\FOLDERKU\SmartGlove\datashet\angka"
GESTURES    = ['0', '1', '2', '3', '4']
WINDOW_SIZE = 80       # frame per sampel
MIN_REP     = 3        # minimal repetisi yang harus ada
OUTPUT_DIR  = r"C:\FOLDERKU\SmartGlove\mini_eval_output"
# ──────────────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 60)
print("   SMART GLOVE — MINI EVALUATION")
print("=" * 60)

# ─── 1. LOAD DATA ─────────────────────────────────────────────────────────────
print("\n[1/6] Loading data...")

FLEX_COLS = [f'flex{i}_L' for i in range(1,6)] + [f'flex{i}_R' for i in range(1,6)]
IMU_COLS  = ['accX_L','accY_L','accZ_L','gyroX_L','gyroY_L','gyroZ_L',
             'accX_R','accY_R','accZ_R','gyroX_R','gyroY_R','gyroZ_R']
ALL_COLS  = FLEX_COLS + IMU_COLS

all_data = []
report   = {}

for gesture in GESTURES:
    pattern = os.path.join(DATA_PATH, f"{gesture}_rep*.csv")
    files   = sorted(glob(pattern))

    if not files:
        # coba cari dengan nama folder atau prefix berbeda
        pattern2 = os.path.join(DATA_PATH, f"{gesture}*.csv")
        files    = sorted(glob(pattern2))

    report[gesture] = {'n_files': len(files), 'files': files, 'issues': []}

    if len(files) < MIN_REP:
        print(f"  ✗ Gesture '{gesture}': hanya {len(files)} file (minimal {MIN_REP})")
        report[gesture]['issues'].append(f"Hanya {len(files)} repetisi")
        continue

    print(f"  ✓ Gesture '{gesture}': {len(files)} file ditemukan")

    for fpath in files:
        try:
            df = pd.read_csv(fpath)
            # cek kolom yang ada
            missing = [c for c in ALL_COLS if c not in df.columns]
            if missing:
                report[gesture]['issues'].append(f"Kolom missing: {missing[:3]}")
                continue

            arr = df[ALL_COLS].values.astype(np.float32)

            # Padding atau truncate ke WINDOW_SIZE
            if len(arr) >= WINDOW_SIZE:
                arr = arr[-WINDOW_SIZE:]
            else:
                pad = np.zeros((WINDOW_SIZE - len(arr), arr.shape[1]))
                arr = np.vstack([pad, arr])

            all_data.append({'gesture': gesture, 'data': arr, 'file': fpath})
        except Exception as e:
            report[gesture]['issues'].append(f"Error baca file: {e}")

if not all_data:
    print("\n✗ Tidak ada data yang bisa diload!")
    print(f"  Pastikan CSV ada di: {DATA_PATH}")
    print(f"  Format nama file: 0_rep1_xxx.csv, 1_rep1_xxx.csv, dst")
    sys.exit(1)

print(f"\n  Total sampel loaded: {len(all_data)}")

# ─── 2. CEK KUALITAS SENSOR ───────────────────────────────────────────────────
print("\n[2/6] Cek kualitas sensor...")

sensor_stats = defaultdict(list)
zero_imu_count = 0
low_flex_range = defaultdict(list)

for item in all_data:
    arr = item['data']
    gesture = item['gesture']

    # Cek IMU — apakah ada yang semua nol
    accel_L = arr[:, 10:13]  # accX/Y/Z_L
    gyro_L  = arr[:, 13:16]
    accel_R = arr[:, 16:19]
    gyro_R  = arr[:, 19:22]

    if np.all(accel_L == 0) or np.all(gyro_L == 0):
        zero_imu_count += 1
        report[gesture]['issues'].append("IMU KIRI semua nol!")

    if np.all(accel_R == 0) or np.all(gyro_R == 0):
        zero_imu_count += 1
        report[gesture]['issues'].append("IMU KANAN semua nol!")

    # Cek range flex per sensor
    for i, col in enumerate(FLEX_COLS):
        col_data = arr[:, i]
        rng = col_data.max() - col_data.min()
        sensor_stats[col].append(rng)

        if rng < 0.05:  # range normalized < 5%
            low_flex_range[col].append(gesture)

print("\n  Range sensor flex (normalized 0-1):")
print(f"  {'Sensor':<15} {'Range min':>10} {'Range max':>10} {'Rata-rata':>10} {'Status'}")
print(f"  {'-'*60}")

flex_issues = []
for col in FLEX_COLS:
    ranges = sensor_stats[col]
    if not ranges:
        continue
    rmin, rmax, rmean = min(ranges), max(ranges), np.mean(ranges)
    if rmean < 0.05:
        status = "⚠ SANGAT SEMPIT"
        flex_issues.append(col)
    elif rmean < 0.15:
        status = "! Sempit"
    else:
        status = "✓ OK"
    print(f"  {col:<15} {rmin:>10.3f} {rmax:>10.3f} {rmean:>10.3f}   {status}")

if zero_imu_count > 0:
    print(f"\n  ⚠ WARNING: {zero_imu_count} file dengan IMU semua nol!")
    print(f"    Ini berarti MPU6050 tidak terinisialisasi saat rekam.")
else:
    print(f"\n  ✓ IMU: tidak ada yang nol")

# ─── 3. AUGMENTASI SEDERHANA ──────────────────────────────────────────────────
print("\n[3/6] Augmentasi data (5 rep → 25 sampel per gesture)...")

def augment(arr, n=4):
    results = [arr]
    for _ in range(n):
        aug = arr.copy()
        # gaussian noise
        aug += np.random.normal(0, 0.01, arr.shape).astype(np.float32)
        # magnitude scale
        scale = np.random.uniform(0.92, 1.08)
        aug *= scale
        # time warp ringan
        if np.random.random() > 0.5:
            factor = np.random.uniform(0.85, 1.15)
            old_len = arr.shape[0]
            new_len = int(old_len * factor)
            if new_len > 10:
                indices = np.linspace(0, old_len-1, new_len)
                warped  = np.array([np.interp(indices, np.arange(old_len), arr[:,j])
                                    for j in range(arr.shape[1])]).T
                if len(warped) >= WINDOW_SIZE:
                    aug = warped[-WINDOW_SIZE:].astype(np.float32)
                else:
                    pad = np.zeros((WINDOW_SIZE - len(warped), warped.shape[1]))
                    aug = np.vstack([pad, warped]).astype(np.float32)
        results.append(np.clip(aug, -5, 5))
    return results

X, y, gesture_names = [], [], []
label_map = {g: i for i, g in enumerate(GESTURES)}

for item in all_data:
    g = item['gesture']
    if g not in label_map:
        continue
    augmented = augment(item['data'], n=4)
    for arr in augmented:
        X.append(arr)
        y.append(label_map[g])
        gesture_names.append(g)

X = np.array(X, dtype=np.float32)
y = np.array(y, dtype=np.int32)
print(f"  Dataset: {X.shape} — {len(np.unique(y))} kelas")

# ─── 4. TRAINING MODEL MINI ───────────────────────────────────────────────────
print("\n[4/6] Training model mini...")

from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, classification_report, accuracy_score

# Flatten untuk model sederhana (bukan LSTM) agar cepat
X_flat = X.reshape(len(X), -1)

# Normalize
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_flat)

# K-Fold cross validation
kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
all_preds, all_true = [], []

try:
    from sklearn.ensemble import RandomForestClassifier
    clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)

    fold_accs = []
    for fold, (train_idx, test_idx) in enumerate(kf.split(X_scaled, y)):
        X_tr, X_te = X_scaled[train_idx], X_scaled[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]
        clf.fit(X_tr, y_tr)
        preds = clf.predict(X_te)
        acc = accuracy_score(y_te, preds)
        fold_accs.append(acc)
        all_preds.extend(preds)
        all_true.extend(y_te)
        print(f"  Fold {fold+1}: accuracy = {acc*100:.1f}%")

    mean_acc = np.mean(fold_accs)
    std_acc  = np.std(fold_accs)
    print(f"\n  Accuracy rata-rata: {mean_acc*100:.1f}% ± {std_acc*100:.1f}%")

except Exception as e:
    print(f"  Error training: {e}")
    sys.exit(1)

# ─── 5. CONFUSION MATRIX ──────────────────────────────────────────────────────
print("\n[5/6] Membuat laporan dan visualisasi...")

cm = confusion_matrix(all_true, all_preds)
gesture_labels = [GESTURES[i] for i in sorted(np.unique(all_true))]

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('Smart Glove — Mini Evaluation (Angka 0-4)', fontsize=14, fontweight='bold')

# Confusion matrix
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=gesture_labels, yticklabels=gesture_labels,
            ax=axes[0])
axes[0].set_title(f'Confusion Matrix\nAccuracy: {mean_acc*100:.1f}%')
axes[0].set_ylabel('Actual')
axes[0].set_xlabel('Predicted')

# Accuracy per gesture
per_class_acc = cm.diagonal() / cm.sum(axis=1)
colors = ['#27ae60' if a >= 0.8 else '#e67e22' if a >= 0.6 else '#e74c3c'
          for a in per_class_acc]
axes[1].bar(gesture_labels, per_class_acc * 100, color=colors, edgecolor='white')
axes[1].set_title('Accuracy per Gesture')
axes[1].set_ylabel('Accuracy (%)')
axes[1].set_ylim(0, 110)
axes[1].axhline(y=80, color='green', linestyle='--', alpha=0.5, label='Target 80%')
axes[1].axhline(y=60, color='orange', linestyle='--', alpha=0.5, label='Batas 60%')
axes[1].legend()
for i, (g, a) in enumerate(zip(gesture_labels, per_class_acc)):
    axes[1].text(i, a*100 + 2, f'{a*100:.0f}%', ha='center', fontsize=11, fontweight='bold')

plt.tight_layout()
out_path = os.path.join(OUTPUT_DIR, 'mini_eval_result.png')
plt.savefig(out_path, dpi=120, bbox_inches='tight')
plt.close()
print(f"  Grafik disimpan: {out_path}")

# ─── 6. LAPORAN AKHIR ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("   LAPORAN AKHIR — KEPUTUSAN LANJUT ATAU TIDAK")
print("=" * 60)

# Evaluasi per gesture
print("\nAccuracy per gesture:")
problem_gestures = []
for i, g in enumerate(gesture_labels):
    acc = per_class_acc[i] * 100
    if acc >= 80:
        status = "✓ BAIK"
    elif acc >= 60:
        status = "! Cukup — bisa lanjut tapi perlu lebih banyak data"
        problem_gestures.append(g)
    else:
        status = "✗ BURUK — ada masalah serius"
        problem_gestures.append(g)
    print(f"  Gesture '{g}': {acc:.0f}%  {status}")

print("\nIssue sensor yang ditemukan:")
has_issue = False
if zero_imu_count > 0:
    print(f"  ✗ IMU nol: {zero_imu_count} file — MPU6050 bermasalah saat rekam")
    has_issue = True
if flex_issues:
    print(f"  ! Flex range sempit: {flex_issues}")
    has_issue = True
for g, issues in report.items():
    if issues['issues']:
        for iss in set(issues['issues']):
            print(f"  ! Gesture '{g}': {iss}")
            has_issue = True
if not has_issue:
    print("  ✓ Tidak ada issue sensor yang ditemukan")

print("\n" + "─" * 60)
print("KEPUTUSAN:")

if mean_acc >= 0.80 and not flex_issues and zero_imu_count == 0:
    print("""
  ✓ AMAN LANJUT REKAM SEMUA GESTURE

  Accuracy {:.0f}% dengan hanya 5 gesture dan data minimal.
  Sensor dan pipeline bekerja dengan baik.
  Lanjutkan rekam semua gesture sesuai daftar.
""".format(mean_acc*100))

elif mean_acc >= 0.60:
    print("""
  ! LANJUT DENGAN CATATAN

  Accuracy {:.0f}% — cukup tapi ada ruang perbaikan.
  Rekomendasi:
    - Rekam 5 repetisi penuh untuk setiap gesture (jangan kurang)
    - Perhatikan konsistensi posisi tangan saat rekam
    - Gesture yang accuracy-nya rendah: {}
    - Setelah semua terekam, accuracy akan naik karena lebih banyak data
""".format(mean_acc*100, problem_gestures if problem_gestures else "tidak ada"))

else:
    print("""
  ✗ ADA MASALAH SERIUS — JANGAN LANJUT DULU

  Accuracy {:.0f}% terlalu rendah.
  Kemungkinan penyebab:
    - Data rekaman tidak konsisten antar repetisi
    - IMU tidak terbaca (semua nol) saat rekam
    - Posisi tangan sangat berbeda antar repetisi
  
  Yang perlu dilakukan:
    1. Cek file CSV — buka di Excel, lihat apakah IMU ada nilainya
    2. Rekam ulang gesture angka dengan posisi lebih konsisten
    3. Pastikan MPU6050 sudah OK sebelum rekam (lihat Serial Monitor)
""".format(mean_acc*100))

if flex_issues:
    print(f"""  Sensor flex bermasalah: {flex_issues}
  Range sangat sempit — pertimbangkan solusi yang sudah dibahas.
""")

print("=" * 60)
print(f"Output disimpan di: {OUTPUT_DIR}")
print("=" * 60)