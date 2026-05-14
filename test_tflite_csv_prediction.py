"""
Smart Glove — TFLite Model Testing dengan Data CSV
====================================================
Script untuk menguji prediksi model TFLite menggunakan data CSV dari test_csv folder.

Fitur:
- Preprocessing data: raw features + delta + acceleration
- Prediksi per window (sliding window)
- Evaluasi akurasi per kategori
- Detail hasil prediksi per file

Requirements:
- tensorflow (untuk TFLite interpreter)
- numpy
- pandas
- scikit-learn
"""

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
from typing import Dict, List, Tuple

# TFLite interpreter
try:
    import tensorflow as tf
    from tensorflow import lite
except ImportError:
    print("ERROR: TensorFlow tidak terinstall!")
    print("Install dengan: pip install tensorflow")
    sys.exit(1)

# ═════════════════════════════════════════════════════════════════════════════
# KONFIGURASI
# ═════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "model_path": r"C:\FOLDERKU\SmartGlove\Model_Final\gesture_model_f32.tflite",
    "metadata_path": r"C:\FOLDERKU\SmartGlove\Model_Final\model_metadata.json",
    "test_csv_dir": r"C:\FOLDERKU\SmartGlove\test_csv",
    
    "window_size": 80,           # frame
    "num_features_raw": 22,      # sensor features
    "sliding_window_step": 1,    # frame per slide (1 = semua window ditest)
    "confidence_threshold": 0.3,
}

# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — SENSOR PREPROCESSING  
# ═════════════════════════════════════════════════════════════════════════════

class GloveSensorPreprocessor:
    """Preprocessing pipeline untuk sensor data."""
    
    def __init__(self, scaler_mean=None, scaler_scale=None):
        self.scaler_mean = np.array(scaler_mean) if scaler_mean else None
        self.scaler_scale = np.array(scaler_scale) if scaler_scale else None
        self._fitted = (scaler_mean is not None)
    
    def transform_sequence(self, raw: np.ndarray, window_size: int) -> np.ndarray:
        """
        Transform raw sensor data → (window_size, 66) tensor siap model.
        
        Fitur output:
            [0:22]   raw (normalized)
            [22:44]  delta (velocity)
            [44:66]  acceleration
        """
        assert self._fitted, "Scaler belum di-fit!"
        raw = np.array(raw, dtype=np.float32)
        
        # 1. Truncate jika terlalu panjang
        if len(raw) > window_size:
            raw = raw[-window_size:]
        
        # 2. Normalize
        normed = (raw - self.scaler_mean) / (self.scaler_scale + 1e-7)
        
        # 3. Delta (velocity)
        delta = np.zeros_like(normed)
        delta[1:] = normed[1:] - normed[:-1]
        
        # 4. Acceleration
        accel = np.zeros_like(normed)
        accel[1:] = delta[1:] - delta[:-1]
        
        # 5. Concatenate
        combined = np.concatenate([normed, delta, accel], axis=-1)
        
        # 6. POST-PADDING
        if len(combined) < window_size:
            pad = np.zeros((window_size - len(combined), combined.shape[1]),
                          dtype=np.float32)
            combined = np.concatenate([combined, pad], axis=0)
        
        return combined.astype(np.float32)


# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — TFLITE INFERENCE ENGINE
# ═════════════════════════════════════════════════════════════════════════════

class TFLitePredictor:
    """Wrapper untuk TFLite interpreter."""
    
    def __init__(self, model_path: str, gesture_labels: List[str]):
        self.interpreter = lite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        
        # Get input/output details
        self.input_detail = self.interpreter.get_input_details()[0]
        self.output_detail = self.interpreter.get_output_details()[0]
        
        self.gesture_labels = gesture_labels
        self.num_gestures = len(gesture_labels)
    
    def predict(self, X: np.ndarray) -> Tuple[int, str, float]:
        """
        Prediksi single window.
        
        Args:
            X: (window_size, 66) tensor
            
        Returns:
            (gesture_id, gesture_label, confidence)
        """
        # Ensure shape (1, window_size, 66)
        if X.ndim == 2:
            X = X[np.newaxis, :]
        
        X = X.astype(self.input_detail['dtype'])
        self.interpreter.set_tensor(self.input_detail['index'], X)
        self.interpreter.invoke()
        
        # Get output
        output = self.interpreter.get_tensor(self.output_detail['index'])
        probabilities = output[0]  # (num_gestures,)
        
        gesture_id = np.argmax(probabilities)
        confidence = float(probabilities[gesture_id])
        gesture_label = self.gesture_labels[gesture_id]
        
        return gesture_id, gesture_label, confidence


