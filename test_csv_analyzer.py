import os
import pandas as pd
import numpy as np
from pathlib import Path
import statistics

# Directory containing test CSV files
test_dir = Path("./test_csv")

print("=" * 80)
print("SMART GLOVE TEST DATA ANALYSIS")
print("=" * 80)
print()

# Get all CSV files
csv_files = sorted(list(test_dir.glob("*.csv")))
print(f"Found {len(csv_files)} CSV files:\n")
for f in csv_files:
    print(f"  - {f.name}")
print()

# Analyze each file
all_data = {}
summary_stats = []

for csv_file in csv_files:
    print(f"\n{'=' * 80}")
    print(f"Analyzing: {csv_file.name}")
    print(f"{'=' * 80}")
    
    df = pd.read_csv(csv_file)
    all_data[csv_file.name] = df
    
    # Basic info
    print(f"\n[FILE INFO]")
    print(f"  Shape: {df.shape} (rows, columns)")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Data types:\n{df.dtypes}")
    
    # Missing values
    print(f"\n[MISSING VALUES]")
    missing = df.isnull().sum()
    if missing.sum() == 0:
        print("  ✓ No missing values")
    else:
        print(f"  ✗ Missing values detected:\n{missing[missing > 0]}")
    
    # Timestamp analysis
    print(f"\n[TIMESTAMP ANALYSIS]")
    print(f"  First timestamp: {df['timestamp'].min()}")
    print(f"  Last timestamp: {df['timestamp'].max()}")
    print(f"  Duration: {df['timestamp'].max() - df['timestamp'].min()} ms")
    print(f"  Sampling points: {len(df)}")
    if len(df) > 1:
        time_diffs = df['timestamp'].diff().dropna()
        print(f"  Sample interval - Mean: {time_diffs.mean():.2f} ms, Std: {time_diffs.std():.2f} ms")
    
    # Repetition info
    print(f"\n[REPETITION INFO]")
    rep_counts = df['repetition'].value_counts().sort_index()
    print(f"  Unique repetitions: {df['repetition'].unique()}")
    print(f"  Repetition distribution:\n{rep_counts}")
    
    # Flex sensor analysis
    flex_cols = [col for col in df.columns if col.startswith('flex')]
    print(f"\n[FLEX SENSORS] ({len(flex_cols)} sensors)")
    print("  Value ranges:")
    for col in flex_cols:
        print(f"    {col}: [{df[col].min():.3f}, {df[col].max():.3f}] (μ={df[col].mean():.3f}, σ={df[col].std():.3f})")
    
    # Accelerometer analysis
    acc_cols = [col for col in df.columns if col.startswith('acc')]
    print(f"\n[ACCELEROMETER] ({len(acc_cols)} axes)")
    print("  Value ranges:")
    for col in acc_cols:
        print(f"    {col}: [{df[col].min():.3f}, {df[col].max():.3f}] (μ={df[col].mean():.3f}, σ={df[col].std():.3f})")
    
    # Gyroscope analysis
    gyro_cols = [col for col in df.columns if col.startswith('gyro')]
    print(f"\n[GYROSCOPE] ({len(gyro_cols)} axes)")
    print("  Value ranges:")
    for col in gyro_cols:
        print(f"    {col}: [{df[col].min():.3f}, {df[col].max():.3f}] (μ={df[col].mean():.3f}, σ={df[col].std():.3f})")
    
    # Data quality
    print(f"\n[DATA QUALITY CHECK]")
    outliers = 0
    for col in flex_cols + acc_cols + gyro_cols:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        col_outliers = len(df[(df[col] < lower_bound) | (df[col] > upper_bound)])
        outliers += col_outliers
    
    print(f"  Total potential outliers (IQR method): {outliers}")
    print(f"  Data completeness: {(1 - df.isnull().sum().sum() / (df.shape[0] * df.shape[1])) * 100:.2f}%")
    
    # Summary for comparison
    summary_stats.append({
        'File': csv_file.name,
        'Rows': len(df),
        'Duration_ms': df['timestamp'].max() - df['timestamp'].min(),
        'Flex_Range': f"[{df[flex_cols].min().min():.3f}, {df[flex_cols].max().max():.3f}]",
        'Acc_Range': f"[{df[acc_cols].min().min():.3f}, {df[acc_cols].max().max():.3f}]",
        'Gyro_Range': f"[{df[gyro_cols].min().min():.3f}, {df[gyro_cols].max().max():.3f}]",
    })

# Overall comparison
print(f"\n\n{'=' * 80}")
print("SUMMARY COMPARISON")
print(f"{'=' * 80}\n")

summary_df = pd.DataFrame(summary_stats)
print(summary_df.to_string(index=False))

print(f"\n\n[OVERALL STATISTICS]")
print(f"  Total files analyzed: {len(csv_files)}")
print(f"  Total data points: {sum(len(df) for df in all_data.values())}")
print(f"  Gesture classes detected: {sorted([int(f.name[0]) for f in csv_files])}")

print("\n" + "=" * 80)
print("Analysis complete! Data is ready for model training/testing.")
print("=" * 80)
