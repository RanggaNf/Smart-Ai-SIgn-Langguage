# SmartGlove v3 - Hierarchical Model Android Implementation Guide

## 📱 Overview

```
SENSOR (Raw ADC Data)
         ↓ [WiFi TCP]
    ESP32 Master
         ↓ [Android receives RAW ADC]
  Android App
    ├─ STAGE 1: Calibration
    │  └─ Convert raw ADC → normalized [0-1]
    ├─ STAGE 2: Feature Extraction
    │  └─ Compute delta & acceleration (66 features)
    ├─ STAGE 3: Category Detection
    │  └─ 4-class: ANGKA/HURUF/KATA/FRASA
    └─ STAGE 4: Gesture Classification
       └─ Specialized model per category
```

---

## 🔧 Data Format & Calibration

### Data Received from ESP32 Master

**Format:** JSON via TCP (8080)
```json
{
  "flex": [ADC1, ADC2, ADC3, ADC4, ADC5],
  "accel": [AX, AY, AZ],
  "gyro": [GX, GY, GZ],
  "battery": 4.2,
  "timestamp": 1712345678000
}
```

**Field Details:**
- `flex[5]`: Raw ADC readingsfrom 5 flex sensors (0-4095)
- `accel[3]`: Raw accelerometer from MPU6050 (-32768 to 32767)
- `gyro[3]`: Raw gyroscope from MPU6050 (-32768 to 32767)
- `battery`: Battery voltage (V)
- `timestamp`: Milliseconds

### Step 1: Flex Sensor Calibration

**Purpose:** Convert raw ADC [0-4095] → normalized [-1.0, 1.0]

**Formula:**
```
normalized = (raw_adc - flex_min) / (flex_max - flex_min)
clamped = max(-1.0, min(1.0, normalized))
```

**Calibration Procedure (First Time Setup):**

1. **Straight Hand Position:**
   - Keep hand fully extended (all fingers straight)
   - Flex sensors should be in MIN position (smallest ADC value)
   - Record 30 frames, take average→ **flex_min[i]**

2. **Curved Hand Position:**
   - Make tight fist (all fingers fully bent)
   - Flex sensors should be in MAX position (largest ADC value)
   - Record 30 frames, take average → **flex_max[i]**

3. **Store Calibration:**
   - Save `flex_min[5]` and `flex_max[5]` to Android SharedPreferences
   - Or embedded in app as constants (see Default Values below)

**Default Values (if calibration not done):**
```
Thumb:    min=1200, max=2800
Index:    min=1300, max=2900
Middle:   min=1450, max=3100
Ring:     min=1250, max=2600
Pinky:    min=1200, max=2500
```

**Android Code (Kotlin):**
```kotlin
class FlexCalibrator {
    private val flexMin = FloatArray(5)
    private val flexMax = FloatArray(5)
    
    fun calibrateMin(adcValues: IntArray) {
        // Record 30 frames with straight hand, average them
        flexMin = adcValues.map { it.toFloat() }.toFloatArray()
        saveToPrefs("flex_min", flexMin)
    }
    
    fun calibrateMax(adcValues: IntArray) {
        // Record 30 frames with clenched fist, average them
        flexMax = adcValues.map { it.toFloat() }.toFloatArray()
        saveToPrefs("flex_max", flexMax)
    }
    
    fun normalize(rawAdc: IntArray): FloatArray {
        return FloatArray(5) { i ->
            val normalized = (rawAdc[i] - flexMin[i]) / (flexMax[i] - flexMin[i])
            normalized.coerceIn(-1f, 1f)
        }
    }
    
    private fun saveToPrefs(key: String, values: FloatArray) {
        val prefs = context.getSharedPreferences("glove_calibration", 0)
        prefs.edit().putString(key, values.joinToString(",")).apply()
    }
}
```

---

### Step 2: MPU6050 Calibration

**Purpose:** Offset raw IMU values to remove sensor bias

**Calibration Procedure:**

1. **Resting Calibration (First Time or Weekly):**
   - Place hand on flat table (perfectly still)
   - Record 100 frames without any motion
   - Compute mean values → `accel_offset` & `gyro_offset`

2. **Formula:**
```
accel_calibrated = (raw_accel / 16384.0) - accel_offset  [in g]
gyro_calibrated  = (raw_gyro / 131.0) - gyro_offset      [in deg/s]
```

