"""
Dataset Quality Evaluation Script
Mengecek kualitas dataset untuk Smart Glove Gesture Recognition
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

class DatasetQualityEvaluator:
    def __init__(self, dataset_root="datashet"):
        self.dataset_root = dataset_root
        self.angka_path = os.path.join(dataset_root, "angka")
        self.huruf_path = os.path.join(dataset_root, "huruf")
        self.kata_path = os.path.join(dataset_root, "kata")
        self.frasa_path = os.path.join(dataset_root, "frasa")
        self.kontrol_path = os.path.join(dataset_root, "kontrol")
        self.rilis_path = os.path.join(dataset_root, "rilis")
        self.results = {}
        
    def evaluate_category(self, category_path, category_name):
        """Evaluasi kualitas data untuk satu kategori"""
        print(f"\n{'='*80}")
        print(f"EVALUASI KATEGORI: {category_name.upper()}")
        print(f"{'='*80}")
        
        if not os.path.exists(category_path):
            print(f"⚠️  Path tidak ditemukan: {category_path}")
            return None
        
        csv_files = sorted([f for f in os.listdir(category_path) if f.endswith('.csv')])
        
        # 1. CEK KELENGKAPAN FILE
        print(f"\n1️⃣  CEK KELENGKAPAN FILE")
        print(f"   Total file ditemukan: {len(csv_files)}")
        
        # Kelompokkan berdasarkan gesture
        gestures = {}
        for fname in csv_files:
            parts = fname.split('_rep')
            gesture = parts[0]
            if gesture not in gestures:
                gestures[gesture] = []
            gestures[gesture].append(fname)
        
        print(f"   Total gesture unik: {len(gestures)}")
        
        # Cek apakah semua gesture memiliki 5 repetisi
        incomplete_gestures = []
        for gesture, files in sorted(gestures.items()):
            if len(files) != 5:
                incomplete_gestures.append((gesture, len(files)))
                print(f"   ⚠️  Gesture '{gesture}' hanya punya {len(files)}/5 repetisi")
        
        if not incomplete_gestures:
            print(f"   ✅ Semua gesture punya 5 repetisi")
        else:
            print(f"   ❌ Ada {len(incomplete_gestures)} gesture yang tidak lengkap")
        
        # 2. ANALISIS STATISTIK DATA
        print(f"\n2️⃣  ANALISIS STATISTIK DATA")
        
        file_stats = []
        all_data = []
        
        for fname in csv_files:
            fpath = os.path.join(category_path, fname)
            try:
                df = pd.read_csv(fpath)
                all_data.append(df)
                
                # Statistik file
                gesture = fname.split('_rep')[0]
                num_rows = len(df)
                num_cols = len(df.columns)
                missing_values = df.isnull().sum().sum()
                
                file_stats.append({
                    'file': fname,
                    'gesture': gesture,
                    'rows': num_rows,
                    'cols': num_cols,
                    'missing': missing_values
                })
            except Exception as e:
                print(f"   ❌ Error membaca {fname}: {str(e)}")
        
        if file_stats:
            stats_df = pd.DataFrame(file_stats)
            print(f"\n   File Statistics:")
            print(f"   - Rata-rata baris per file: {stats_df['rows'].mean():.1f} (min: {stats_df['rows'].min()}, max: {stats_df['rows'].max()})")
            print(f"   - Total kolom: {stats_df['cols'].iloc[0]} (konsisten: {'✅' if stats_df['cols'].nunique() == 1 else '❌'})")
            print(f"   - Total missing values: {stats_df['missing'].sum()} ({'✅' if stats_df['missing'].sum() == 0 else '❌'})")
            
            # Cek variasi baris antar file
            if stats_df['rows'].std() > stats_df['rows'].mean() * 0.1:
                print(f"   ⚠️  Ada variasi besar dalam jumlah baris per file (std: {stats_df['rows'].std():.1f})")
            else:
                print(f"   ✅ Jumlah baris konsisten antar file")
        
        # 3. ANALISIS DATA NUMERIK
        print(f"\n3️⃣  ANALISIS DATA NUMERIK")
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Ambil kolom numerik (exclude timestamp dan repetition untuk analisis awal)
            numeric_cols = [col for col in combined_df.columns 
                           if col not in ['timestamp', 'repetition']]
            
            print(f"\n   Range Data Sensor:")
            print(f"   {'-'*70}")
            
            # Analisis per kolom
            outlier_count = 0
            zero_variance_cols = []
            
            for col in numeric_cols:
                try:
                    data = combined_df[col].dropna()
                    if len(data) == 0:
                        continue
                    
                    mean_val = data.mean()
                    std_val = data.std()
                    min_val = data.min()
                    max_val = data.max()
                    
                    # Cek outliers menggunakan IQR
                    Q1 = data.quantile(0.25)
                    Q3 = data.quantile(0.75)
                    IQR = Q3 - Q1
                    outliers = len(data[(data < Q1 - 1.5*IQR) | (data > Q3 + 1.5*IQR)])
                    
                    if std_val < 1e-6:
                        zero_variance_cols.append(col)
                    
                    if outliers > len(data) * 0.05:  # Lebih dari 5% outliers
                        outlier_count += 1
                        status = "⚠️"
                    else:
                        status = "✅"
                    
                    print(f"   {status} {col:15} → min: {min_val:8.4f}, max: {max_val:8.4f}, mean: {mean_val:8.4f}, std: {std_val:8.4f}")
                except:
                    pass
            
            if zero_variance_cols:
                print(f"\n   ⚠️  Kolom dengan variance ~0: {zero_variance_cols}")
            
            print(f"\n   Total outliers terdeteksi: {outlier_count} dari {len(numeric_cols)} kolom")
        
        # 4. KESEIMBANGAN DATASET
        print(f"\n4️⃣  KESEIMBANGAN DATASET")
        
        gesture_counts = {}
        if file_stats:
            samples_per_gesture = {}
            for stat in file_stats:
                gesture = stat['gesture']
                samples_per_gesture[gesture] = stat['rows']
            
            gesture_counts = {}
            for gesture, files in sorted(gestures.items()):
                total_rows = sum([s['rows'] for s in file_stats if s['gesture'] == gesture])
                gesture_counts[gesture] = total_rows
            
            if gesture_counts:
                counts = list(gesture_counts.values())
                mean_count = np.mean(counts)
                std_count = np.std(counts)
                imbalance_ratio = np.max(counts) / (np.min(counts) + 1e-6)
                
                print(f"   Total sampel: {sum(counts)}")
                print(f"   Rata-rata per gesture: {mean_count:.1f}")
                print(f"   Range: {np.min(counts)} - {np.max(counts)}")
                print(f"   Imbalance ratio: {imbalance_ratio:.2f}x")
                
                if imbalance_ratio > 1.2:
                    print(f"   ⚠️  Dataset TIDAK SEIMBANG (>20% perbedaan)")
                else:
                    print(f"   ✅ Dataset SEIMBANG")
                
                # Top 5 gesture dengan paling sedikit sampel
                sorted_gestures = sorted(gesture_counts.items(), key=lambda x: x[1])
                print(f"\n   Gesture dengan sampel PALING SEDIKIT:")
                for gesture, count in sorted_gestures[:5]:
                    print(f"   - {gesture}: {count} sampel")
        
        # 5. KUALITAS SENSOR READINGS
        print(f"\n5️⃣  KUALITAS SENSOR READINGS")
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Cek sensor flex (jangan ada nilai > 1 atau < 0)
            flex_cols = [col for col in combined_df.columns if 'flex' in col.lower()]
            if flex_cols:
                flex_data = combined_df[flex_cols]
                invalid_flex = ((flex_data < 0) | (flex_data > 1)).sum().sum()
                print(f"   Flex sensors: {invalid_flex} nilai invalid (harus 0-1)")
                if invalid_flex == 0:
                    print(f"   ✅ Semua flex sensor readings valid")
                else:
                    print(f"   ❌ Ada {invalid_flex} invalid readings")
            
            # Cek untuk setiap repetisi
            if 'repetition' in combined_df.columns:
                reps = combined_df['repetition'].unique()
                print(f"\n   Repetisi yang ada: {sorted(reps)}")
        
        # RINGKASAN
        print(f"\n{'='*80}")
        print(f"RINGKASAN - {category_name.upper()}")
        print(f"{'='*80}")
        
        quality_score = 100
        issues = []
        
        if incomplete_gestures:
            quality_score -= 20
            issues.append(f"Ada {len(incomplete_gestures)} gesture tidak lengkap")
        
        if file_stats and stats_df['missing'].sum() > 0:
            quality_score -= 10
            issues.append("Ada missing values")
        
        if gesture_counts:
            imbalance_ratio = np.max(list(gesture_counts.values())) / (np.min(list(gesture_counts.values())) + 1e-6)
            if imbalance_ratio > 1.2:
                quality_score -= 10
                issues.append("Dataset tidak seimbang")
        
        if issues:
            print("Issues found:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✅ Tidak ada issue signifikan ditemukan!")
        
        print(f"\n📊 QUALITY SCORE: {quality_score}/100")
        
        if quality_score >= 80:
            print("❤️  KUALITAS: BAIK - Dataset siap untuk training")
        elif quality_score >= 60:
            print("🟡 KUALITAS: CUKUP - Review dan perbaiki beberapa issue")
        else:
            print("❌ KUALITAS: BURUK - Perlu perbaikan signifikan")
        
        return {
            'category': category_name,
            'score': quality_score,
            'total_files': len(csv_files),
            'total_gestures': len(gestures),
            'issues': issues,
            'incomplete_gestures': incomplete_gestures
        }
    
    def run_full_evaluation(self):
        """Jalankan evaluasi untuk semua kategori"""
        print("\n" + "="*80)
        print("🔍 SMART GLOVE DATASET QUALITY EVALUATION")
        print("="*80)
        
        results = []
        
        # Evaluasi angka
        result_angka = self.evaluate_category(self.angka_path, "ANGKA")
        if result_angka:
            results.append(result_angka)
        
        # Evaluasi huruf
        result_huruf = self.evaluate_category(self.huruf_path, "HURUF")
        if result_huruf:
            results.append(result_huruf)
        
        # Evaluasi kata
        result_kata = self.evaluate_category(self.kata_path, "KATA")
        if result_kata:
            results.append(result_kata)
        
        # Evaluasi frasa
        result_frasa = self.evaluate_category(self.frasa_path, "FRASA")
        if result_frasa:
            results.append(result_frasa)
        
        # Evaluasi kontrol
        result_kontrol = self.evaluate_category(self.kontrol_path, "KONTROL")
        if result_kontrol:
            results.append(result_kontrol)
        
        # Evaluasi rilis
        result_rilis = self.evaluate_category(self.rilis_path, "RILIS")
        if result_rilis:
            results.append(result_rilis)
        
        # Print summary keseluruhan
        print("\n\n" + "="*80)
        print("📋 SUMMARY KESELURUHAN")
        print("="*80)
        
        for result in results:
            print(f"{result['category']:10} | Score: {result['score']:3}/100 | Files: {result['total_files']:4} | Gestures: {result['total_gestures']:3}")
        
        if results:
            avg_score = np.mean([r['score'] for r in results])
            print(f"\n{'='*80}")
            print(f"AVERAGE QUALITY SCORE: {avg_score:.1f}/100")
            
            if avg_score >= 80:
                print("✅ DATASET BAIK - Dataset siap untuk training model")
            elif avg_score >= 60:
                print("🟡 DATASET CUKUP - Lakukan perbaikan untuk hasil optimal")
            else:
                print("❌ DATASET KURANG - Diperlukan pengumpulan data tambahan")
            print("="*80)
        
        return results

if __name__ == "__main__":
    evaluator = DatasetQualityEvaluator()
    results = evaluator.run_full_evaluation()
