# Smart Glove Calibration Protocol

## 1. Overview

The Smart Glove requires a **two-stage calibration process**:

1. **Flex Sensor Calibration** - Maps sensor ADC values to finger bend range [0, 1]
2. **IMU Calibration** - Removes gravity offset from accelerometer/gyroscope

This document outlines the complete workflow for end-users and Android developers.

---

## 2. Flex Sensor Calibration

### Purpose

Raw flex sensor values vary significantly between individuals due to:

- Hand size and finger length differences
- Manufacturing tolerances in flex sensors
- Different hand postures during recording

A per-user calibration ensures consistent gesture recognition accuracy.

### Data Collection

#### Phase 1: Rest Position (Open Hand)

1. **User keeps hand completely relaxed** on a flat surface
2. **All fingers fully extended** (not forced, natural extension)
3. **Record for 3 seconds** → Collect ~300 samples
4. **Result:** Min flex values per sensor

#### Phase 2: Closed Position (Fist)

1. **User makes a tight fist** without straining
2. **Hold for 3 seconds** → Collect ~300 samples
3. **Result:** Max flex values per sensor

#### Phase 3: Calibration Endpoints

From the collected data, compute per-sensor:

```
flex_min[i] = min(all_rest_samples[i])      // e.g., 1200
flex_max[i] = max(all_closed_samples[i])    // e.g., 2800
```

### Algorithm (Normalization)

Once calibrated:

```python
def normalize_flex(raw_adc, sensor_index):
    """
    Convert raw ADC (0-4095) to normalized value (0.0-1.0)
    """
    norm = (raw_adc - flex_min[sensor_index]) / (flex_max[sensor_index] - flex_min[sensor_index])
    return constrain(norm, 0.0, 1.0)  # Clamp to [0, 1]
```

### Storage (Android SharedPreferences)

```json
{
  "calibration": {
    "flex_min": [1200, 1300, 1450, 1250, 1200],
    "flex_max": [2800, 2900, 3100, 2600, 2500],
    "flex_calibrated_at": "2025-04-03T14:30:00Z"
  }
}
```

### Default Fallback Values

If user skips calibration:

```
Flex Min: [1200, 1300, 1450, 1250, 1200]
Flex Max: [2800, 2900, 3100, 2600, 2500]
```

---

## 3. IMU Calibration

### Purpose

MPU6050 accelerometer & gyroscope have permanent offsets due to manufacturing. These must be removed for accurate motion detection.

### Data Collection

#### Procedure: Static Calibration

1. **Place glove on flat surface** (hand resting)
2. **DO NOT MOVE for 10 seconds**
3. **Collect 1000 samples** (at 100 Hz = 10 seconds)
4. **Compute mean per axis**

#### Expected Accel Values at Rest

On flat surface:

- ax = 0.0 ± 0.05 m/s² (small noise)
- ay = 0.0 ± 0.05 m/s²
- az = 9.81 ± 0.1 m/s² (gravity)

#### Expected Gyro Values at Rest

Stationary glove:

- gx = 0.0 ± 0.5 deg/s (small drift)
- gy = 0.0 ± 0.5 deg/s
- gz = 0.0 ± 0.5 deg/s

### Algorithm (Offset Removal)

```python
def calibrate_imu():
    """
    Collect 1000 samples while glove is completely still
    """
    samples = collect_1000_samples()  # At 100 Hz = 10 seconds

    imu_offset = {
        'accel_x': mean(samples['ax']),
        'accel_y': mean(samples['ay']),
        'accel_z': mean(samples['az']),
        'gyro_x': mean(samples['gx']),
        'gyro_y': mean(samples['gy']),
        'gyro_z': mean(samples['gz'])
    }

    return imu_offset

def apply_imu_calibration(raw_measurement, offset):
    """
    Remove offset during feature extraction
    """
    corrected = {
        'ax': raw_measurement['ax'] - offset['accel_x'],
        'ay': raw_measurement['ay'] - offset['accel_y'],
        'az': raw_measurement['az'] - offset['accel_z'] - 9.81,  # Remove gravity
        'gx': raw_measurement['gx'] - offset['gyro_x'],
        'gy': raw_measurement['gy'] - offset['gyro_y'],
        'gz': raw_measurement['gz'] - offset['gyro_z']
    }
    return corrected
```

