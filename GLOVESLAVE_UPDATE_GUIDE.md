# GloveSlave Arduino Update Guide

## Overview

Update **GloveSlave.ino** (ESP32 on left glove) to send **raw ADC values** via ESP-NOW, matching the Master architecture. This completes the hardware data pipeline for the Android calibration system.

## Critical Changes Required

### 1. Update struct_message (Data Structure)

**Change the struct to indicate raw vs. processed values:**

```cpp
// OLD STRUCTURE (DEPRECATED):
typedef struct struct_message {
    float flex[5];          // Was normalized 0.0-1.0
    float accel[3];         // Already OK: m/s²
    float gyro[3];          // Already OK: deg/s
    float batteryVoltage;   // Was in volts (e.g., 3.82)
    int   batteryPercentage;
    unsigned long timestamp;
} struct_message;

// NEW STRUCTURE (RAW ADC):
typedef struct struct_message {
    float flex[5];          // NOW: raw ADC values 0-4095 (cast from int)
    float accel[3];         // Unchanged: m/s²
    float gyro[3];          // Unchanged: deg/s
    float batteryVoltage;   // NOW: raw ADC battery 0-4095 (cast from int)
    int   batteryPercentage; // Can be deprecated or kept for info
    unsigned long timestamp;
} struct_message;
```

### 2. Update readLocalSensors() Function

**Before (DEPRECATED):**

```cpp
void readLocalSensors() {
    // Read and NORMALIZE flex immediately
    sensorData.flex[0] = normalizeFlexValue(analogRead(FLEX_PIN_1), 0);
    sensorData.flex[1] = normalizeFlexValue(analogRead(FLEX_PIN_2), 1);
    sensorData.flex[2] = normalizeFlexValue(analogRead(FLEX_PIN_3), 2);
    sensorData.flex[3] = normalizeFlexValue(analogRead(FLEX_PIN_4), 3);
    sensorData.flex[4] = normalizeFlexValue(analogRead(FLEX_PIN_5), 4);

    // Read battery voltage
    int raw = analogRead(VBAT_PIN);
    sensorData.batteryVoltage = (raw / 4095.0) * 3.3 * 2.0; // Convert to voltage

    // IMU processing (unchanged)
    int16_t ax, ay, az, gx, gy, gz;
    mpuGetMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    sensorData.accel[0] = ax / 16384.0;
    sensorData.accel[1] = ay / 16384.0;
    sensorData.accel[2] = az / 16384.0;
    sensorData.gyro[0]  = gx / 131.0;
    sensorData.gyro[1]  = gy / 131.0;
    sensorData.gyro[2]  = gz / 131.0;

    sensorData.timestamp = millis();
}
```

**After (NEW):**

```cpp
void readLocalSensors() {
    // Read RAW ADC flex - NO normalization
    sensorData.flex[0] = (float)analogRead(FLEX_PIN_1);  // Cast int to float
    sensorData.flex[1] = (float)analogRead(FLEX_PIN_2);
    sensorData.flex[2] = (float)analogRead(FLEX_PIN_3);
    sensorData.flex[3] = (float)analogRead(FLEX_PIN_4);
    sensorData.flex[4] = (float)analogRead(FLEX_PIN_5);

    // Read RAW ADC battery - NO voltage conversion
    sensorData.batteryVoltage = (float)analogRead(VBAT_PIN);  // Cast int to float, range 0-4095

    // IMU processing (UNCHANGED - already converts to SI units)
    int16_t ax, ay, az, gx, gy, gz;
    mpuGetMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    sensorData.accel[0] = ax / 16384.0;  // Valid m/s²
    sensorData.accel[1] = ay / 16384.0;
    sensorData.accel[2] = az / 16384.0;
    sensorData.gyro[0]  = gx / 131.0;    // Valid deg/s
    sensorData.gyro[1]  = gy / 131.0;
    sensorData.gyro[2]  = gz / 131.0;

    sensorData.timestamp = millis();
}
```

### 3. Remove normalizeFlexValue Function

**Delete or comment out the old normalization function:**

```cpp
// DEPRECATED - NO LONGER NEEDED
/*
float normalizeFlexValue(int raw, int idx) {
    float n = (float)(raw - flexMin[idx]) / (flexMax[idx] - flexMin[idx]);
    return constrain(n, 0.0, 1.0);
}
*/
```

### 4. Keep or Remove Calibration Arrays (Optional)

**Option A: Keep for reference (recommended)**

```cpp
// ==================== FLEX CALIBRATION (FOR REFERENCE ONLY) ====================
// These values are now DEPRECATED on Arduino side
// All calibration happens on Android device
float flexMin[5] = {2646, 2582, 1665, 1262, 1258};
float flexMax[5] = {3668, 3128, 3559, 2124, 2024};

// NOTE: Kept for backward compatibility and documentation purposes only
```