**Android Code:**
```kotlin
class IMUCalibrator {
    private lateinit var accelOffset: FloatArray
    private lateinit var gyroOffset: FloatArray
    
    fun calibrate(frames: List<IMUData>) {
        // frames[i] = [ax, ay, az, gx, gy, gz] raw values
        accelOffset = FloatArray(3)
        gyroOffset = FloatArray(3)
        
        for (i in 0..2) {
            accelOffset[i] = frames.map { it.accel[i] / 16384.0f }.average().toFloat()
            gyroOffset[i] = frames.map { it.gyro[i] / 131.0f }.average().toFloat()
        }
        saveToPrefs("imu_accel_offset", accelOffset)
        saveToPrefs("imu_gyro_offset", gyroOffset)
    }
    
    fun calibrate(rawAccel: IntArray, rawGyro: IntArray): Pair<FloatArray, FloatArray> {
        val accel = FloatArray(3) { i -> rawAccel[i] / 16384f - accelOffset[i] }
        val gyro = FloatArray(3) { i -> rawGyro[i] / 131f - gyroOffset[i] }
        return Pair(accel, gyro)
    }
}
```

---

## 🎯 Feature Extraction (66 Features)

### Raw Features: 22 channels
```
1-5:   Normalized flex sensors (Thumb, Index, Middle, Ring, Pinky)
6-8:   Calibrated accelerometer (Ax, Ay, Az) [g]
9-11:  Calibrated gyroscope (Gx, Gy, Gz) [deg/s]
12-22: Reserved for future sensors
```

### Delta Features: 22 channels (velocity)
```
23-44: Derivative (rate of change) of raw 22 channels
```

### Acceleration Features: 22 channels (second derivative)
```
45-66: Second derivative of raw 22 channels
```

**Android Code:**
```kotlin
class FeatureExtractor(val windowSize: Int) {
    private val preprocessor = GloveSensorPreprocessor()
    
    fun extract(
        flex: FloatArray,
        accel: FloatArray,
        gyro: FloatArray
    ): FloatArray {
        // 1. Concatenate all 22 raw channels
        val raw = FloatArray(22)
        System.arraycopy(flex, 0, raw, 0, 5)      // flex: 0-4
        System.arraycopy(accel, 0, raw, 5, 3)     // accel: 5-7
        System.arraycopy(gyro, 0, raw, 8, 3)      // gyro: 8-10
        // channels 11-21: padding/reserved = 0
        
        // 2. Compute deltas (velocity)
        val delta = computeDelta(raw)
        
        // 3. Compute acceleration (second derivative)
        val accelFeatures = computeAcceleration(delta)
        
        // 4. Concatenate: [raw 22] + [delta 22] + [accel 22]
        val all66 = FloatArray(66)
        System.arraycopy(raw, 0, all66, 0, 22)
        System.arraycopy(delta, 0, all66, 22, 22)
        System.arraycopy(accelFeatures, 0, all66, 44, 22)
        
        // 5. Apply preprocessor normalization
        return preprocessor.transform(all66, windowSize)
    }
    
    private fun computeDelta(raw: FloatArray): FloatArray {
        // delta[i] = (raw[i] - raw[i-1]) / dt
        // Simplified: assume uniform sampling
        return FloatArray(22) { i ->
            if (i == 0) 0f else (raw[i] - raw[i-1]) / 0.01f  // 100 Hz sampling
        }
    }
    
    private fun computeAcceleration(delta: FloatArray): FloatArray {
        // accel[i] = (delta[i] - delta[i-1]) / dt
        return FloatArray(22) { i ->
            if (i == 0) 0f else (delta[i] - delta[i-1]) / 0.01f
        }
    }
}
```

---

## 🧠 Model Inference

### Stage 1: Category Classifier

**Input:** 80-frame window × 66 features (normalized)  
**Output:** 4 probabilities [ANGKA, FRASA, HURUF, KATA]

```kotlin
val categoryProbs = categoryClassifier.predict(input80x66)
// categoryProbs = [0.02, 0.05, 0.08, 0.85]  → KATA (85%)
```

### Stage 2: Gesture Classifier (Per Category)

