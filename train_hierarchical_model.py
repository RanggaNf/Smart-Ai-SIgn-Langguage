"""
GloveSpeak v3 — Hierarchical Gesture Recognition
================================================
Arsitektur:
  1. KATEGORI CLASSIFIER  (4 class: HURUF | ANGKA | KATA | FRASA)
  2. GESTURE CLASSIFIERS  (per kategori: 26, 15, 81, 14)

Keuntungan vs model monolitik (136 class):
  ✓ Setiap model kecil & specialized → akurasi lebih tinggi
  ✓ Confusion matrix 26x26 bukan 136x136 → mudah debug
  ✓ Inference cepat: hanya 2 inference (kategori + gesture)
  ✓ Realtime smart: kategori stable → switch gesture model
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings('ignore')
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════

SAMPLING_RATE = 100
NUM_RAW_FEATURES = 22
NUM_DELTA_FEATURES = 22
NUM_ACCEL_FEATURES = 22
NUM_FEATURES = NUM_RAW_FEATURES + NUM_DELTA_FEATURES + NUM_ACCEL_FEATURES  # 66

# Window size per kategori
WINDOW_SIZES = {
    'HURUF': 50,    # 500ms — gesture cepat
    'ANGKA': 50,    # 500ms
    'KATA': 70,     # 700ms — gesture lebih kompleks
    'FRASA': 120,   # 1200ms — gesture paling kompleks
    'KATEGORI': 80, # scanning window untuk kategori
}

print("=" * 80)
print("GloveSpeak v3 — Hierarchical Gesture Recognition")
print("=" * 80)
print()
print(f"Features per frame: {NUM_FEATURES} (raw 22 + delta 22 + accel 22)")
print(f"Window sizes: {WINDOW_SIZES}")
print()

# ═══════════════════════════════════════════════════════════════════════════
#  LOAD GESTURE LIST & DATA
# ═══════════════════════════════════════════════════════════════════════════

def load_gesture_list(filename='bisindo_gesture_list.txt'):
    gestures_global = []
    categories = {}
    label_to_idx = {}
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',', 1)
            if len(parts) == 2:
                cat, label = parts[0].strip(), parts[1].strip()
                idx = len(gestures_global)
                gestures_global.append(label)
                categories.setdefault(cat, []).append(idx)
                label_to_idx[label] = idx
    
    return gestures_global, categories, label_to_idx

gestures_global, categories, label_to_idx = load_gesture_list()
print(f"Total gestures: {len(gestures_global)}")
for cat, idxs in sorted(categories.items()):
    print(f"  {cat:10s}: {len(idxs):3d} gestures")
print()

# ─────────────────────────────────────────────────────────────────────────────
#  LOAD DATA PER KATEGORI
# ─────────────────────────────────────────────────────────────────────────────

def load_data_per_category(base_path='datashet', categories=None, label_to_idx=None):
    """
    Return: dict[category] -> {
        'X_raw': list of np.array,
        'y_local': list of local indices (0-25 untuk HURUF, 0-14 untuk ANGKA, etc),
        'y_global': list of global indices,
        'labels': list of label names,
        'label_to_idx': local mapping,
    }
    """
    data_per_cat = {}
    
    for cat, global_idxs in categories.items():
        cat_dir = os.path.join(base_path, cat.lower())
        if not os.path.exists(cat_dir):
            print(f"[WARN] Folder tidak ditemukan: {cat_dir}")
            continue
        
        # Build mapping untuk kategori ini
        cat_gestures = [gestures_global[i] for i in global_idxs]
        cat_label_to_local = {g: i for i, g in enumerate(cat_gestures)}
        
        X_raw, y_local, y_global, labels = [], [], [], []
        
        for csv_file in sorted(Path(cat_dir).glob('*.csv')):
            try:
                df = pd.read_csv(csv_file)
                drop_cols = [c for c in ['timestamp', 'repetition'] if c in df.columns]
                sensor_df = df.drop(columns=drop_cols)
                
                if sensor_df.shape[1] != 22:
                    continue
                
                data = sensor_df.values.astype(np.float32)
                if len(data) == 0:
                    continue
                
                # Parse label dari filename
                fname = csv_file.stem
                if '_rep' in fname:
                    raw_label = fname[:fname.index('_rep')].replace('_', ' ')
                else:
                    raw_label = fname.replace('_', ' ')
                
                if raw_label not in cat_label_to_local:
                    continue
                
                local_idx = cat_label_to_local[raw_label]
                global_idx = global_idxs[local_idx]
                
                X_raw.append(data)
                y_local.append(local_idx)
                y_global.append(global_idx)
                labels.append(raw_label)
            
            except Exception as e:
                print(f"[ERROR] {csv_file.name}: {e}")
        
        data_per_cat[cat] = {
            'X_raw': X_raw,
            'y_local': np.array(y_local),
            'y_global': np.array(y_global),
            'labels': labels,
            'label_to_idx': cat_label_to_local,
            'gestures': cat_gestures,
        }
        
        print(f"{cat:10s}: {len(X_raw)} recordings, {len(cat_gestures)} gestures")
    
    return data_per_cat

data_per_cat = load_data_per_category('datashet', categories, label_to_idx)
print()

# ═══════════════════════════════════════════════════════════════════════════
#  PREPROCESSOR
# ═══════════════════════════════════════════════════════════════════════════

class GloveSensorPreprocessor:
    """Preprocessing: normalize + delta + accel"""
    
    def __init__(self, scaler_mean=None, scaler_scale=None):
        self.scaler_mean = scaler_mean
        self.scaler_scale = scaler_scale
        self._fitted = scaler_mean is not None
    
    def fit(self, X_raw_list):
        all_frames = np.vstack(X_raw_list)
        self.scaler_mean = all_frames.mean(axis=0)
        self.scaler_scale = all_frames.std(axis=0) + 1e-7
        self._fitted = True
        return self
    
    def transform_sequence(self, raw, window_size):
        assert self._fitted, "Panggil fit() terlebih dahulu"
        raw = np.array(raw, dtype=np.float32)
        
        if len(raw) > window_size:
            raw = raw[-window_size:]
        
        normed = (raw - self.scaler_mean) / self.scaler_scale
        
        delta = np.zeros_like(normed)
        delta[1:] = normed[1:] - normed[:-1]
        
        accel = np.zeros_like(normed)
        accel[1:] = delta[1:] - delta[:-1]
        
        combined = np.concatenate([normed, delta, accel], axis=-1)
        
        if len(combined) < window_size:
            pad = np.zeros((window_size - len(combined), combined.shape[1]), dtype=np.float32)
            combined = np.concatenate([combined, pad], axis=0)
        
        return combined.astype(np.float32)
    
    def batch_transform(self, X_raw_list, window_size):
        return np.array([
            self.transform_sequence(seq, window_size) for seq in X_raw_list
        ], dtype=np.float32)
    
    def to_dict(self):
        return {
            'mean': self.scaler_mean.tolist(),
            'scale': self.scaler_scale.tolist(),
        }
    
    @classmethod
    def from_dict(cls, d):
        return cls(
            scaler_mean=np.array(d['mean'], dtype=np.float32),
            scaler_scale=np.array(d['scale'], dtype=np.float32),
        )

# Fit preprocessor global dari semua data
print("Fitting preprocessor...")
all_X_raw = []
for cat_data in data_per_cat.values():
    all_X_raw.extend(cat_data['X_raw'])

global_preprocessor = GloveSensorPreprocessor()
global_preprocessor.fit(all_X_raw)
print(f"Preprocessor fitted: mean shape {global_preprocessor.scaler_mean.shape}")
print()

# ═══════════════════════════════════════════════════════════════════════════
#  IMPORT MODEL BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

from advanced_gesture_recognition import (
    build_bilstm_attention_model,
    AttentionLayer,
)

# ═══════════════════════════════════════════════════════════════════════════
#  TRAINING SETUP
# ═══════════════════════════════════════════════════════════════════════════

def train_category_models(data_per_cat, global_preprocessor, WINDOW_SIZES):
    """
    Train:
    1. Kategori classifier (4 class)
    2. Gesture classifiers per kategori (26, 15, 81, 14)
    
    Return: dict berisi semua trained models
    """
    trained_models = {
        'preprocessor': global_preprocessor,
        'category_classifier': None,
        'gesture_classifiers': {},
        'window_sizes': WINDOW_SIZES,
    }
    
    # ─ Train Kategori Classifier ─────────────────────────────────────────────
    print("=" * 80)
    print("TRAINING KATEGORI CLASSIFIER (4 class)")
    print("=" * 80)
    
    X_cat_all, y_cat_all = [], []
    cat_list = sorted(data_per_cat.keys())
    cat_to_idx = {cat: i for i, cat in enumerate(cat_list)}
    
    for cat, cat_data in data_per_cat.items():
        X_raw = cat_data['X_raw']
        X_proc = global_preprocessor.batch_transform(X_raw, WINDOW_SIZES['KATEGORI'])
        y_cat = np.full(len(X_proc), cat_to_idx[cat])
        
        X_cat_all.append(X_proc)
        y_cat_all.append(y_cat)
    
    X_cat_all = np.vstack(X_cat_all)
    y_cat_all = np.concatenate(y_cat_all)
    
    X_cat_train, X_cat_val, y_cat_train, y_cat_val = train_test_split(
        X_cat_all, y_cat_all, test_size=0.2, random_state=42, stratify=y_cat_all
    )
    
    cat_model = build_bilstm_attention_model(
        num_gestures=4,
        window_size=WINDOW_SIZES['KATEGORI'],
        num_features=NUM_FEATURES,
        lstm_units=64,
        dense_units=64,
        dropout_rate=0.3,
    )
    
    cat_model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.0005),
        loss='sparse_categorical_crossentropy',
        metrics=['accuracy'],
    )
    
    cat_model.fit(
        X_cat_train, y_cat_train,
        validation_data=(X_cat_val, y_cat_val),
        epochs=60,
        batch_size=16,
        callbacks=[
            keras.callbacks.EarlyStopping('val_loss', patience=15, restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau('val_loss', factor=0.5, patience=5, min_lr=1e-7),
        ],
        verbose=0,
    )
    
    _, cat_acc = cat_model.evaluate(X_cat_val, y_cat_val, verbose=0)
    print(f"Kategori Classifier accuracy: {cat_acc*100:.2f}%")
    print()
    
    trained_models['category_classifier'] = cat_model
    trained_models['category_list'] = cat_list
    trained_models['cat_to_idx'] = cat_to_idx
    
    # ─ Train Gesture Classifiers per Kategori ────────────────────────────────
    print("=" * 80)
    print("TRAINING GESTURE CLASSIFIERS (per kategori)")
    print("=" * 80)
    print()
    
    for cat in cat_list:
        cat_data = data_per_cat[cat]
        num_gestures_cat = len(cat_data['gestures'])
        window_sz = WINDOW_SIZES.get(cat, WINDOW_SIZES['KATEGORI'])
        
        print(f"Training {cat} gesture classifier ({num_gestures_cat} class)...")
        
        # Preprocess
        X_raw = cat_data['X_raw']
        X_proc = global_preprocessor.batch_transform(X_raw, window_sz)
        y_local = cat_data['y_local']
        
        # Split
        X_train, X_val, y_train, y_val = train_test_split(
            X_proc, y_local, test_size=0.2, random_state=42, stratify=y_local
        )
        
        # Build & train
        gest_model = build_bilstm_attention_model(
            num_gestures=num_gestures_cat,
            window_size=window_sz,
            num_features=NUM_FEATURES,
            lstm_units=96,
            dense_units=96,
            dropout_rate=0.3,
        )
        
        gest_model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.0005),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'],
        )
        
        gest_model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=80,
            batch_size=16,
            callbacks=[
                keras.callbacks.EarlyStopping('val_loss', patience=15, restore_best_weights=True),
                keras.callbacks.ReduceLROnPlateau('val_loss', factor=0.5, patience=5, min_lr=1e-7),
            ],
            verbose=0,
        )
        
        _, gest_acc = gest_model.evaluate(X_val, y_val, verbose=0)
        print(f"  {cat:10s} accuracy: {gest_acc*100:5.2f}%")
        
        trained_models['gesture_classifiers'][cat] = {
            'model': gest_model,
            'gestures': cat_data['gestures'],
            'window_size': window_sz,
            'preprocessor': global_preprocessor,
        }
    
    print()
    return trained_models

# Train semua models
trained_models = train_category_models(data_per_cat, global_preprocessor, WINDOW_SIZES)

print("=" * 80)
print("Semua models sudah di-train!")
print("=" * 80)
print()

# ═══════════════════════════════════════════════════════════════════════════
#  SAVE MODELS
# ═══════════════════════════════════════════════════════════════════════════

print("Menyimpan models...")
os.makedirs('hierarchical_models', exist_ok=True)

# Save kategori classifier
trained_models['category_classifier'].save('hierarchical_models/category_classifier.keras')
print("✓ hierarchical_models/category_classifier.keras")

# Save gesture classifiers
for cat, info in trained_models['gesture_classifiers'].items():
    model = info['model']
    model.save(f'hierarchical_models/{cat.lower()}_gesture_model.keras')
    print(f"✓ hierarchical_models/{cat.lower()}_gesture_model.keras")

# Save metadata
metadata = {
    'version': '3.0',
    'architecture': 'hierarchical',
    'categories': trained_models['category_list'],
    'cat_to_idx': trained_models['cat_to_idx'],
    'window_sizes': WINDOW_SIZES,
    'num_features': NUM_FEATURES,
    'sampling_rate': SAMPLING_RATE,
    'preprocessor': global_preprocessor.to_dict(),
    'gesture_classifiers': {
        cat: {
            'num_gestures': len(info['gestures']),
            'gestures': info['gestures'],
            'window_size': info['window_size'],
        }
        for cat, info in trained_models['gesture_classifiers'].items()
    },
}

with open('hierarchical_models/metadata.json', 'w', encoding='utf-8') as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)
print("✓ hierarchical_models/metadata.json")

print()
print("=" * 80)
print("Training selesai! Models siap untuk realtime inference.")
print("=" * 80)
