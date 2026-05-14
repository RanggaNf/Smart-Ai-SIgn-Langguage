#!/usr/bin/env python
"""
Quick start script untuk Smart Glove Real-Time Prediction
Cek dependencies dan setup, jalankan langsung
"""

import sys
import os
import subprocess

MODEL_DIR = r"C:\FOLDERKU\SmartGlove\model_output"
PREDICT_SCRIPT = r"C:\FOLDERKU\SmartGlove\smartglove_realtime_predict.py"
SIMULATOR_SCRIPT = r"C:\FOLDERKU\SmartGlove\test_realtime_simulator.py"

def check_model():
    """Check if model files exist"""
    files = ['model.pkl', 'scaler.pkl', 'meta.pkl']
    missing = []
    
    for f in files:
        fpath = os.path.join(MODEL_DIR, f)
        if not os.path.exists(fpath):
            missing.append(f)
    
    if missing:
        print("❌ Model files MISSING:")
        for f in missing:
            print(f"   - {f}")
        print(f"\n   Run training first: smartglove_predict (2).ipynb Cell 1-5")
        return False
    
    print("✓ Model files OK")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    packages = {
        'sklearn': 'scikit-learn',
        'pandas': 'pandas',
        'numpy': 'numpy',
        'matplotlib': 'matplotlib',
        'joblib': 'joblib',
    }
    
    missing = []
    for import_name, pkg_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)
    
    if missing:
        print(f"⚠️  Missing packages: {', '.join(missing)}")
        print("   Installing...\n")
        for pkg in missing:
            subprocess.run([sys.executable, '-m', 'pip', 'install', pkg, '-q'])
        print("✓ Dependencies installed")
    else:
        print("✓ All dependencies OK")
    
    return True

def main():
    print("""
╔════════════════════════════════════════════════════════╗
║  🧤 Smart Glove - Real-Time Gesture Prediction       ║
║          Quick Start Setup                             ║
╚════════════════════════════════════════════════════════╝
    """)
    
    print("🔍 Checking setup...\n")
    
    # Check dependencies
    print("[1/3] Checking dependencies...")
    if not check_dependencies():
        return 1
    
    # Check model
    print("\n[2/3] Checking model files...")
    if not check_model():
        return 1
    
    # Check scripts
    print("\n[3/3] Checking scripts...")
    for script in [PREDICT_SCRIPT]:
        if os.path.exists(script):
            print(f"✓ {os.path.basename(script)} OK")
        else:
            print(f"❌ {script} NOT FOUND")
            return 1
    
    print("\n" + "="*55)
    print("✓ Setup complete! Ready to run\n")
    
    print("📋 Quick Start Guide:\n")
    print("Option A: WITH Hardware (Data Collection App)")
    print("  1. Run: python smart_glove_data_collection.py")
    print("  2. Click START UDP SERVER")
    print("  3. Start performing gestures")
    print("  4. In new terminal: python smartglove_realtime_predict.py")
    print("  5. Click ▶ START LISTENING\n")
    
    print("Option B: WITHOUT Hardware (Simulator)")
    print("  1. Terminal 1: python test_realtime_simulator.py --sequence")
    print("  2. Terminal 2: python smartglove_realtime_predict.py")
    print("  3. Click ▶ START LISTENING\n")
    
    print("=" * 55)
    
    # Ask what to run
    print("\nWhat would you like to do?")
    print("  1. Run predictor app")
    print("  2. Run simulator (test mode)")
    print("  3. Show documentation")
    print("  4. Exit\n")
    
    choice = input("Enter choice (1-4): ").strip()
    
    if choice == '1':
        print("\n▶ Starting predictor app...")
        os.system(f'python "{PREDICT_SCRIPT}"')
    
    elif choice == '2':
        print("\n▶ Starting test simulator...")
        os.system(f'python "{SIMULATOR_SCRIPT}" --sequence --repeat 3')
    
    elif choice == '3':
        doc_file = r"C:\FOLDERKU\SmartGlove\REALTIME_PREDICT_SETUP.md"
        if os.path.exists(doc_file):
            with open(doc_file, 'r', encoding='utf-8') as f:
                print(f.read())
        else:
            print("Documentation not found")
    
    else:
        print("Exiting...")
        return 0
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