**Select Model Based on Category:**
```kotlin
val topCategory = categoryProbs.withIndex().maxByOrNull { it.value }?.index
val categoryName = listOf("ANGKA", "FRASA", "HURUF", "KATA")[topCategory]

// Load appropriate gesture classifier
val gestureModel = when(categoryName) {
    "ANGKA" -> angkaGestureClassifier    // 15 gestures
    "FRASA" -> frasaGestureClassifier    // 13 gestures
    "HURUF" -> hurufGestureClassifier    // 26 gestures
    "KATA"  -> kataGestureClassifier     // 79 gestures
}

val gestureProbs = gestureModel.predict(input)
val topGesture = gestureProbs.withIndex().maxByOrNull { it.value }?.index
val gestureName = gestures[topGesture]
val confidence = gestureProbs[topGesture]
```

---

## 📊 Motion Detection & Gesture Segmentation

### 3-Layer Protection (Avoid False Positives)

```kotlin
class MotionDetector {
    private val threshold = 0.3f
    private val motionHistory = mutableListOf<Float>()
    
    fun isMotionDetected(frame: FloatArray): Boolean {
        // Compute motion magnitude = sum of absolute deltas
        val motion = frame.drop(22).take(22)  // Use delta features (22-44)
            .sumOf { kotlin.math.abs(it).toDouble() }
            .toFloat()
        
        motionHistory.add(motion)
        if (motionHistory.size > 5) motionHistory.removeAt(0)
        
        val avgMotion = motionHistory.average().toFloat()
        return avgMotion > threshold
    }
}

class GestureSegmenter {
    private val minFrames = 20    // ~200ms @ 100Hz
    private val maxFrames = 300   // ~3s @ 100Hz
    private val gestureBuffer = mutableListOf<FloatArray>()
    
    fun addFrame(frame: FloatArray, isMotion: Boolean): FloatArray? {
        if (isMotion) {
            gestureBuffer.add(frame)
            if (gestureBuffer.size > maxFrames)
                gestureBuffer.removeAt(0)
            return null  // Still accumulating
        } else {
            // Motion stopped
            if (gestureBuffer.size >= minFrames) {
                val gesture = gestureBuffer.toTypedArray()
                gestureBuffer.clear()
                return gesture  // Gesture complete
            }
            gestureBuffer.clear()
            return null  // Gesture too short
        }
    }
}

class ReleaseStateDetector {
    private val restThreshold = 0.1f
    private var restFrameCount = 0
    
    fun isResting(motionMagnitude: Float): Boolean {
        if (motionMagnitude < restThreshold)
            restFrameCount++
        else
            restFrameCount = 0
        
        return restFrameCount > 5  // Confirm 5 frames at rest
    }
}
```

---

## 📱 Android App Workflow

### Initialization
```kotlin
// 1. Load calibration
val flexCalibrator = FlexCalibrator()
val imuCalibrator = IMUCalibrator()
flexMin = loadFromPrefs("flex_min")
flexMax = loadFromPrefs("flex_max")
accelOffset = loadFromPrefs("imu_accel_offset")
gyroOffset = loadFromPrefs("imu_gyro_offset")

// 2. Load TFLite models
categoryClassifier = TFLiteInterpreter("category_classifier_f32.tflite")
angkaGestureClassifier = TFLiteInterpreter("angka_gesture_f32.tflite")
kataGestureClassifier = TFLiteInterpreter("kata_gesture_f32.tflite")
// ... etc

// 3. Setup detectors
motionDetector = MotionDetector()
gestureSegmenter = GestureSegmenter()
releaseDetector = ReleaseStateDetector()

// 4. Connect TCP to ESP32
tcpClient.connect("192.168.43.1", 8080)
```

### Real-Time Processing
```kotlin
fun onNewSensorData(jsonData: String) {
    // 1. Parse JSON
    val data = JSONObject(jsonData)
    val flexRaw = data.getJSONArray("flex").toIntArray()
    val accelRaw = data.getJSONArray("accel").toIntArray()
    val gyroRaw = data.getJSONArray("gyro").toIntArray()
    
    // 2. Calibrate
    val flex = flexCalibrator.normalize(flexRaw)
    val (accel, gyro) = imuCalibrator.calibrate(accelRaw, gyroRaw)
    
    // 3. Extract 66 features
    val features = featureExtractor.extract(flex, accel, gyro)
    
    // 4. Motion detection
    val motionMag = features.drop(22).take(22).sumOf { abs(it.toDouble()) }.toFloat()
    val isMotion = motionDetector.isMotionDetected(features)
    val isResting = releaseDetector.isResting(motionMag)
    
    if (isResting) {
        log("Hand resting - skip classification")
        return
    }
    
    // 5. Segment gesture
    val gestureSeq = gestureSegmenter.addFrame(features, isMotion)
    if (gestureSeq == null) return  // Still accumulating or invalid
    
    // 6. Categorize
    val categoryProbs = categoryClassifier.predict(gestureSeq)
    val topCat = categoryProbs.withIndex().maxByOrNull { it.value }?.index ?: return
    
    // 7. Gesture classify
    val gestureModel = selectGestureModel(topCat)
    val gestureProbs = gestureModel.predict(gestureSeq)
    val topGesture = gestureProbs.withIndex().maxByOrNull { it.value }?.index ?: return
    val confidence = gestureProbs[topGesture]
    
    // 8. Output result
    if (confidence > 0.7) {
        val result = GestureResult(
            gesture = gestureNames[topGesture],
            category = categoryNames[topCat],
            confidence = confidence
        )
        onGestureDetected(result)
    }
}
```