**Option B: Remove completely**

```cpp
// Delete flexMin[] and flexMax[] arrays entirely
// Arduino now sends only raw ADC values
```

### 5. Battery Check Function Update (Optional)

**If battery monitoring exists, update thresholds:**

```cpp
// OLD (worked with voltage):
void checkBatteryStatus() {
    if (sensorData.batteryVoltage < 3.3)  // 3.3V threshold
        Serial.println("[BATTERY] LOW!");
}

// NEW (works with raw ADC):
void checkBatteryStatus() {
    // Convert raw ADC to voltage for comparison
    int raw_battery = (int)sensorData.batteryVoltage;  // 0-4095
    float voltage = (raw_battery / 4095.0) * 3.3 * 2.0;  // Convert back to voltage

    if (voltage < 3.3)  // Still 3.3V threshold
        Serial.println("[BATTERY] LOW! " + String(voltage, 2) + "V");
}
```

---

## Data Format Comparison

### Before Update (DEPRECATED)

```json
{
  "fL": [0.12, 0.45, 0.67, 0.34, 0.89],   // Normalized 0.0-1.0
  "fR": [0.15, 0.50, 0.70, 0.40, 0.91],   // Normalized 0.0-1.0
  "aL": [-0.213, 0.891, 9.821],           // m/s² (correct)
  "aR": [-0.215, 0.901, 9.831],           // m/s² (correct)
  "gL": [1.23, -2.45, 0.78],              // deg/s (correct)
  "gR": [1.25, -2.47, 0.80],              // deg/s (correct)
  "bL": 3.82,                             // Voltage in V
  "bR": 3.91,                             // Voltage in V
  "ts": 12345
}
PROBLEM: Can't recalibrate without reprogramming Arduino!
```

### After Update (NEW - CORRECT)

```json
{
  "fL": [1200, 1400, 1650, 1250, 1350],   // Raw ADC 0-4095 ✓
  "fR": [1250, 1450, 1700, 1300, 1400],   // Raw ADC 0-4095 ✓
  "aL": [-0.213, 0.891, 9.821],           // m/s² (unchanged ✓)
  "aR": [-0.215, 0.901, 9.831],           // m/s² (unchanged ✓)
  "gL": [1.23, -2.45, 0.78],              // deg/s (unchanged ✓)
  "gR": [1.25, -2.47, 0.80],              // deg/s (unchanged ✓)
  "bL": 1850,                             // Raw ADC 0-4095 ✓
  "bR": 1920,                             // Raw ADC 0-4095 ✓
  "ts": 12345
}
BENEFIT: Android handles all calibration - user-friendly!
```

---

## Implementation Checklist

- [ ] **Backup current GloveSlave.ino**
- [ ] **Update struct_message** - flex[] now receives raw ADC
- [ ] **Update readLocalSensors()** - remove normalization
- [ ] **Remove normalizeFlexValue()** - function no longer needed
- [ ] **Keep IMU conversion** - accel/gyro still needs m/s²/deg/s conversion
- [ ] **Update comments** - document the change for future reference
- [ ] **Test ESP-NOW transmission** - verify values are in range 0-4095
- [ ] **Cross-check with Master** - both should now send raw ADC flex + battery

---

## Testing Procedure

### Step 1: Flash Updated GloveSlave.ino

```
Arduino IDE:
1. Open GloveSlave.ino
2. Board: ESP32 (select your board variant)
3. Port: Select COM port for Slave
4. Verify → Upload
5. Open Serial Monitor (115200 baud)
```

### Step 2: Verify Serial Output

Look for startup messages:

```
[SYSTEM] GloveSlave starting...
[I2C] MPU6050 initialized
[ESP-NOW] Initialized and waiting for peer
```

### Step 3: Monitor Raw ADC Values

Should see output like:

```
[SENSOR] fL:[1250,1300,1450,1280,1200] bL:1850 aL:[-0.2,0.9,9.8]
[SENSOR] fL:[1252,1301,1448,1279,1201] bL:1851 aL:[-0.2,0.9,9.8]
[SENSOR] fL:[1248,1299,1452,1281,1199] bL:1849 aL:[-0.2,0.9,9.8]
```

**Expected ranges:**

- Flex: 1000-3000 (should vary with hand position)
- Battery: 1500-2500 (varies with battery voltage)
- Accel: -2 to +11 m/s² (gravity + motion)
- Gyro: -100 to +100 deg/s (rotation only when moving)

### Step 4: Verify Master+Slave Communication

On Master (connected to PC):

```
[TCP] Connecting to Android...
[SYSTEM] Ready — waiting for Android app...
```

Glove should transmit every 20ms with both left + right data in same JSON.

### Step 5: Test with Android App

1. Connect Android to hotspot
2. Open SmartGlove app
3. Should show real-time sensor values
4. Flex values should change when fingers move
5. Calibration should proceed normally

