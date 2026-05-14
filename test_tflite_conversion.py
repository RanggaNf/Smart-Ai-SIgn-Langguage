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
        
        # Try conversion
        print(f"Converting to TFLite...")
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.experimental_new_converter = False
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
print("Files in hierarchical_models:")
print(f"{'='*60}")
os.system("dir hierarchical_models | findstr tflite")
