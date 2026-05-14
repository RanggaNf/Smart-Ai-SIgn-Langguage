"""
Per-Gesture Detailed Analysis
Analisis detail untuk setiap gesture individual
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

class GestureDetailAnalyzer:
    def __init__(self, dataset_root="datashet"):
        self.dataset_root = dataset_root
        self.angka_path = os.path.join(dataset_root, "angka")
        self.huruf_path = os.path.join(dataset_root, "huruf")
    
    def analyze_gesture(self, gesture_name, category_path):
        """Analisis detail untuk satu gesture"""
        csv_files = [f for f in os.listdir(category_path) 
                    if f.startswith(gesture_name + '_rep') and f.endswith('.csv')]
        
        if not csv_files:
            return None
        
        all_data = []
        for fname in sorted(csv_files):
            df = pd.read_csv(os.path.join(category_path, fname))
            rep_num = int(fname.split('_rep')[1].split('_')[0])
            df['file_rep'] = rep_num
            all_data.append(df)
        
        combined = pd.concat(all_data, ignore_index=True)
        
        return {
            'gesture': gesture_name,
            'files': len(csv_files),
            'total_rows': len(combined),
            'rows_per_rep': combined.groupby('file_rep').size().to_dict(),
            'data': combined
        }
    
    def generate_gesture_report(self, category, category_name):
        """Buat laporan untuk semua gesture dalam kategori"""
        category_path = self.angka_path if category == 'angka' else self.huruf_path
        
        # Ambil semua gesture unik
        all_files = [f for f in os.listdir(category_path) if f.endswith('.csv')]
        gestures = sorted(set([f.split('_rep')[0] for f in all_files]))
        
        print(f"\n{'='*80}")
        print(f"DETAILED GESTURE ANALYSIS - {category_name.upper()}")
        print(f"{'='*80}\n")
        
        gesture_report = []
        
        for gesture in gestures:
            result = self.analyze_gesture(gesture, category_path)
            if result is None:
                continue
            
            data = result['data']
            
            # Hitung statistik
            flex_cols = [c for c in data.columns if 'flex' in c.lower()]
            acc_cols = [c for c in data.columns if 'acc' in c.lower()]
            gyro_cols = [c for c in data.columns if 'gyro' in c.lower()]
            
            flex_stats = data[flex_cols].agg(['mean', 'std', 'min', 'max'])
            acc_stats = data[acc_cols].agg(['mean', 'std', 'min', 'max'])
            gyro_stats = data[gyro_cols].agg(['mean', 'std', 'min', 'max'])
            
            # Cek variasi antar repetisi
            rep_vars = {}
            for col in flex_cols[:3]:  # Check first 3 flex sensors
                rep_means = data.groupby('file_rep')[col].mean().values
                rep_vars[col] = np.std(rep_means)
            
            avg_rep_var = np.mean(list(rep_vars.values()))
            
            gesture_report.append({
                'gesture': gesture,
                'total_rows': result['total_rows'],
                'files': result['files'],
                'avg_rows_per_file': result['total_rows'] / result['files'],
                'flex_mean': flex_stats.loc['mean'].mean(),
                'gyro_mean': gyro_stats.loc['mean'].mean(),
                'rep_consistency': avg_rep_var,
                'rows_per_rep': result['rows_per_rep']
            })
        
        # Print dalam format tabel
        print(f"{'Gesture':<8} | {'Files':>5} | {'Total Rows':>10} | {'Avg/File':>8} | {'Flex Mean':>10} | {'Consistency':>12}")
        print(f"{'-'*80}")
        
        for report in gesture_report:
            consistency = "✅ Good" if report['rep_consistency'] < 0.05 else "⚠️  Variable"
            print(f"{report['gesture']:<8} | {report['files']:>5} | {report['total_rows']:>10} | "
                  f"{report['avg_rows_per_file']:>8.1f} | {report['flex_mean']:>10.3f} | {consistency:>12}")
        
        # Statistik keseluruhan
        print(f"\n{'='*80}")
        print("STATISTIK KESELURUHAN")
        print(f"{'='*80}")
        
        total_rows = sum([r['total_rows'] for r in gesture_report])
        avg_rows = np.mean([r['total_rows'] for r in gesture_report])
        std_rows = np.std([r['total_rows'] for r in gesture_report])
        
        print(f"Total Gesture: {len(gesture_report)}")
        print(f"Total Sampel: {total_rows:,}")
        print(f"Rata-rata sampel/gesture: {avg_rows:.0f} ± {std_rows:.0f}")
        print(f"Range: {min([r['total_rows'] for r in gesture_report])} - {max([r['total_rows'] for r in gesture_report])}")
        
        # Find outliers
        low_count = [r for r in gesture_report if r['total_rows'] < avg_rows - std_rows]
        high_count = [r for r in gesture_report if r['total_rows'] > avg_rows + std_rows]
        
        if low_count:
            print(f"\n⚠️  Gesture dengan sampel RENDAH:")
            for r in sorted(low_count, key=lambda x: x['total_rows']):
                print(f"   - {r['gesture']}: {r['total_rows']} sampel ({r['total_rows']/avg_rows*100:.1f}% dari rata-rata)")
        
        if high_count:
            print(f"\n⚠️  Gesture dengan sampel TINGGI:")
            for r in sorted(high_count, key=lambda x: x['total_rows'], reverse=True):
                print(f"   - {r['gesture']}: {r['total_rows']} sampel ({r['total_rows']/avg_rows*100:.1f}% dari rata-rata)")
        
        if not low_count and not high_count:
            print(f"\n✅ Semua gesture memiliki sampel yang SEIMBANG")
        
        return gesture_report
    
    def create_gesture_comparison_chart(self):
        """Buat chart perbandingan gesture"""
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Analisis ANGKA
        angka_files = [f for f in os.listdir(self.angka_path) if f.endswith('.csv')]
        angka_gestures = sorted(set([f.split('_rep')[0] for f in angka_files]))
        angka_counts = []
        for gesture in angka_gestures:
            files = [f for f in angka_files if f.startswith(gesture + '_rep')]
            if files:
                df = pd.read_csv(os.path.join(self.angka_path, files[0]))
                angka_counts.append(len(df))
        
        # Analisis HURUF (sample)
        huruf_files = [f for f in os.listdir(self.huruf_path) if f.endswith('.csv')]
        huruf_gestures = sorted(set([f.split('_rep')[0] for f in huruf_files]))
        huruf_counts = []
        for gesture in huruf_gestures:
            files = [f for f in huruf_files if f.startswith(gesture + '_rep')]
            if files:
                df = pd.read_csv(os.path.join(self.huruf_path, files[0]))
                huruf_counts.append(len(df))
        
        # Plot ANGKA
        ax1.hist(angka_counts, bins=15, color='#2ecc71', alpha=0.7, edgecolor='black')
        ax1.axvline(np.mean(angka_counts), color='red', linestyle='--', linewidth=2, 
                   label=f'Mean: {np.mean(angka_counts):.0f}')
        ax1.axvline(np.median(angka_counts), color='blue', linestyle='--', linewidth=2, 
                   label=f'Median: {np.median(angka_counts):.0f}')
        ax1.set_xlabel('Rows per File', fontsize=11, fontweight='bold')
        ax1.set_ylabel('Frequency', fontsize=11, fontweight='bold')
        ax1.set_title('Distribution of Rows per File - ANGKA', fontsize=12, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot HURUF
        ax2.hist(huruf_counts, bins=20, color='#e74c3c', alpha=0.7, edgecolor='black')
        ax2.axvline(np.mean(huruf_counts), color='red', linestyle='--', linewidth=2, 
                   label=f'Mean: {np.mean(huruf_counts):.0f}')
        ax2.axvline(np.median(huruf_counts), color='blue', linestyle='--', linewidth=2, 
                   label=f'Median: {np.median(huruf_counts):.0f}')
        ax2.set_xlabel('Rows per File', fontsize=11, fontweight='bold')
        ax2.set_ylabel('Frequency', fontsize=11, fontweight='bold')
        ax2.set_title('Distribution of Rows per File - HURUF', fontsize=12, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('gesture_rows_distribution.png', dpi=120, bbox_inches='tight')
        print("\n✅ Chart saved as 'gesture_rows_distribution.png'")

if __name__ == "__main__":
    analyzer = GestureDetailAnalyzer()
    
    # Generate report untuk ANGKA
    angka_report = analyzer.generate_gesture_report('angka', 'ANGKA')
    
    # Generate report untuk HURUF
    huruf_report = analyzer.generate_gesture_report('huruf', 'HURUF')
    
    # Create comparison chart
    analyzer.create_gesture_comparison_chart()
    
    print("\n" + "="*80)
    print("✅ Analisis per-gesture selesai!")
    print("="*80)
