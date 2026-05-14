"""
QUICK REFERENCE - Smart Glove Dataset Quality Testing Commands
Copy-paste commands untuk berbagai keperluan
"""

# ============================================================================
# 1. EVALUASI KUALITAS DATASET (LENGKAP)
# ============================================================================

"""
Jalankan evaluasi komprehensif dataset:
"""
cd c:\FOLDERKU\SmartGlove
python dataset_quality_evaluation.py

# Output: Detailed report tentang setiap kategori + overall score


# ============================================================================  
# 2. VISUALISASI DATASET (GRAFIK)
# ============================================================================

"""
Generate grafik distribusi dan statistik:
"""
python visualize_dataset_quality.py

# Output: 
# - dataset_quality_report.png (grafik distribusi semua kategori)
# - dataset_quality_summary.png (tabel ringkasan)


# ============================================================================
# 3. ANALISIS PER-GESTURE (DETAIL)
# ============================================================================

"""
Analisis detail untuk setiap gesture individual:
"""
python gesture_detail_analysis.py

# Output:
# - gesture_rows_distribution.png (histogram distribusi)
# - Console output dengan detail per gesture


# ============================================================================
# 4. LIHAT SAMPLE DATA
# ============================================================================

# Python shell:
import pandas as pd

# Baca satu file untuk melihat struktur:
df_angka = pd.read_csv('datashet/angka/0_rep1_20260402_091923.csv')
print(df_angka.head())
print(df_angka.describe())

# Baca huruf:
df_huruf = pd.read_csv('datashet/huruf/a_rep1_20260402_093922.csv')
print(df_huruf.head())
print(df_huruf.describe())


# ============================================================================
# 5. CUSTOM ANALYSIS - PILIH GESTURE TERTENTU
# ============================================================================

import os
import pandas as pd

# Lihat statistik untuk gesture tertentu (misal angka '5'):
gesture = '5'
csv_files = [f for f in os.listdir('datashet/angka') 
             if f.startswith(gesture + '_rep') and f.endswith('.csv')]

print(f"File untuk gesture '{gesture}':")
for f in csv_files:
    df = pd.read_csv(f'datashet/angka/{f}')
    print(f"  {f}: {len(df)} rows")

# Combine semua repetisi untuk gesture '5':
all_dfs = []
for f in csv_files:
    df = pd.read_csv(f'datashet/angka/{f}')
    all_dfs.append(df)

combined = pd.concat(all_dfs)
print(f"\nGesture '{gesture}' Statistics:")
print(combined.describe())


# ============================================================================
# 6. CEK KELENGKAPAN DATA
# ============================================================================

import os
import pandas as pd

data_path = 'datashet'

for category in ['angka', 'huruf']:
    cat_path = os.path.join(data_path, category)
    files = [f for f in os.listdir(cat_path) if f.endswith('.csv')]
    gestures = set([f.split('_rep')[0] for f in files])
    
    print(f"\n{category.upper()}:")
    print(f"Total file: {len(files)}")
    print(f"Total gesture: {len(gestures)}")
    
    # Cek apakah setiap gesture punya 5 repetisi
    incomplete = []
    for gesture in sorted(gestures):
        gesture_files = [f for f in files if f.startswith(gesture + '_rep')]
        if len(gesture_files) != 5:
            incomplete.append((gesture, len(gesture_files)))
    
    if incomplete:
        print(f"❌ Gesture tidak lengkap: {incomplete}")
    else:
        print(f"✅ Semua gesture punya 5 repetisi")


# ============================================================================
# 7. ANALISIS DISTRIBUSI SENSOR
# ============================================================================

import pandas as pd
import numpy as np

# Load semua data ANGKA
files = os.listdir('datashet/angka')
all_data = []
for f in files:
    if f.endswith('.csv'):
        df = pd.read_csv(f'datashet/angka/{f}')
        all_data.append(df)

combined = pd.concat(all_data, ignore_index=True)

# Analisis flex sensors
flex_cols = ['flex1_L', 'flex2_L', 'flex3_L', 'flex4_L', 'flex5_L',
             'flex1_R', 'flex2_R', 'flex3_R', 'flex4_R', 'flex5_R']

print("FLEX SENSORS STATISTICS (ANGKA):")
print(combined[flex_cols].describe())

