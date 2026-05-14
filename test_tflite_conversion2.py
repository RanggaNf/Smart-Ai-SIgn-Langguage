import tensorflow as tf
import os
from advanced_gesture_recognition import AttentionLayer

models_dir = 'hierarchical_models'
model_names = ['category_classifier', 'angka_gesture_model', 'frasa_gesture_model', 'huruf_gesture_model', 'kata_gesture_model']

for model_name in model_names:
    model_path = f'{models_dir}/{model_name}.keras'
    
    if not os.path.exists(model_path):
        print(f"✗ File not found: {model_path}")
        continue
    
    try:
        print(f"\n{'='*60}")
        print(f"Loading: {model_name}")
        print(f"{'='*60}")
        
        model = tf.keras.models.load_model(model_path, custom_objects={'AttentionLayer': AttentionLayer})
        print(f"✓ Model loaded successfully")
        
        # Try conversion - dengan new converter (tanpa experimental_new_converter=False)
        print(f"Converting to TFLite...")
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        # JANGAN gunakan experimental_new_converter = False
        # converter.experimental_new_converter = False  # Ini bisa bikin error di Windows
        
        # Tapi TETAP gunakan SELECT_TF_OPS untuk BiLSTM support
        converter.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS,
            tf.lite.OpsSet.SELECT_TF_OPS
        ]
        
        tflite_model = converter.convert()
        print(f"✓ Conversion successful")
        print(f"  TFLite size: {len(tflite_model) / 1024:.1f} KB")
        
        # Save it
        output_name = model_name.replace('_model', '').replace('_gesture', '_gesture')
        output_path = f'{models_dir}/{output_name}_f32.tflite'
        with open(output_path, 'wb') as f:
            f.write(tflite_model)
        print(f"✓ Saved to: {output_path}")
        
    except Exception as e:
        print(f"✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}")
print("Verifying TFLite files:")
print(f"{'='*60}")
import glob
tflite_files = glob.glob(f'{models_dir}/*.tflite')
if tflite_files:
    for f in sorted(tflite_files):
        size_kb = os.path.getsize(f) / 1024
        print(f"  ✓ {os.path.basename(f)} ({size_kb:.1f} KB)")
else:
    print("  (No TFLite files found)")