# ═════════════════════════════════════════════════════════════════════════════
# PART 3 — CSV DATA LOADER
# ═════════════════════════════════════════════════════════════════════════════

class CSVDataLoader:
    """Loader untuk CSV files."""
    
    # Kolom sensor yang diinginkan (sesuai urutan training)
    SENSOR_COLUMNS = [
        'flex1_L', 'flex2_L', 'flex3_L', 'flex4_L', 'flex5_L',
        'accX_L', 'accY_L', 'accZ_L',
        'gyroX_L', 'gyroY_L', 'gyroZ_L',
        'flex1_R', 'flex2_R', 'flex3_R', 'flex4_R', 'flex5_R',
        'accX_R', 'accY_R', 'accZ_R',
        'gyroX_R', 'gyroY_R', 'gyroZ_R',
    ]
    
    @staticmethod
    def load_csv(csv_path: str) -> np.ndarray:
        """
        Load CSV dan extract sensor features.
        
        Returns:
            np.array (T, 22) — raw sensor data
        """
        df = pd.read_csv(csv_path)
        
        # Validasi kolom
        for col in CSVDataLoader.SENSOR_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"Kolom '{col}' tidak ditemukan di {csv_path}")
        
        # Extract features
        raw = df[CSVDataLoader.SENSOR_COLUMNS].values.astype(np.float32)
        return raw
    
    @staticmethod
    def extract_label_from_filename(filename: str) -> str:
        """
        Extract gesture label dari filename.
        
        Format expected: "{label}_rep{num}_{timestamp}.csv"
        Contoh: "1_rep1_20260406_114050.csv" → "1"
                "pagi_rep1_20260406_114340.csv" → "pagi"
        """
        # Ambil bagian sebelum '_rep'
        parts = filename.split('_rep')
        if len(parts) >= 1:
            return parts[0]
        return "unknown"


# ═════════════════════════════════════════════════════════════════════════════
# PART 4 — TESTING PIPELINE
# ═════════════════════════════════════════════════════════════════════════════

