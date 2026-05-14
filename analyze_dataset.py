import os
import csv
import pandas as pd
from collections import defaultdict
import numpy as np

base_path = r'C:\FOLDERKU\SmartGlove\datashet'
categories = ['angka', 'huruf', 'kata', 'frasa', 'rilis']

print('='*70)
print('ANALISIS KUALITAS DATASET SMARTGLOVE')
print('='*70)

stats = defaultdict(lambda: {'total': 0, 'good': 0, 'bad': 0, 'issues': []})
detailed_stats = {}

for category in categories:
    cat_path = os.path.join(base_path, category)
    files = sorted([f for f in os.listdir(cat_path) if f.endswith('.csv')])
    
    print(f'\n[{category.upper()}] Menganalisis {len(files)} files...')
    
    for file in files:
        filepath = os.path.join(cat_path, file)
        stats[category]['total'] += 1
        
        try:
            df = pd.read_csv(filepath)
            
            issues = []
            
            # Check row count
            rows = len(df)
            if rows < 100:
                issues.append(f'Too few rows ({rows})')
                stats[category]['bad'] += 1
            
            # Check for null values
            null_count = df.isnull().sum().sum()
            if null_count > 0:
                issues.append(f'Null values ({null_count})')
                stats[category]['bad'] += 1
            
            # Check flex sensors (0-1 range)
            flex_cols = [c for c in df.columns if 'flex' in c]
            if flex_cols:
                flex_data = df[flex_cols]
                if (flex_data < -0.1).any().any() or (flex_data > 1.1).any().any():
                    bad_flex = flex_cols[(flex_data < -0.1).any() | (flex_data > 1.1).any()].tolist()
                    issues.append(f'Flex out of range: {bad_flex[0] if bad_flex else "?"}')
                    stats[category]['bad'] += 1
            
            # Check accelerometer
            accel_cols = [c for c in df.columns if 'acc' in c]
            if accel_cols:
                accel_data = df[accel_cols]
                if (accel_data < -50).any().any() or (accel_data > 50).any().any():
                    issues.append(f'Accel extreme values')
                    stats[category]['bad'] += 1
            
            if not issues:
                stats[category]['good'] += 1
                detailed_stats[f"{category}/{file}"] = {'rows': rows, 'issues': 'OK'}
            else:
                stats[category]['issues'].append((file, issues))
                detailed_stats[f"{category}/{file}"] = {'rows': rows, 'issues': issues}
        
        except Exception as e:
            issues = [f'Error: {str(e)[:50]}']
            stats[category]['bad'] += 1
            stats[category]['issues'].append((file, issues))
            detailed_stats[f"{category}/{file}"] = {'rows': 0, 'issues': issues}

print('\n' + '='*70)
print('RINGKASAN PER KATEGORI:')
print('='*70)

total_files = 0
total_good = 0

for cat in categories:
    s = stats[cat]
    pct = (s['good'] / s['total'] * 100) if s['total'] > 0 else 0
    status = '✓ OK' if pct >= 90 else '⚠ PERIKSA' if pct >= 70 else '✗ BURUK'
    print(f'{cat:10} | Total:{s["total"]:3d} | Good:{s["good"]:3d} | Bad:{s["bad"]:3d} | {pct:5.1f}% {status}')
    total_files += s['total']
    total_good += s['good']

overall_pct = (total_good / total_files * 100) if total_files > 0 else 0
print('-'*70)
print(f'{"TOTAL":10} | Total:{total_files:3d} | Good:{total_good:3d} | Bad:{total_files-total_good:3d} | {overall_pct:5.1f}%')

print('\n' + '='*70)
print('MASALAH TERDETEKSI:')
print('='*70)

for cat in categories:
    if stats[cat]['issues']:
        print(f'\n{cat.upper()} - {len(stats[cat]["issues"])} file dengan masalah:')
        for fname, issues in stats[cat]['issues'][:8]:
            print(f'  {fname}')
            for issue in issues:
                print(f'    → {issue}')
        if len(stats[cat]['issues']) > 8:
            print(f'  ... plus {len(stats[cat]["issues"])-8} files lainnya')

print('\n' + '='*70)
print('SARAN:')
print('='*70)

if overall_pct >= 90:
    print('✓ Dataset BAIK - Lebih dari 90% file berkualitas')
    print('  Lanjutkan dengan preprocessing dan model training')
elif overall_pct >= 70:
    print('⚠ Dataset CUKUP - 70-90% file berkualitas')
    print('  Periksa file dengan masalah dan pertimbangkan re-recording')
else:
    print('✗ Dataset BERMASALAH - Kurang dari 70% file berkualitas')
    print('  Lakukan pengecekan hardware dan re-recording data')

# Check for dataset balance
print('\n' + '='*70)
print('KESEIMBANGAN DATASET:')
print('='*70)

for cat in categories:
    s = stats[cat]
    if s['total'] > 0:
        print(f'{cat:10}: {s["total"]} samples')
