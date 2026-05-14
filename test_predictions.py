"""
Smart Glove Keras Model - Test Data Prediction
===============================================
Memprediksi gesture dari file CSV test_csv menggunakan best_gesture_model.keras
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# TensorFlow quiet
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import tensorflow as tf
from tensorflow import keras

# Import custom layer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from advanced_gesture_recognition import AttentionLayer, GloveSensorPreprocessor

# ─────────────────────────────────────────────────────────────────────────────
#  LOAD MODEL & METADATA
# ─────────────────────────────────────────────────────────────────────────────

MODEL_PATH = r"best_gesture_model.keras"
METADATA_PATH = r"model_metadata.json"

print("=" * 80)
print("SMART GLOVE - KERAS MODEL PREDICTION")
print("=" * 80)
print()

# Load model
if not os.path.exists(MODEL_PATH):
    print(f"❌ Model tidak ditemukan: {MODEL_PATH}")
    sys.exit(1)

print(f"📦 Loading model: {MODEL_PATH}")
model = keras.models.load_model(MODEL_PATH, custom_objects={"AttentionLayer": AttentionLayer})
print(f"✓ Model loaded successfully!")
print(f"  Input shape: {model.input_shape}")
print(f"  Output shape: {model.output_shape}")
print()

# Load metadata & preprocessor
preprocessor = None
gesture_classes = {}

if os.path.exists(METADATA_PATH):
    with open(METADATA_PATH, 'r') as f:
        meta = json.load(f)
        
        # Get gesture labels
        if 'gesture_labels' in meta:
            gesture_classes = {i: label for i, label in enumerate(meta['gesture_labels'])}
        elif 'gesture_classes' in meta:
            gesture_classes = {int(k): v for k, v in meta.get("gesture_classes", {}).items()}
        
        # Load preprocessor from scaler
        if 'scaler' in meta:
            preprocessor = GloveSensorPreprocessor.from_dict(meta['scaler'])
            print(f"✓ Preprocessor loaded from metadata (scaler)")
        
        print(f"📋 Gesture classes ({len(gesture_classes)}):")
        for idx in sorted(gesture_classes.keys())[:10]:
            print(f"  {idx}: {gesture_classes[idx]}")
        if len(gesture_classes) > 10:
            print(f"  ... and {len(gesture_classes) - 10} more")
        print()
else:
    print(f"⚠️  Metadata tidak ditemukan. Menggunakan label numerik.")
    print()

if preprocessor is None:
    print(f"❌ Preprocessor tidak ditemukan! Tidak bisa melanjutkan prediksi.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
#  PREPROCESS DATA
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_csv(csv_path, window_size=80):
    """
    Baca CSV dan format untuk model input menggunakan preprocessor.
    Return: (data_windows, raw_df)
    
    Data columns:
    timestamp, flex1_L..5_L, accX_L, accY_L, accZ_L, gyroX_L, gyroY_L, gyroZ_L,
    flex1_R..5_R, accX_R, accY_R, accZ_R, gyroX_R, gyroY_R, gyroZ_R, repetition
    """
    df = pd.read_csv(csv_path)
    
    # Extract sensor features (skip timestamp & repetition)
    sensor_cols = [col for col in df.columns if col not in ['timestamp', 'repetition']]
    raw_data = df[sensor_cols].values.astype(np.float32)
    
    # Use preprocessor to transform
    # Preprocessing expects individual sequences, so we'll process them as windows
    
    # Transform the entire sequence and create windows
    transformed = preprocessor.transform_sequence(raw_data, len(raw_data) + 1000)[:len(raw_data)]
    
    # Create overlapping windows
    windows = []
    for start_idx in range(0, len(transformed) - window_size + 1, window_size // 2):
        window = transformed[start_idx:start_idx + window_size]
        if len(window) == window_size:
            windows.append(window)
    
    return np.array(windows), df, sensor_cols


# ─────────────────────────────────────────────────────────────────────────────
#  PREDICT & EVALUATE
# ─────────────────────────────────────────────────────────────────────────────

test_dir = Path("./test_csv")
csv_files = sorted(list(test_dir.glob("*.csv")))

if not csv_files:
    print(f"❌ Tidak ada file CSV di {test_dir}")
    sys.exit(1)

print(f"📂 Found {len(csv_files)} test files\n")

all_predictions = []
results_summary = []

for csv_file in csv_files:
    gesture_label = int(csv_file.name[0])  # Ambil dari nama file
    gesture_name = gesture_classes.get(gesture_label, f"Gesture {gesture_label}")
    
    print(f"\n{'─' * 80}")
    print(f"File: {csv_file.name} → Expected: {gesture_name}")
    print(f"{'─' * 80}")
    
    # Preprocess
    windows, raw_df, sensor_cols = preprocess_csv(csv_file)
    
    if len(windows) == 0:
        print(f"⚠️  Insufficient data (need 80+ samples)")
        continue
    
    print(f"  Data points: {len(raw_df)}")
    print(f"  Windows created: {len(windows)}")
    
    # Predict
    predictions = model.predict(windows, verbose=0)
    
    # Analysis
    if predictions.ndim == 2:
        # Multi-class output
        pred_classes = np.argmax(predictions, axis=1)
        pred_confidence = np.max(predictions, axis=1)
    else:
        # Binary output
        pred_classes = (predictions > 0.5).astype(int).flatten()
        pred_confidence = np.abs(predictions - 0.5).flatten() * 2
    
    # Majority voting
    majority_pred = np.bincount(pred_classes).argmax()
    majority_conf = np.mean(pred_confidence[pred_classes == majority_pred])
    
    # Statistics
    unique, counts = np.unique(pred_classes, return_counts=True)
    
    print(f"\n  Predictions per window:")
    for uc, count in zip(unique, counts):
        uc_name = gesture_classes.get(int(uc), f"Gesture {int(uc)}")
        pct = (count / len(windows)) * 100
        print(f"    {uc_name}: {count} ({pct:.1f}%)")
    
    final_pred_name = gesture_classes.get(int(majority_pred), f"Gesture {int(majority_pred)}")
    
    print(f"\n  ✓ Final prediction: {final_pred_name}")
    print(f"    Confidence: {majority_conf:.2%}")
    print(f"    Match: {'✓ CORRECT' if majority_pred == gesture_label else '✗ INCORRECT'}")
    
    # Store results
    all_predictions.append({
        'file': csv_file.name,
        'expected': int(gesture_label),
        'predicted': int(majority_pred),
        'confidence': float(majority_conf),
        'correct': bool(majority_pred == gesture_label),
        'windows': len(windows)
    })
    
    results_summary.append({
        'File': csv_file.name,
        'Expected': gesture_name,
        'Predicted': final_pred_name,
        'Confidence': f"{majority_conf:.1%}",
        'Result': '✓' if majority_pred == gesture_label else '✗'
    })

# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n\n{'=' * 80}")
print("PREDICTION SUMMARY")
print(f"{'=' * 80}\n")

summary_df = pd.DataFrame(results_summary)
print(summary_df.to_string(index=False))

# Overall stats
correct = sum(1 for p in all_predictions if p['correct'])
total = len(all_predictions)
accuracy = (correct / total * 100) if total > 0 else 0

print(f"\n{'─' * 80}")
print(f"Accuracy: {correct}/{total} ({accuracy:.1f}%)")
print(f"{'─' * 80}")

# Save detailed results
output_file = "test_predictions.json"
with open(output_file, 'w') as f:
    results = {
        'timestamp': datetime.now().isoformat(),
        'model': MODEL_PATH,
        'total_files': int(total),
        'correct': int(correct),
        'accuracy': float(accuracy),
        'predictions': [
            {k: (int(v) if isinstance(v, (bool, np.bool_)) else v) for k, v in p.items()}
            for p in all_predictions
        ]
    }
    json.dump(results, f, indent=2)

print(f"\n💾 Detailed results saved to: {output_file}")
print(f"\n{'=' * 80}")
print("Prediction complete!")
print(f"{'=' * 80}")
