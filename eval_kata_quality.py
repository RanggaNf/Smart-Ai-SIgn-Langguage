"""
Data KATA Quality Evaluation
Evaluasi kualitas dataset untuk kategori KATA
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

class KataDataQualityEvaluator:
    def __init__(self, dataset_path="datashet/kata"):
        self.kata_path = dataset_path
    
    def evaluate_kata_category(self):
        """Evaluasi kualitas data KATA"""
        print(f"\n{'='*80}")
        print(f"EVALUASI KATEGORI KATA (WORDS)")
        print(f"{'='*80}")
        
        if not os.path.exists(self.kata_path):
            print(f"⚠️  Path tidak ditemukan: {self.kata_path}")
            return None
        
        csv_files = sorted([f for f in os.listdir(self.kata_path) if f.endswith('.csv')])
        
        # 1. CEK KELENGKAPAN FILE
        print(f"\n1️⃣  CEK KELENGKAPAN FILE")
        print(f"   Total file ditemukan: {len(csv_files)}")
        
        # Kelompokkan berdasarkan kata
        words = {}
        for fname in csv_files:
            parts = fname.split('_rep')
            word = parts[0]
            if word not in words:
                words[word] = []
            words[word].append(fname)
        
        print(f"   Total kata unik: {len(words)}")
        print(f"   Kata-kata: {', '.join(sorted(words.keys()))}")
        
        # Cek apakah semua kata memiliki 5 repetisi
        incomplete_words = []
        for word, files in words.items():
            if len(files) != 5:
                incomplete_words.append((word, len(files)))
                print(f"   ⚠️  Kata '{word}' hanya punya {len(files)}/5 repetisi")
        
        if not incomplete_words:
            print(f"   ✅ Semua kata punya 5 repetisi")
        else:
            print(f"   ❌ Ada {len(incomplete_words)} kata yang tidak lengkap")
        
        # 2. ANALISIS STATISTIK DATA
        print(f"\n2️⃣  ANALISIS STATISTIK DATA")
        
        file_stats = []
        all_data = []
        
        for fname in csv_files:
            fpath = os.path.join(self.kata_path, fname)
            try:
                df = pd.read_csv(fpath)
                all_data.append(df)
                
                # Statistik file
                word = fname.split('_rep')[0]
                num_rows = len(df)
                num_cols = len(df.columns)
                missing_values = df.isnull().sum().sum()
                
                file_stats.append({
                    'file': fname,
                    'word': word,
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
                print(f"   ⚠️  Ada variasi dalam jumlah baris per file (std: {stats_df['rows'].std():.1f})")
            else:
                print(f"   ✅ Jumlah baris konsisten antar file")
        
        # 3. ANALISIS DATA NUMERIK
        print(f"\n3️⃣  ANALISIS DATA NUMERIK")
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Ambil kolom numerik
            numeric_cols = [col for col in combined_df.columns 
                           if col not in ['timestamp', 'repetition']]
            
            print(f"\n   Range Data Sensor (Sample 7 kolom):")
            print(f"   {'-'*70}")
            
            sample_cols = numeric_cols[:7]
            for col in sample_cols:
                try:
                    data = combined_df[col].dropna()
                    if len(data) == 0:
                        continue
                    
                    mean_val = data.mean()
                    std_val = data.std()
                    min_val = data.min()
                    max_val = data.max()
                    
                    # Cek outliers
                    Q1 = data.quantile(0.25)
                    Q3 = data.quantile(0.75)
                    IQR = Q3 - Q1
                    outliers = len(data[(data < Q1 - 1.5*IQR) | (data > Q3 + 1.5*IQR)])
                    
                    if outliers > len(data) * 0.05:
                        status = "⚠️"
                    else:
                        status = "✅"
                    
                    print(f"   {status} {col:15} → min: {min_val:8.4f}, max: {max_val:8.4f}, mean: {mean_val:8.4f}")
                except:
                    pass
        
        # 4. KESEIMBANGAN DATASET
        print(f"\n4️⃣  KESEIMBANGAN DATASET")
        
        if file_stats:
            gesture_counts = {}
            for stat in file_stats:
                word = stat['word']
                if word not in gesture_counts:
                    gesture_counts[word] = 0
                gesture_counts[word] += stat['rows']
            
            if gesture_counts:
                counts = list(gesture_counts.values())
                mean_count = np.mean(counts)
                std_count = np.std(counts)
                imbalance_ratio = np.max(counts) / (np.min(counts) + 1e-6)
                
                print(f"   Total sampel: {sum(counts)}")
                print(f"   Total kata: {len(gesture_counts)}")
                print(f"   Rata-rata per kata: {mean_count:.1f}")
                print(f"   Range: {np.min(counts)} - {np.max(counts)}")
                print(f"   Imbalance ratio: {imbalance_ratio:.2f}x")
                
                if imbalance_ratio > 1.2:
                    print(f"   ⚠️  Dataset TIDAK SEIMBANG (>20% perbedaan)")
                else:
                    print(f"   ✅ Dataset SEIMBANG")
                
                # Daftar kata dengan sampel terbanyak dan tersedikit
                sorted_words = sorted(gesture_counts.items(), key=lambda x: x[1])
                
                if len(sorted_words) > 0:
                    print(f"\n   Kata dengan sampel PALING SEDIKIT:")
                    for word, count in sorted_words[:5]:
                        pct = (count / mean_count * 100)
                        print(f"   - {word}: {count} sampel ({pct:.1f}% dari rata-rata)")
                    
                    print(f"\n   Kata dengan sampel PALING BANYAK:")
                    for word, count in sorted_words[-5:]:
                        pct = (count / mean_count * 100)
                        print(f"   - {word}: {count} sampel ({pct:.1f}% dari rata-rata)")
        
        # 5. KUALITAS SENSOR
        print(f"\n5️⃣  KUALITAS SENSOR READINGS")
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Cek flex sensors
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
        print(f"RINGKASAN - KATEGORI KATA")
        print(f"{'='*80}")
        
        quality_score = 100
        issues = []
        
        if incomplete_words:
            quality_score -= 20
            issues.append(f"Ada {len(incomplete_words)} kata tidak lengkap")
        
        if file_stats and stats_df['missing'].sum() > 0:
            quality_score -= 10
            issues.append("Ada missing values")
        
        if gesture_counts:
            imbalance_ratio = np.max(list(gesture_counts.values())) / (np.min(list(gesture_counts.values())) + 1e-6)
            if imbalance_ratio > 1.2:
                quality_score -= 15
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
        
        # Statistik detail per kata
        print(f"\n{'='*80}")
        print(f"STATISTIK DETAIL PER KATA")
        print(f"{'='*80}\n")
        
        print(f"{'Kata':<15} | {'Files':>5} | {'Total Rows':>10} | {'Avg/File':>8} | {'%/Rata2':>8}")
        print(f"{'-'*65}")
        
        for word in sorted(gesture_counts.keys()):
            count = gesture_counts[word]
            files_count = len([w for w in words[word]])
            avg_per_file = count / files_count
            pct_of_mean = (count / mean_count * 100)
            
            print(f"{word:<15} | {files_count:>5} | {count:>10} | {avg_per_file:>8.1f} | {pct_of_mean:>7.1f}%")
        
        return {
            'category': 'KATA',
            'score': quality_score,
            'total_files': len(csv_files),
            'total_words': len(words),
            'total_samples': sum(counts),
            'issues': issues,
            'incomplete_words': incomplete_words,
            'word_counts': gesture_counts
        }

if __name__ == "__main__":
    evaluator = KataDataQualityEvaluator()
    result = evaluator.evaluate_kata_category()
    
    print(f"\n{'='*80}")
    print("✅ Evaluasi KATA selesai!")
    print(f"{'='*80}")
