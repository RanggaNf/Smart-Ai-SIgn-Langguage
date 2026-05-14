"""
Data Augmentation Script untuk Smart Glove 3-Repetition Strategy
Mengubah 3 repetisi per gesture menjadi ~9 variasi menggunakan:
- Rotation augmentation (jari rotasi ±5°)
- Time warping (speed variation ±10%)
- Jitter (noise addition ±2%)
- Mixing (blend 2 samples)

Gunakan script ini SETELAH semua gesture 3x sudah terekam.
"""

import os
import csv
import numpy as np
from pathlib import Path
import json
from datetime import datetime
import shutil

class DataAugmenter:
    def __init__(self, base_path="datashet", output_path="datashet_augmented"):
        self.base_path = base_path
        self.output_path = output_path
        self.augmentation_count = 0
        
        # Create output directory
        os.makedirs(output_path, exist_ok=True)
    
    def load_csv(self, filepath):
        """Load CSV gesture data"""
        data = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        return data
    
    def save_csv(self, filepath, header, data_rows):
        """Save data to CSV"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(data_rows)
    
    def rotate_gesture(self, data, angle_degrees=3):
        """
        Augmentation 1: Rotation
        Rotasi gesture dengan angle tertentu (±3-5 degrees)
        Membuat posisi jari sedikit miring, simulasi natural variation
        """
        augmented = []
        angle_rad = np.radians(angle_degrees)
        
        for row in data:
            new_row = row.copy()
            
            # Rotation matrix 2D untuk flex sensors (representasi 2D)
            # Rotasi memperkecil beberapa flex, memperbesar yang lain
            rotation_factor = np.cos(angle_rad)
            
            # Apply rotation ke flex sensors
            for i in range(1, 6):
                flex_key_L = f'flex{i}_L'
                flex_key_R = f'flex{i}_R'
                
                if flex_key_L in row:
                    try:
                        val = float(row[flex_key_L])
                        # Slight variation dari rotation
                        new_val = val * (rotation_factor + 0.02) 
                        new_row[flex_key_L] = str(min(1.0, max(0.0, new_val)))
                    except:
                        pass
                
                if flex_key_R in row:
                    try:
                        val = float(row[flex_key_R])
                        new_val = val * (rotation_factor + 0.02)
                        new_row[flex_key_R] = str(min(1.0, max(0.0, new_val)))
                    except:
                        pass
            
            augmented.append(new_row)
        
        return augmented
    
    def time_warp(self, data, speed_factor=1.08):
        """
        Augmentation 2: Time Warping
        Ubah kecepatan gesture (mempercepat atau memperlambat sampai 10%)
        Menggunakan interpolasi untuk resample data
        """
        # Convert string values to floats
        numeric_data = []
        for row in data:
            numeric_row = {}
            for key, val in row.items():
                try:
                    numeric_row[key] = float(val) if key != 'timestamp' and key != 'repetition' else val
                except:
                    numeric_row[key] = val
            numeric_data.append(numeric_row)
        
        # Original length
        n_original = len(numeric_data)
        n_new = int(n_original / speed_factor)
        
        # Interpolate
        warped = []
        indices = np.linspace(0, n_original - 1, n_new)
        
        for idx in indices:
            # Linear interpolation
            idx_low = int(idx)
            idx_high = min(idx_low + 1, n_original - 1)
            weight = idx - idx_low
            
            interpolated_row = {}
            
            # Interpolate numeric values
            for key in numeric_data[0]:
                if key == 'timestamp' or key == 'repetition':
                    interpolated_row[key] = numeric_data[idx_low][key]
                else:
                    try:
                        val_low = float(numeric_data[idx_low][key])
                        val_high = float(numeric_data[idx_high][key])
                        interpolated_val = val_low + (val_high - val_low) * weight
                        interpolated_row[key] = str(interpolated_val)
                    except:
                        interpolated_row[key] = numeric_data[idx_low][key]
            
            warped.append(interpolated_row)
        
        return warped
    
    def add_jitter(self, data, noise_scale=0.02):
        """
        Augmentation 3: Jitter/Noise
        Tambahkan random noise kecil ke sensor (±2%)
        Simulasi natural sensor variation
        """
        jittered = []
        
        for row in data:
            new_row = row.copy()
            
            # Add jitter ke flex sensors
            for i in range(1, 6):
                flex_key_L = f'flex{i}_L'
                flex_key_R = f'flex{i}_R'
                
                noise_L = np.random.normal(0, noise_scale)
                noise_R = np.random.normal(0, noise_scale)
                
                if flex_key_L in row:
                    try:
                        val = float(row[flex_key_L])
                        new_val = val + noise_L
                        new_row[flex_key_L] = str(min(1.0, max(0.0, new_val)))
                    except:
                        pass
                
                if flex_key_R in row:
                    try:
                        val = float(row[flex_key_R])
                        new_val = val + noise_R
                        new_row[flex_key_R] = str(min(1.0, max(0.0, new_val)))
                    except:
                        pass
            
            # Add jitter ke accel/gyro
            for axis in ['X', 'Y', 'Z']:
                for sensor_type in ['acc', 'gyro']:
                    for hand in ['L', 'R']:
                        key = f'{sensor_type}{axis}_{hand}'
                        noise = np.random.normal(0, noise_scale)
                        if key in row:
                            try:
                                val = float(row[key])
                                new_val = val + noise
                                new_row[key] = str(new_val)
                            except:
                                pass
            
            jittered.append(new_row)
        
        return jittered
    
    def mix_samples(self, data1, data2, alpha=0.7):
        """
        Augmentation 4: Mixing
        Mix 2 gesture samples dengan weighted average
        Membuat semi-gesture yang belum pernah ada
        """
        if len(data1) != len(data2):
            # Resample yang lebih pendek
            min_len = min(len(data1), len(data2))
            data1 = data1[:min_len]
            data2 = data2[:min_len]
        
        mixed = []
        
        for row1, row2 in zip(data1, data2):
            mixed_row = row1.copy()
            
            # Mix flex sensors
            for i in range(1, 6):
                flex_key_L = f'flex{i}_L'
                flex_key_R = f'flex{i}_R'
                
                for key in [flex_key_L, flex_key_R]:
                    if key in row1 and key in row2:
                        try:
                            val1 = float(row1[key])
                            val2 = float(row2[key])
                            mixed_val = val1 * alpha + val2 * (1 - alpha)
                            mixed_row[key] = str(min(1.0, max(0.0, mixed_val)))
                        except:
                            pass
            
            # Mix accel/gyro
            for axis in ['X', 'Y', 'Z']:
                for sensor_type in ['acc', 'gyro']:
                    for hand in ['L', 'R']:
                        key = f'{sensor_type}{axis}_{hand}'
                        if key in row1 and key in row2:
                            try:
                                val1 = float(row1[key])
                                val2 = float(row2[key])
                                mixed_val = val1 * alpha + val2 * (1 - alpha)
                                mixed_row[key] = str(mixed_val)
                            except:
                                pass
            
            mixed.append(mixed_row)
        
        return mixed
    
    def augment_gesture_file(self, original_filepath, gesture_type, gesture_label):
        """Augment single gesture file 3x dengan berbagai methods"""
        print(f"\n  Augmenting: {Path(original_filepath).name}")
        
        # Load original data
        data = self.load_csv(original_filepath)
        header_dict = None
        
        # Baca header
        with open(original_filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                header = list(reader.fieldnames)
        
        # Get repetition number from original
        try:
            rep_match = Path(original_filepath).stem.split('_rep')
            if len(rep_match) > 1:
                original_rep = int(rep_match[1])
            else:
                original_rep = 1
        except:
            original_rep = 1
        
        timestamp_now = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # AUGMENTATION 1: Rotation
        rotated = self.rotate_gesture(data, angle_degrees=4)
        aug1_filename = f"{gesture_label}_rep{original_rep + 3}_rot_{timestamp_now}.csv"
        aug1_path = os.path.join(self.output_path, gesture_type, aug1_filename)
        self.save_csv(aug1_path, header, rotated)
        print(f"    ✓ Saved: {aug1_filename}")
        self.augmentation_count += 1
        
        # AUGMENTATION 2: Time Warp (Speed up)
        warped_fast = self.time_warp(data, speed_factor=1.08)
        aug2_filename = f"{gesture_label}_rep{original_rep + 6}_warp_{timestamp_now}.csv"
        aug2_path = os.path.join(self.output_path, gesture_type, aug2_filename)
        self.save_csv(aug2_path, header, warped_fast)
        print(f"    ✓ Saved: {aug2_filename}")
        self.augmentation_count += 1
        
        # AUGMENTATION 3: Jitter
        jittered = self.add_jitter(data, noise_scale=0.015)
        aug3_filename = f"{gesture_label}_rep{original_rep + 9}_jitter_{timestamp_now}.csv"
        aug3_path = os.path.join(self.output_path, gesture_type, aug3_filename)
        self.save_csv(aug3_path, header, jittered)
        print(f"    ✓ Saved: {aug3_filename}")
        self.augmentation_count += 1
        
        return 3  # Return number of augmentations created
    
    def run(self):
        """Run full augmentation pipeline"""
        print("=" * 60)
        print("SMART GLOVE DATA AUGMENTATION")
        print("=" * 60)
        print(f"\nSource directory: {self.base_path}")
        print(f"Output directory: {self.output_path}")
        print(f"\nStrategy: 3 repetitions × 3 augmentations = 9 total samples per gesture")
        print("\nAugmentation methods:")
        print("  1. ROTATION (±4°) - gesture sedikit miring")
        print("  2. TIME WARPING (±8% speed) - gesture lebih cepat/lambat")
        print("  3. JITTER (±1.5% noise) - sensor natural variation")
        print("\n" + "=" * 60)
        
        total_originals = 0
        total_augmented = 0
        
        # Scan all categories
        for category in os.listdir(self.base_path):
            category_path = os.path.join(self.base_path, category)
            
            if not os.path.isdir(category_path):
                continue
            
            print(f"\n📁 Category: {category.upper()}")
            
            # Create output category directory
            out_category_path = os.path.join(self.output_path, category)
            os.makedirs(out_category_path, exist_ok=True)
            
            # Copy original files first
            for filename in os.listdir(category_path):
                if filename.endswith('.csv'):
                    src = os.path.join(category_path, filename)
                    dst = os.path.join(out_category_path, filename)
                    shutil.copy2(src, dst)
            
            # Process each gesture
            gesture_files = [f for f in os.listdir(category_path) if f.endswith('.csv')]
            
            for csv_file in gesture_files:
                filepath = os.path.join(category_path, csv_file)
                
                # Parse filename: [gesture_label]_rep[N]_[timestamp].csv
                parts = csv_file.split('_rep')
                if len(parts) == 2:
                    gesture_label = parts[0]
                    
                    # Augment this file
                    n_aug = self.augment_gesture_file(filepath, category, gesture_label)
                    total_originals += 1
                    total_augmented += n_aug
        
        # Summary
        print("\n" + "=" * 60)
        print("AUGMENTATION COMPLETE!")
        print("=" * 60)
        print(f"\n✓ Original samples copied: {total_originals}")
        print(f"✓ Augmented samples created: {total_augmented}")
        print(f"✓ Total available: {total_originals + total_augmented}")
        print(f"✓ Augmentation factor: {(total_originals + total_augmented) / total_originals:.1f}x")
        
        print(f"\n📂 Augmented data saved to: {os.path.abspath(self.output_path)}")
        print("\n✅ Ready for training!")
        print("=" * 60)


if __name__ == "__main__":
    # Configuration
    BASE_PATH = r"C:\FOLDERKU\SmartGlove\datashet"  # Original 3-rep data
    OUTPUT_PATH = r"C:\FOLDERKU\SmartGlove\datashet_augmented"  # Output augmented data
    
    # Run augmentation
    augmenter = DataAugmenter(BASE_PATH, OUTPUT_PATH)
    augmenter.run()
    
    print("\nNext steps:")
    print("1. Review augmented data in datashet_augmented/")
    print("2. Use augmented data for training model")
    print("3. Check if augmentation improves model accuracy")