### Storage (Android SharedPreferences)

```json
{
  "calibration": {
    "imu_offset": {
      "accel_x": 0.045,
      "accel_y": -0.032,
      "accel_z": 0.018,
      "gyro_x": 0.23,
      "gyro_y": -0.15,
      "gyro_z": 0.08
    },
    "imu_calibrated_at": "2025-04-03T14:35:00Z"
  }
}
```

### Default Fallback Values

If user skips calibration:

```
Accel Offset: [0.0, 0.0, 0.0]
Gyro Offset: [0.0, 0.0, 0.0]
```

---

## 4. Android App UI Flow

### Screen 1: Calibration Welcome

```
┌─────────────────────────────────────┐
│    Smart Glove Setup                │
│                                     │
│  First-time calibration needed      │
│                                     │
│  This ensures accurate gestures     │
│  Estimated time: 2 minutes          │
│                                     │
│  [SKIP] [START CALIBRATION]         │
└─────────────────────────────────────┘
```

### Screen 2: Flex Sensor - Rest (Phase 1)

```
┌─────────────────────────────────────┐
│  Flex Calibration - Resting Hand    │
│                                     │
│  Instructions:                      │
│  1. Place glove on flat surface     │
│  2. Keep hand completely relaxed    │
│  3. All fingers FULLY EXTENDED      │
│                                     │
│  Ready: [YES, CONTINUE]             │
│                                     │
│  Progress: [████░░░░░░]  30/100     │
│  Time: 7/10 seconds remaining       │
└─────────────────────────────────────┘
```

**Data Display (Real-time):**

```
Current Flex Values:
  Thumb   : 1235 (min)
  Index   : 1305
  Middle  : 1450
  Ring    : 1270
  Pinky   : 1200
```

### Screen 3: Flex Sensor - Closed (Phase 2)

```
┌─────────────────────────────────────┐
│  Flex Calibration - Closed Fist     │
│                                     │
│  Instructions:                      │
│  1. Make a TIGHT FIST               │
│  2. Hold for 3 seconds              │
│  3. Don't strain - natural tension  │
│                                     │
│  Ready: [YES, CONTINUE]             │
│                                     │
│  Progress: [████████░░]  75/100     │
│  Time: 2/10 seconds remaining       │
└─────────────────────────────────────┘
```

**Data Display (Real-time):**

```
Current Flex Values:
  Thumb   : 2800 (max)
  Index   : 2915
  Middle  : 3105
  Ring    : 2625
  Pinky   : 2510
```

### Screen 4: Flex Results

```
┌─────────────────────────────────────┐
│  Flex Calibration Complete ✓        │
│                                     │
│  Calibration Values:                │
│                                     │
│  Thumb:   1235 - 2800 (rang: 1565)  │
│  Index:   1305 - 2915 (rang: 1610)  │
│  Middle:  1450 - 3105 (rang: 1655)  │
│  Ring:    1270 - 2625 (rang: 1355)  │
│  Pinky:   1200 - 2510 (rang: 1310)  │
│                                     │
│  [CONTINUE TO IMU CALIBRATION]      │
└─────────────────────────────────────┘
```

### Screen 5: IMU Calibration

```
┌─────────────────────────────────────┐
│  IMU Calibration - Static Position  │
│                                     │
│  Instructions:                      │
│  1. Place glove on flat surface     │
│  2. DO NOT MOVE for 10 seconds      │
│  3. Keep hand completely still      │
│                                     │
│  Ready: [YES, CONTINUE]             │
│                                     │
│  Progress: [████████████]  100/100  │
│  Time: 0/10 seconds remaining       │
│                                     │
│  Calibration Status: COMPLETE ✓     │
└─────────────────────────────────────┘
```

**Data Display (Real-time):**

