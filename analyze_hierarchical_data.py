"""
Analisis Data Per-Kategori untuk Hierarchical Model
=====================================================
Persiapan: Lihat distribusi data huruf/angka/kata/frasa
"""

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

print("=" * 80)
print("ANALISIS DATA GESTURE HIERARCHICAL")
print("=" * 80)
print()

# Load gesture list
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

print("Gesture Categories:")
for cat, idxs in sorted(categories.items()):
    print(f"  {cat:10s}: {len(idxs):3d} gestures")
print()

# Scan data folder
data_stats = defaultdict(lambda: {'count': 0, 'total_frames': 0, 'seq_lengths': []})

base_path = 'datashet'
for cat, cat_idxs in categories.items():
    cat_dir = os.path.join(base_path, cat.lower())
    if not os.path.exists(cat_dir):
        print(f"[WARN] Folder tidak ditemukan: {cat_dir}")
        continue
    
    for csv_file in Path(cat_dir).glob('*.csv'):
        try:
            df = pd.read_csv(csv_file)
            drop_cols = [c for c in ['timestamp', 'repetition'] if c in df.columns]
            sensor_df = df.drop(columns=drop_cols)
            
            if sensor_df.shape[1] != 22:
                continue
            
            data_stats[cat.lower()]['count'] += 1
            data_stats[cat.lower()]['total_frames'] += len(df)
            data_stats[cat.lower()]['seq_lengths'].append(len(df))
        except Exception as e:
            print(f"[ERROR] {csv_file.name}: {e}")

print("Data Distribution per Kategori:")
print()
for cat in sorted(data_stats.keys()):
    stats = data_stats[cat]
    lengths = np.array(stats['seq_lengths'])
    print(f"{cat.upper():10s}:")
    print(f"  Recordings       : {stats['count']:3d}")
    print(f"  Total frames     : {stats['total_frames']:5d}")
    print(f"  Avg frames/rec   : {lengths.mean():.0f}")
    print(f"  Frame range      : {lengths.min():.0f} — {lengths.max():.0f}")
    print(f"  Median frames    : {np.median(lengths):.0f}")
    print()

# Analisis gesture per kategori
print("=" * 80)
print("GESTURE DISTRIBUTION (berapa recording per gesture)")
print("=" * 80)
print()

for cat, idxs in sorted(categories.items()):
    cat_dir = os.path.join(base_path, cat.lower())
    if not os.path.exists(cat_dir):
        continue
    
    gesture_counts = defaultdict(int)
    for csv_file in Path(cat_dir).glob('*.csv'):
        try:
            df = pd.read_csv(csv_file)
            sensor_df = df.drop(columns=[c for c in ['timestamp', 'repetition'] if c in df.columns])
            if sensor_df.shape[1] != 22:
                continue
            
            fname = csv_file.stem
            if '_rep' in fname:
                raw_label = fname[:fname.index('_rep')].replace('_', ' ')
            else:
                raw_label = fname.replace('_', ' ')
            
            gesture_counts[raw_label] += 1
        except:
            pass
    
    print(f"\n{cat.upper()} ({len(idxs)} gestures, {len(gesture_counts)} ditemukan):")
    sorted_counts = sorted(gesture_counts.items(), key=lambda x: -x[1])
    
    # Statistik
    counts_arr = np.array([c for _, c in sorted_counts])
    print(f"  Avg/gesture   : {counts_arr.mean():.1f} recordings")
    print(f"  Min/Max       : {counts_arr.min()}/{counts_arr.max()}")
    print(f"  Imbalance     : {counts_arr.std():.2f} std")
    
    # Top & bottom gestures
    print(f"  Top 3 (most recordings):")
    for g, c in sorted_counts[:3]:
        print(f"    {g:20s}: {c} recordings")
    
    if len(sorted_counts) > 3:
        print(f"  Bottom 3 (least recordings):")
        for g, c in sorted_counts[-3:]:
            print(f"    {g:20s}: {c} recordings")

print()
print("=" * 80)
print("KESIMPULAN")
print("=" * 80)
print("""
Strategi terbaik untuk model Anda:

1. KATEGORI CLASSIFIER
   - Input: data stream
   - Output: HURUF | ANGKA | KATA | FRASA
   - Arch: Lightweight (TCN atau BiLSTM kecil)

2. PER-KATEGORI GESTURE CLASSIFIER (4 models terpisah)
   - HURUF model    : 26 classes (a-z)
   - ANGKA model    : 10 classes (0-9) + puluhan
   - KATA model     : ~30-50 gesture (umum)
   - FRASA model    : ~30-50 gesture (umum)
   - Arch: Sama seperti notebook (BiLSTM + Attention)

3. REALTIME INFERENCE
   - Push frame → kategori classifier
   - Jika kategori stabil N frame → switch ke gesture classifier
   - Gesture classifier hanya handle kategori tsb
   - Output: kategori + gesture + confidence

Benefits:
✓ Akurasi lebih tinggi (specialized model)
✓ Confusion berkurang (hanya 10-50 class vs 136)
✓ Realtime lebih cepat (model kecil)
✓ Tidak perlu data baru
✓ Mudah debug (pisah per kategori)
""")