---

## 🔌 ESP32 Master Arduino Configuration

See `GLoveMasterAndroid.ino` - updated to send raw ADC data via TCP.

**Key Changes:**
```c
// Send raw ADC (not calibrated) to Android
void sendToAndroid() {
    StaticJsonDocument<200> doc;
    doc["flex"][0] = analogRead(FLEX_PIN_1);
    doc["flex"][1] = analogRead(FLEX_PIN_2);
    doc["flex"][2] = analogRead(FLEX_PIN_3);
    doc["flex"][3] = analogRead(FLEX_PIN_4);
    doc["flex"][4] = analogRead(FLEX_PIN_5);
    
    int16_t ax, ay, az, gx, gy, gz;
    mpuGetMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    doc["accel"][0] = ax;
    doc["accel"][1] = ay;
    doc["accel"][2] = az;
    doc["gyro"][0] = gx;
    doc["gyro"][1] = gy;
    doc["gyro"][2] = gz;
    
    doc["battery"] = getBatteryVoltage();
    doc["timestamp"] = millis();
    
    String json;
    serializeJson(doc, json);
    tcpClient.println(json);
}
```

---

## 🎓 Calibration Guide for Users

### First Time Setup (Android App)

1. **Launch App** → Grant permissions
2. **Pair ESP32** → Connect to SmartGlove hotspot
3. **Go to Settings** → **Calibration**

### Flex Sensor Calibration

**Screen 1: Straight Hand**
- Instructions: "Keep hand fully extended. All fingers STRAIGHT. Ready?"
- Button: "START RECORDING"
- Records 30 frames → shows "✓ MIN recorded"
- Flex sensor values should be LOW (e.g., 1200-1500)

**Screen 2: Curved Hand**
- Instructions: "Make a tight FIST. Press all fingers. Ready?"
- Button: "START RECORDING"
- Records 30 frames → shows "✓ MAX recorded"
- Flex sensor values should be HIGH (e.g., 2500-3000)

**Result:** Display calibration graph showing normalized range

### IMU Calibration

**Screen 3: Resting Calibration**
- Instructions: "Place hand on flat table. Keep STILL. No motion."
- Button: "CALIBRATE IMU"
- Records 100 frames → computes offsets
- Shows: "✓ Calibration complete"

### Verification

**Screen 4: Live Preview**
- Display normalized flex values [0-1]
- Display accelerometer [g]
- Display gyroscope [deg/s]
- "If values look reasonable, tap SAVE"

---

## 📦 File Structure

```
hierarchical_models/
├── category_classifier_f32.tflite
├── angka_gesture_f32.tflite
├── huruf_gesture_f32.tflite
├── kata_gesture_f32.tflite
├── frasa_gesture_f32.tflite
├── metadata.json
├── ANDROID_IMPLEMENTATION.md ← YOU ARE HERE
└── CALIBRATION_PROTOCOL.md (optional)
```

---

## 🐛 Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| False gestures while resting | Calibration wrong | Re-calibrate flex sensors |
| Low accuracy | Bad feature extraction | Check numpy implementation |
| App crashes on inference | Model not loaded | Verify .tflite files exist |
| TCP disconnection | WiFi interference | Move closer to router |
| Flex values stuck | Sensor dirty | Clean sensor pads |

---

## 📚 References

- Model Training: `Hierarchical_Gesture_Training.ipynb`
- Arduino Code: `GLoveMasterAndroid.ino`
- Python Preprocessing: `advanced_gesture_recognition.py`
- Sensor Augmentation: `sensor_augmentation.py`

---

**Last Updated:** April 5, 2026  
**Version:** 3.0 - Hierarchical  
**Status:** Production Ready ✅

