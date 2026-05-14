import os
import shutil
from pathlib import Path
from collections import defaultdict

# Define paths
datashet1_path = Path("datashet1")
datashet2_path = Path("datashet2")
output_path = Path("datashetfiks")

# Create output directory
output_path.mkdir(exist_ok=True)

# Category folders
categories = ["angka", "frasa", "huruf", "kata", "kontrol"]

for category in categories:
    cat_path1 = datashet1_path / category
    cat_path2 = datashet2_path / category
    cat_output = output_path / category
    
    # Create category folder in output
    cat_output.mkdir(exist_ok=True)
    
    if not cat_path2.exists():
        print(f"⚠️  {category} tidak ada di datashet2, skip")
        continue
    
    print(f"\n📁 Memproses: {category}")
    
    # Get labels (filenames without _rep and timestamp) from datashet2
    labels_in_ds2 = set()
    files_in_ds2 = defaultdict(list)
    
    for file in cat_path2.iterdir():
        if file.is_file() and file.suffix == '.csv':
            # Extract label: remove _rep*_timestamp.csv
            parts = file.stem.split('_rep')
            label = parts[0]
            labels_in_ds2.add(label)
            files_in_ds2[label].append(file)
    
    print(f"   Label di datashet2: {len(labels_in_ds2)}")
    
    # First, copy all files from datashet2
    for label, files in files_in_ds2.items():
        for file in files:
            shutil.copy2(file, cat_output / file.name)
    
    print(f"   ✓ Copied {sum(len(files) for files in files_in_ds2.values())} files dari datashet2")
    
    # Now, add files from datashet1 that match labels in datashet2
    if cat_path1.exists():
        added_count = 0
        for file in cat_path1.iterdir():
            if file.is_file() and file.suffix == '.csv':
                # Extract label
                parts = file.stem.split('_rep')
                label = parts[0]
                
                # Only copy if label exists in datashet2
                if label in labels_in_ds2:
                    # Check if file doesn't already exist with exact name
                    output_file = cat_output / file.name
                    if not output_file.exists():
                        shutil.copy2(file, output_file)
                        added_count += 1
        
        print(f"   ✓ Added {added_count} files dari datashet1")
    
    # Show summary for this category
    total_files = len(list(cat_output.glob("*.csv")))
    print(f"   📊 Total files: {total_files}")

print("\n" + "="*50)
print(f"✅ Merge selesai!")
print(f"📁 Folder {output_path} telah dibuat")
print("="*50)

# Print summary
for category in categories:
    cat_output = output_path / category
    if cat_output.exists():
        file_count = len(list(cat_output.glob("*.csv")))
        label_count = len(set(f.stem.split('_rep')[0] for f in cat_output.glob("*.csv")))
        print(f"  {category:12} - {label_count:3} labels, {file_count:4} files")