---

## Verification: Data Transmission Path

```
GloveSlave (Left Hand)
    ↓
    ESP-NOW (wireless)
    ↓
GloveMaster (Right Hand)
    │ + Local sensors
    ↓
    TCP over WiFi hotspot
    ↓
Android Phone
    │ (Calibration)
    ├─ Apply flex_min/max normalization
    ├─ Apply IMU offset correction
    ├─ Extract 66 features
    ├─ Inference (Category + Gesture)
    ↓
    Display recognized gesture
```

All calibration happens in Android, not Arduino ✓

---

## Common Issues After Update

| Problem                                           | Cause                                 | Solution                                                                       |
| ------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------ |
| Flex values are ~2000 (midpoint) and not changing | Old normalization code still active   | Verify `analogRead()` is returning raw ADC, not calling `normalizeFlexValue()` |
| Values get stuck at 0 or 4095                     | ADC pin issue or sensor disconnected  | Check flex sensor wiring, verify FLEX_PIN definitions                          |
| Battery reading stays constant                    | VBAT_PIN not connected or ADC error   | Verify battery circuit, check ADC resolution set to 12-bit                     |
| ESP-NOW transmission fails after update           | Data structure size changed           | Ensure both Master + Slave use identical struct_message definition             |
| App shows "Invalid calibration range"             | Min and max flex values are too close | Ensure ADC values differ by at least 500 (rest vs. fist)                       |
| Accelerometer/gyro values seem wrong              | IMU processing corrupted              | Verify accel/gyro conversion factors still: `ax/16384.0`, `gx/131.0`           |

---

## Rollback Procedure (If Issues Occur)

If the update causes problems, you can restore the old version:

### Option 1: From Backup

```
1. Restore GloveSlave.ino.backup
2. Flash to GloveSlave Arduino
3. System returns to old normalized behavior
```

### Option 2: Manual Revert

1. Restore `normalizeFlexValue()` function
2. Change `sensorData.flex[i] = (float)analogRead(FLEX_PIN_i);` back to `sensorData.flex[i] = normalizeFlexValue(analogRead(FLEX_PIN_i), i);`
3. Change battery: `sensorData.batteryVoltage = (raw / 4095.0) * 3.3 * 2.0;`
4. Re-upload

---

## FAQ

**Q: Why send raw ADC instead of normalized values?**
A: Normalized values depend on hardware calibration (flexMin/flexMax). By sending raw ADC, we enable runtime calibration without reprogramming the Arduino. Users can recalibrate for accuracy improvements anytime within the app.

**Q: Will this break existing Android apps?**
A: Yes. Old Android apps expect normalized 0.0-1.0 values. A new version of the Android app must be deployed to handle raw ADC data (provided separately).

**Q: Can I still use the old calibration on the Arduino side?**
A: No. Once you send raw ADC, the Arduino-side calibration becomes useless. The Android app must handle all normalization.

**Q: How do I know if both Master and Slave are transmitting correctly?**
A: Monitor the Android TCP connection - should show all 10 sensor values (fL, fR, aL, aR, gL, gR, bL, bR) updating every 20ms. If any values are missing, check ESP-NOW transmission between Master/Slave.

**Q: What's the performance impact of transmitting raw ADC?**
A: None. Raw integers are slightly smaller than floats, actually reducing bandwidth. Transmission rate stays at 50 Hz (20ms intervals).

---

## Next Steps

1. ✅ **GLoveMasterAndroid.ino** - Updated to transmit raw ADC
2. ⏳ **GloveSlave.ino** - Update using this guide
3. ⏳ **Android App** - Update to parse raw ADC and apply calibration
4. ⏳ **User Testing** - End-to-end gesture recognition test
5. ⏳ **Deployment** - Flash all devices with updated firmware

---

## Summary of Code Changes

| File                   | Change                   | Type             | Impact                                  |
| ---------------------- | ------------------------ | ---------------- | --------------------------------------- |
| struct_message         | flex[] now raw ADC       | Data Structure   | Medium - affects all transmitted values |
| readLocalSensors()     | Remove normalization     | Function Logic   | High - core data acquisition            |
| normalizeFlexValue()   | Delete/comment           | Function Removal | Low - not used by Slave after this      |
| flexMin/flexMax arrays | Keep or remove           | Config           | Low - purely optional reference         |
| Battery readout        | Send raw ADC not voltage | Function Logic   | Medium - affects battery monitoring     |
| IMU processing         | Unchanged                | No Change        | None - accel/gyro conversion stays same |

**Total lines changed:** ~15 lines  
**Time to implement:** 5-10 minutes  
**Testing required:** Yes - verify ESP-NOW transmission and value ranges  
**Rollback difficulty:** Easy - restore from backup or revert 2-3 lines