# Cek ada yang out of range (< 0 atau > 1):
out_of_range = ((combined[flex_cols] < 0) | (combined[flex_cols] > 1)).sum().sum()
print(f"\nOut of range values: {out_of_range}")


# ============================================================================
# 8. IMPORT DATASET UNTUK TRAINING
# ============================================================================

import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

def load_dataset(data_path='datashet'):
    """Load semua data untuk training"""
    X = []
    y = []
    
    for category in ['angka', 'huruf']:
        cat_path = os.path.join(data_path, category)
        files = [f for f in os.listdir(cat_path) if f.endswith('.csv')]
        
        for f in files:
            gesture = f.split('_rep')[0]
            df = pd.read_csv(os.path.join(cat_path, f))
            
            # Ambil sensor columns (exclude timestamp, repetition)
            sensor_cols = [col for col in df.columns 
                          if col not in ['timestamp', 'repetition']]
            
            # Normalize data (optional)
            sensor_data = df[sensor_cols].values
            
            X.append(sensor_data)
            y.extend([gesture] * len(sensor_data))
    
    X = np.concatenate(X)
    y = np.array(y)
    
    return X, y

# Usage:
X, y = load_dataset()
print(f"Dataset shape: {X.shape}")
print(f"Number of classes: {len(set(y))}")

# Split data:
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"Train set: {X_train.shape[0]} samples")
print(f"Test set: {X_test.shape[0]} samples")


# ============================================================================
# 9. CEPAT CEK FILE SIZE & STORAGE
# ============================================================================

import os

def get_folder_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            total_size += os.path.getsize(filepath)
    return total_size

angka_size = get_folder_size('datashet/angka')
huruf_size = get_folder_size('datashet/huruf')
total_size = angka_size + huruf_size

print(f"ANGKA folder size: {angka_size/1024/1024:.1f} MB")
print(f"HURUF folder size: {huruf_size/1024/1024:.1f} MB")
print(f"Total size: {total_size/1024/1024:.1f} MB")


# ============================================================================
# 10. GENERATE REPORT TEXT FILE
# ============================================================================

import os
import pandas as pd

report = []

report.append("="*80)
report.append("DATASET QUALITY REPORT - Smart Glove Gesture Recognition")
report.append("="*80)
report.append("")

for category in ['angka', 'huruf']:
    cat_path = f'datashet/{category}'
    files = [f for f in os.listdir(cat_path) if f.endswith('.csv')]
    gestures = sorted(set([f.split('_rep')[0] for f in files]))
    
    report.append(f"\nCategory: {category.upper()}")
    report.append(f"Total Files: {len(files)}")
    report.append(f"Total Gestures: {len(gestures)}")
    report.append(f"Gestures: {', '.join(gestures)}")
    
    # Load semua data
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(cat_path, f))
        all_data.append(df)
    
    combined = pd.concat(all_data)
    report.append(f"Total Samples: {len(combined):,}")
    report.append(f"Average rows per file: {len(combined)/len(files):.1f}")
    report.append(f"Missing values: {combined.isnull().sum().sum()}")

# Save report
with open('dataset_report.txt', 'w') as f:
    f.write('\n'.join(report))

print("✅ Report saved to dataset_report.txt")

# ============================================================================
# HELPFUL TIPS
# ============================================================================

"""
TIPS BERGUNA:

1. Data Loading Performance:
   - Jangan load semua data sekaligus jika dataset besar
   - Gunakan chunking atau generator untuk memory efficiency

2. Data Preprocessing:
   - Normalize semua features sebelum training
   - Handle outliers dengan IQR method
   - Apply smoothing untuk sensor noise

3. Train/Test Split:
   - Gunakan stratified split untuk maintain class balance
   - Consider per-gesture cross-validation untuk small classes

4. Data Augmentation:
   - Sliding window dengan stride kecil
   - Add Gaussian noise untuk robustness
   - Time warping untuk temporal variation

5. Monitoring:
   - Track per-gesture accuracy selama training
   - Monitor class 's', 'l', 'y' extra (imbalanced)
   - Use F1-score untuk imbalanced data, bukan accuracy

6. Next Steps:
   - Mulai dengan simple model (logistic regression) sebagai baseline
   - Graduate ke LSTM atau TCN untuk better temporal modeling
   - Use ensemble methods untuk final production
"""