class TFLiteCSVTester:
    """Orchestrator untuk testing."""
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Load metadata
        with open(config["metadata_path"], "r") as f:
            metadata = json.load(f)
        
        self.gesture_labels = metadata.get("gesture_labels", [])
        scaler_data = metadata.get("scaler", {})
        
        # Initialize preprocessor
        self.preprocessor = GloveSensorPreprocessor(
            scaler_mean=scaler_data.get("mean"),
            scaler_scale=scaler_data.get("scale")
        )
        
        # Initialize predictor
        self.predictor = TFLitePredictor(
            config["model_path"],
            self.gesture_labels
        )
        
        print(f"✓ Model loaded: {len(self.gesture_labels)} gestures")
        print(f"✓ Preprocessor ready (window={config['window_size']})")
    
    def test_single_csv(self, csv_path: str) -> Dict:
        """
        Test satu CSV file.
        
        Returns:
            {
                "filename": str,
                "label": str,
                "num_windows": int,
                "correct": int,
                "accuracy": float,
                "predictions": [...]
            }
        """
        filename = os.path.basename(csv_path)
        true_label = CSVDataLoader.extract_label_from_filename(filename)
        
        # Load dan preprocess
        try:
            raw = CSVDataLoader.load_csv(csv_path)
        except Exception as e:
            print(f"  ⚠ Error loading {filename}: {e}")
            return None
        
        # Sliding window
        window_size = self.config["window_size"]
        step = self.config["sliding_window_step"]
        predictions = []
        correct_count = 0
        
        # Generate windows
        num_windows = len(raw) - window_size + 1
        if num_windows <= 0:
            # Data terlalu pendek, pad saja
            X = self.preprocessor.transform_sequence(raw, window_size)
            windows = [X]
        else:
            windows = []
            for i in range(0, num_windows, step):
                window_raw = raw[i:i+window_size]
                X = self.preprocessor.transform_sequence(window_raw, window_size)
                windows.append(X)
        
        # Predict setiap window
        for w_idx, X in enumerate(windows):
            pred_id, pred_label, confidence = self.predictor.predict(X)
            
            is_correct = (pred_label == str(true_label).lower())
            if is_correct:
                correct_count += 1
            
            predictions.append({
                "window_idx": w_idx,
                "predicted": pred_label,
                "confidence": confidence,
                "correct": is_correct,
            })
        
        accuracy = correct_count / len(windows) if windows else 0.0
        
        return {
            "filename": filename,
            "label": true_label,
            "num_windows": len(windows),
            "correct": correct_count,
            "accuracy": accuracy,
            "predictions": predictions,
        }
    
    def run_tests(self) -> Dict:
        """
        Test semua CSV di test_csv folder.
        
        Returns:
            {
                "summary": {...},
                "per_category": {...},
                "per_file": [...]
            }
        """
        test_dir = self.config["test_csv_dir"]
        results_per_file = []
        results_per_category = {}
        
        # Scan semua subfolder (angka, huruf, kata)
        for category in os.listdir(test_dir):
            category_path = os.path.join(test_dir, category)
            if not os.path.isdir(category_path):
                continue
            
            print(f"\n📁 Testing category: {category.upper()}")
            print("=" * 60)
            
            category_results = []
            
            # Scan CSV files
            csv_files = sorted([f for f in os.listdir(category_path) 
                               if f.endswith('.csv')])
            
            for csv_file in csv_files:
                csv_path = os.path.join(category_path, csv_file)
                print(f"  Testing {csv_file}...", end=" ")
                
                result = self.test_single_csv(csv_path)
                if result is None:
                    print("SKIP")
                    continue
                
                results_per_file.append(result)
                category_results.append(result)
                
                # Print summary
                acc_pct = result["accuracy"] * 100
                wins = result["num_windows"]
                print(f"✓ {wins} windows, accuracy={acc_pct:.1f}%")
            
            # Category summary
            if category_results:
                cat_accuracy = np.mean([r["accuracy"] for r in category_results])
                cat_total_windows = sum([r["num_windows"] for r in category_results])
                cat_correct = sum([r["correct"] for r in category_results])
                
                results_per_category[category] = {
                    "num_files": len(category_results),
                    "total_windows": cat_total_windows,
                    "correct_windows": cat_correct,
                    "accuracy": cat_accuracy,
                }
                
                print(f"  📊 Category {category}: "
                      f"accuracy={cat_accuracy*100:.1f}% "
                      f"({cat_correct}/{cat_total_windows} windows correct)")
        
        # Overall summary
        if results_per_file:
            overall_accuracy = np.mean([r["accuracy"] for r in results_per_file])
            total_windows = sum([r["num_windows"] for r in results_per_file])
            total_correct = sum([r["correct"] for r in results_per_file])
        else:
            overall_accuracy = 0.0
            total_windows = 0
            total_correct = 0
        
        return {
            "summary": {
                "timestamp": datetime.now().isoformat(),
                "model_path": self.config["model_path"],
                "total_files": len(results_per_file),
                "total_windows": total_windows,
                "correct_windows": total_correct,
                "overall_accuracy": overall_accuracy,
            },
            "per_category": results_per_category,
            "per_file": results_per_file,
        }


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("╔" + "═" * 58 + "╗")
    print("║ Smart Glove — TFLite CSV Prediction Testing              ║")
    print("╚" + "═" * 58 + "╝\n")
    
    # Initialize tester
    tester = TFLiteCSVTester(CONFIG)
    
    # Run tests
    print(f"\nStarting tests from: {CONFIG['test_csv_dir']}\n")
    results = tester.run_tests()
    
    # Print final summary
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    
    summary = results["summary"]
    print(f"\n📊 Overall Statistics:")
    print(f"   Total Files Tested: {summary['total_files']}")
    print(f"   Total Windows: {summary['total_windows']}")
    print(f"   Correct Predictions: {summary['correct_windows']}")
    print(f"   Overall Accuracy: {summary['overall_accuracy']*100:.2f}%")
    
    print(f"\n📈 Per Category Accuracy:")
    for cat, metrics in results["per_category"].items():
        acc = metrics["accuracy"] * 100
        files = metrics["num_files"]
        windows = metrics["total_windows"]
        correct = metrics["correct_windows"]
        print(f"   {cat:10s}: {acc:6.2f}% ({files} files, "
              f"{correct}/{windows} windows)")
    
    print(f"\n📋 Per File Details:")
    print(f"   {'File':<35s} {'Label':<8s} {'Accuracy':<12s}")
    print(f"   {'-'*55}")
    for r in results["per_file"]:
        fname = r["filename"][:35]
        label = str(r["label"])[:8]
        acc = f"{r['accuracy']*100:.1f}%"
        print(f"   {fname:<35s} {label:<8s} {acc:<12s}")
    
    # Save results to JSON
    output_path = "tflite_test_results.json"
    with open(output_path, "w") as f:
        # Convert numpy types for JSON serialization
        results_json = json.dumps(results, indent=2, default=str)
        f.write(results_json)
    
    print(f"\n✅ Results saved to: {output_path}")


if __name__ == "__main__":
    main()