```
Current IMU Values:
  Accel-X: 0.032 m/s²
  Accel-Y: -0.045 m/s²
  Accel-Z: 9.821 m/s²
  Gyro-X:  0.15 deg/s
  Gyro-Y: -0.22 deg/s
  Gyro-Z:  0.08 deg/s
```

### Screen 6: Calibration Summary

```
┌─────────────────────────────────────┐
│  Setup Complete! ✓                  │
│                                     │
│  ✓ Flex Sensors Calibrated          │
│  ✓ IMU Calibrated                   │
│  ✓ Models Loaded                    │
│                                     │
│  Your Smart Glove is ready!         │
│                                     │
│  [START GESTURE RECOGNITION]        │
└─────────────────────────────────────┘
```

---

## 5. First-Time User Quickstart

### For End-Users (Non-Technical)

#### Step 1: Download & Install

- Install SmartGlove app from Play Store
- Ensure Android 8.0+
- Grant WiFi permissions

#### Step 2: Connect to WiFi Hotspot

1. Open Android WiFi settings
2. Find **"SmartGlove"** hotspot
3. Connect with password: **smartglove1234**
4. Leave USB debugging cable connected to ESP32

#### Step 3: Launch App

1. Open SmartGlove app
2. Wait for "Sensor Connection OK" message (blue indicator)
3. When ready, app shows calibration screen

#### Step 4: Calibration (2 minutes)

Follow on-screen instructions:

1. **Relax hand** - 10 seconds
2. **Close fist** - 10 seconds
3. **Keep still** - 10 seconds
4. Done!

#### Step 5: Start Using

- Perform gestures naturally
- System recognizes in real-time
- Results displayed on screen

---

## 6. Technical Implementation Details

### Data Flow: Arduino → Android

#### ESP32 Transmits (Every 20ms):

```json
{
  "fL": [raw_adc_1, raw_adc_2, ...],  // Slave flex (integers 0-4095)
  "fR": [raw_adc_1, raw_adc_2, ...],  // Master flex (integers 0-4095)
  "aL": [accel_x, accel_y, accel_z],  // Slave accel (float, m/s²)
  "aR": [accel_x, accel_y, accel_z],  // Master accel (float, m/s²)
  "gL": [gyro_x, gyro_y, gyro_z],     // Slave gyro (float, deg/s)
  "gR": [gyro_x, gyro_y, gyro_z],     // Master gyro (float, deg/s)
  "bL": raw_adc_battery,               // Slave battery (integer 0-4095)
  "bR": raw_adc_battery,               // Master battery (integer 0-4095)
  "ts": timestamp_ms                   // Timestamp in milliseconds
}
```

#### Android Processing:

```python
def process_sensor_data(json_packet, calibration):
    # Step 1: Parse JSON
    data = parse_json(json_packet)

    # Step 2: Normalize flex sensors
    flex_L = [normalize_flex(data['fL'][i], i) for i in range(5)]
    flex_R = [normalize_flex(data['fR'][i], i) for i in range(5)]

    # Step 3: Calibrate IMU
    accel_L = [data['aL'][i] - calibration['accel_offset'][i] for i in range(3)]
    accel_R = [data['aR'][i] - calibration['accel_offset'][i] for i in range(3)]
    gyro_L = [data['gL'][i] - calibration['gyro_offset'][i] for i in range(3)]
    gyro_R = [data['gR'][i] - calibration['gyro_offset'][i] for i in range(3)]

    # Step 4: Extract 66 features
    features = extract_features(flex_L, flex_R, accel_L, accel_R, gyro_L, gyro_R)

    # Step 5: Inference
    category = category_classifier.infer(features)
    gesture = gesture_classifier[category].infer(features)
    confidence = get_confidence()

    return {
        'gesture': gesture,
        'category': category,
        'confidence': confidence,
        'features': features
    }
```

---

## 7. Troubleshooting Calibration Issues

### Flex Calibration Problems

