#!/usr/bin/env python
"""Test import dari advanced_gesture_recognition"""

import sys
import traceback

print("Python:", sys.version)
print("Path:", sys.path[:3])
print()

try:
    print("1. Import basic libraries...")
    import os, json, warnings
    import numpy as np
    import pandas as pd
    import tensorflow as tf
    from tensorflow import keras
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report
    import matplotlib.pyplot as plt
    import seaborn as sns
    from pathlib import Path
    print("   ✓ Basic imports OK")
except Exception as e:
    print(f"   ✗ Error: {e}")
    traceback.print_exc()
    sys.exit(1)

print()
try:
    print("2. Import advanced_gesture_recognition...")
    from advanced_gesture_recognition import (
        build_bilstm_attention_model,
        build_tcn_model,
        GloveSensorPreprocessor,
        AdaptiveGestureSegmenter,
        GrammarPostprocessor,
        RealtimeInferenceEngine,
        ProductionInferenceEngine,
        AttentionLayer,
        CATEGORY_WINDOW,
        CONFIDENCE_THRESHOLD,
        NUM_TOTAL_FEATURES,
        SAMPLING_RATE,
    )
    print("   ✓ advanced_gesture_recognition import OK")
except Exception as e:
    print(f"   ✗ Error: {e}")
    print("\nTraceback:")
    traceback.print_exc()
    print("\nMencoba debug...")
    try:
        import advanced_gesture_recognition as agr
        print(f"\nModule attributes: {dir(agr)}")
    except Exception as e2:
        print(f"Module load error: {e2}")
        traceback.print_exc()
    sys.exit(1)

print()
print("3. Testing constants...")
print(f"   SAMPLING_RATE: {SAMPLING_RATE}")
print(f"   NUM_TOTAL_FEATURES: {NUM_TOTAL_FEATURES}")
print(f"   CATEGORY_WINDOW: {CATEGORY_WINDOW}")
print(f"   CONFIDENCE_THRESHOLD: {CONFIDENCE_THRESHOLD}")

print()
print("✓ Semua import berhasil!")
