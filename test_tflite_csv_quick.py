"""
Smart Glove — TFLite Quick Test (Versi Sederhana)
==================================================
Versi simpel untuk quick testing dengan output ringkas.
"""

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
import sys

try:
    from tensorflow import lite
except ImportError:
    print("ERROR: TensorFlow tidak terinstall! pip install tensorflow")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────────────────────────────────────

MODEL_TFLITE = r"C:\FOLDERKU\SmartGlove\Model_Final\gesture_model_f32.tflite"
METADATA = r"C:\FOLDERKU\SmartGlove\Model_Final\model_metadata.json"
TEST_CSV_DIR = r"C:\FOLDERKU\SmartGlove\test_csv"
WINDOW_SIZE = 80

SENSOR_COLS = [
    'flex1_L', 'flex2_L', 'flex3_L', 'flex4_L', 'flex5_L',
    'accX_L', 'accY_L', 'accZ_L', 'gyroX_L', 'gyroY_L', 'gyroZ_L',
    'flex1_R', 'flex2_R', 'flex3_R', 'flex4_R', 'flex5_R',
    'accX_R', 'accY_R', 'accZ_R', 'gyroX_R', 'gyroY_R', 'gyroZ_R',
]

# ─────────────────────────────────────────────────────────────────────────────
# FUNGSI PREPROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_window(raw, scaler_mean, scaler_scale, window_size):
    """Convert raw sensor (T, 22) → (window_size, 66) dengan features."""
    # Normalize
    normed = (raw - scaler_mean) / (scaler_scale + 1e-7)
    
    # Delta
    delta = np.zeros_like(normed)
    delta[1:] = normed[1:] - normed[:-1]
    
    # Acceleration
    accel = np.zeros_like(normed)
    accel[1:] = delta[1:] - delta[:-1]
    
    # Combine
    combined = np.concatenate([normed, delta, accel], axis=1)
    
    # Pad jika perlu
    if len(combined) < window_size:
        pad = np.zeros((window_size - len(combined), combined.shape[1]))
        combined = np.vstack([combined, pad])
    elif len(combined) > window_size:
        combined = combined[-window_size:]
    
    return combined.astype(np.float32)


def predict(interpreter, X):
    """Prediksi dengan TFLite."""
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    
    X = X[np.newaxis, :].astype(input_detail['dtype'])
    interpreter.set_tensor(input_detail['index'], X)
    interpreter.invoke()
    
    output = interpreter.get_tensor(output_detail['index'])[0]
    gesture_id = np.argmax(output)
    confidence = float(output[gesture_id])
    
    return gesture_id, confidence


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("🚀 Loading model...")
    
    # Load metadata
    with open(METADATA) as f:
        meta = json.load(f)
    
    gesture_labels = meta["gesture_labels"]
    scaler_mean = np.array(meta["scaler"]["mean"])
    scaler_scale = np.array(meta["scaler"]["scale"])
    
    # Load TFLite
    interpreter = lite.Interpreter(model_path=MODEL_TFLITE)
    interpreter.allocate_tensors()
    
    print(f"✓ Model: {len(gesture_labels)} gestures")
    print(f"✓ Scaler: mean={len(scaler_mean)}, scale={len(scaler_scale)}")
    
    # Test loop
    print(f"\n📁 Testing CSV files from: {TEST_CSV_DIR}\n")
    
    total_correct = 0
    total_tests = 0
    
    for category in sorted(os.listdir(TEST_CSV_DIR)):
        cat_path = os.path.join(TEST_CSV_DIR, category)
        if not os.path.isdir(cat_path):
            continue
        
        print(f"\n📂 {category.upper()}")
        print("─" * 50)
        
        for csv_file in sorted(os.listdir(cat_path)):
            if not csv_file.endswith('.csv'):
                continue
            
            # Extract true label dari filename
            true_label = csv_file.split('_rep')[0].lower()
            
            # Load CSV
            csv_path = os.path.join(cat_path, csv_file)
            df = pd.read_csv(csv_path)
            raw = df[SENSOR_COLS].values.astype(np.float32)
            
            # Preprocess & predict
            X = preprocess_window(raw, scaler_mean, scaler_scale, WINDOW_SIZE)
            gesture_id, confidence = predict(interpreter, X)
            pred_label = gesture_labels[gesture_id].lower()
            
            # Check correctness
            is_correct = (pred_label == true_label)
            total_tests += 1
            if is_correct:
                total_correct += 1
            
            status = "✓" if is_correct else "✗"
            print(f"  {status} {csv_file:<40s} "
                  f"→ {pred_label:10s} (conf={confidence:.2f})")
    
    # Summary
    accuracy = total_correct / total_tests if total_tests > 0 else 0
    print(f"\n{'='*50}")
    print(f"ACCURACY: {total_correct}/{total_tests} = {accuracy*100:.1f}%")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