| Issue                        | Symptom                               | Solution                                                  |
| ---------------------------- | ------------------------------------- | --------------------------------------------------------- |
| **Unable to Move**           | Flex sensors always show same value   | Check USB connection, verify FLEX*PIN*\* in Arduino code  |
| **Values Out of Range**      | Always 0 or 4095                      | Check flex sensor continuity, test with multimeter        |
| **Poor Gesture Recognition** | Low confidence even after calibration | Recalibrate, ensure full hand relaxation & closure        |
| **One Sensor Not Working**   | One flex value missing or constant    | Check flex sensor for physical damage or loose wiring     |
| **Calibration Rejected**     | App says "Invalid range" (min ≥ max)  | Check for inverted sensor orientation or defective sensor |

### IMU Calibration Problems

| Issue                           | Symptom                                   | Solution                                                                    |
| ------------------------------- | ----------------------------------------- | --------------------------------------------------------------------------- |
| **IMU Not Detected**            | "No IMU Found" error                      | Check I2C wiring (SDA/SCL), verify MPU6050 address 0x68                     |
| **Gravity Removed Incorrectly** | Hand orientation affects recognition      | Ensure flat surface during calibration, perpendicular to ground             |
| **High Gyro Drift**             | Rotation values changing without movement | Not a critical issue - normal for uncalibrated gyro, recalibrating may help |
| **Calibration Takes Forever**   | Status stuck at 80%                       | Check SD connection, verify TCP connection to Android still active          |

---

## 8. Advanced: Manual Calibration Override

For power users who want to adjust values:

### SharedPreferences Manual Edit (Android):

```json
{
  "calibration": {
    "flex_min": [1200, 1300, 1450, 1250, 1200],
    "flex_max": [2800, 2900, 3100, 2600, 2500],
    "imu_offset": {
      "accel_x": 0.045,
      "accel_y": -0.032,
      "accel_z": 0.018,
      "gyro_x": 0.23,
      "gyro_y": -0.15,
      "gyro_z": 0.08
    },
    "manual_override": true,
    "last_modified": "2025-04-03T14:30:00Z"
  }
}
```

### How to Adjust:

1. Connect Android to PC with USB debugging enabled
2. Use Android Studio Device File Explorer
3. Navigate to app's SharedPreferences file
4. Manually edit JSON values
5. Reload app

**Recommended adjustments:**

- If gestures feel too sensitive: Increase `flex_max` values by 5-10%
- If gestures feel too loose: Decrease `flex_max` values by 5-10%
- If drifting occurs during gesture: Recalibrate IMU

---

## 9. Verification Checklist

After calibration, verify system is working:

- [ ] All flex values change smoothly when hand moves (no jumps)
- [ ] Flex values different for each finger (not synchronized)
- [ ] Resting values are stable (< 10 ADC variance)
- [ ] Closed values are significantly higher than resting (diff > 500)
- [ ] IMU acceleration changes when hand tilted
- [ ] Gyro values change when hand rotated
- [ ] Battery voltage reading realistic (3.0-4.2V)
- [ ] TCP connection shows real-time data stream
- [ ] First gesture recognized with confidence > 80%

---

## 10. Calibration Data Retention

### Where Calibration is Stored

- **Android Device:** `/data/data/com.smartglove.app/shared_prefs/calibration.xml`
- **Cloud (Optional):** Firebase Realtime Database (if enabled)
- **Local Backup:** Can export to CSV for multi-device setup

### Multi-Device Setup

If using multiple Android phones with same glove:

1. Calibrate on Phone A
2. Export calibration: `Menu → Export Calibration`
3. Save QR code
4. On Phone B: `Menu → Import Calibration` → Scan QR
5. Both phones now use same calibration

---

## Summary

| Stage                 | Duration | Frequency                                |
| --------------------- | -------- | ---------------------------------------- |
| **Flex Rest**         | 10 sec   | First-time only                          |
| **Flex Close**        | 10 sec   | First-time only                          |
| **IMU Static**        | 10 sec   | First-time only                          |
| **Total Calibration** | ~2 min   | First-time only                          |
| **Re-calibration**    | ~2 min   | Recommended monthly or if accuracy drops |

**Key Takeaway:** Calibration is a one-time process that takes 2 minutes. Results are stored locally and require recalibration only if sensor hardware is changed or accuracy degrades over time.
