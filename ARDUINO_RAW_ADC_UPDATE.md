# Arduino Raw ADC Data Transmission Update

## Overview

Modified GLoveMasterAndroid.ino to send **raw ADC values** instead of pre-calibrated normalized values. This allows the Android app to handle all calibration procedures at runtime, enabling users to recalibrate without reprogramming the Arduino.

## Changes Made

### 1. **sendTCPData() Function**

Changed JSON format to include **raw ADC values**:

**BEFORE:**

```json
{
  "fL": [0.12, 0.45, 0.67, 0.34, 0.89], // normalized 0.0-1.0
  "fR": [0.15, 0.5, 0.7, 0.4, 0.91],
  "aL": [-0.213, 0.891, 9.821], // m/s²
  "aR": [-0.215, 0.901, 9.831],
  "gL": [1.23, -2.45, 0.78], // deg/s
  "gR": [1.25, -2.47, 0.8],
  "bL": 3.82, // voltage
  "bR": 3.91,
  "ts": 12345
}
```

**AFTER:**

```json
{
  "fL": [1200, 1400, 1650, 1250, 1350], // raw ADC 0-4095
  "fR": [1250, 1450, 1700, 1300, 1400],
  "aL": [-0.213, 0.891, 9.821], // m/s² unchanged
  "aR": [-0.215, 0.901, 9.831],
  "gL": [1.23, -2.45, 0.78], // deg/s unchanged
  "gR": [1.25, -2.47, 0.8],
  "bL": 1850, // raw ADC battery
  "bR": 1920,
  "ts": 12345
}
```

### 2. **New Global Variables**

Added to store raw ADC values:

```cpp
int localRawFlex[5] = {0};       // raw ADC flex kanan (master)
int txRawFlex[5] = {0};          // raw ADC flex kiri dari slave
int lastBatteryRawRight = 0;     // raw ADC battery kanan
int lastBatteryRawLeft = 0;      // raw ADC battery kiri
```

### 3. **readLocalSensors() Function**

Now stores both raw and normalized values:

```cpp
// Store raw ADC
localRawFlex[0] = analogRead(FLEX_PIN_1);
localRawFlex[1] = analogRead(FLEX_PIN_2);
// ... etc

// Still normalize for local computation (if needed)
localData.flex[0] = normalizeFlexValue(localRawFlex[0], 0);
// ... etc
```

### 4. **readBattery() Function**

Stores raw ADC battery values:

```cpp
int raw = analogRead(VBAT_PIN);
lastBatteryRawRight = raw;  // Store raw for transmission
```

## Important Notes for Android Developer

### Flex Sensor Calibration

- **Raw ADC Range:** 0-4095 (12-bit ADC on ESP32)
- **Typical Resting Min:** 1000-1500 per sensor type
- **Typical Max (fully bent):** 2500-3500 per sensor type
- **Need to calibrate per user:** Different hand sizes/sensor variations

### Battery Measurement

- **Raw ADC:** 0-4095
- **Formula:** `voltage = (raw / 4095.0) * 3.3 * 2.0` (account for voltage divider ratio)
- **Expected Range:** 3.0V to 4.2V (lithium battery)

### MPU6050 Data

- **Accel & Gyro:** Still sent as processed values (m/s² and deg/s)
- **No raw sensor data** - already converted on Arduino for efficiency
- **Reason:** IMU processing is standard and doesn't need per-user calibration

## CRITICAL: Slave Arduino Update Required

The **GloveSlave.ino** ESP-NOW transmitter must also be updated to send raw ADC values in its `struct_message`:

### Current GloveSlave struct_message:

```cpp
typedef struct struct_message {
    float flex[5];              // Currently normalized
    float accel[3];
    float gyro[3];
    float batteryVoltage;       // Currently voltage in volts
    int   batteryPercentage;
    unsigned long timestamp;
} struct_message;
```

### Must change to send raw ADC in flex[] field:

```cpp
// In GloveSlave.ino, modify the sending code:
sensorData.flex[0] = analogRead(FLEX_PIN_1);  // raw ADC, not normalized
sensorData.flex[1] = analogRead(FLEX_PIN_2);
sensorData.flex[2] = analogRead(FLEX_PIN_3);
sensorData.flex[3] = analogRead(FLEX_PIN_4);
sensorData.flex[4] = analogRead(FLEX_PIN_5);

// Battery: send raw ADC value as integer (cast to float field)
sensorData.batteryVoltage = (float)analogRead(VBAT_PIN);  // raw ADC 0-4095
```

## Testing Procedure

1. **Flash Updated GLoveMasterAndroid.ino** to Master ESP32
2. **Update GloveSlave.ino** to send raw ADC (see above)
3. **Connect to WiFi hotspot:** SmartGlove / smartglove1234
4. **Monitor TCP output** on port 8080 using:
   ```python
   import socket
   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   sock.connect(("ESP32_IP", 8080))
   while True:
       line = sock.recv(1024).decode('utf-8')
       print(line)
   ```
5. **Verify JSON format** includes raw ADC values (integers) for fL, fR, bL, bR
6. **Check value ranges:** Flex should be 1000-3000, Battery should be 1500-2500

## Troubleshooting

| Issue                              | Cause                                       | Solution                                                        |
| ---------------------------------- | ------------------------------------------- | --------------------------------------------------------------- |
| Flex values out of range (0, 4095) | Damaged sensor or loose wire                | Check sensor continuity with multimeter                         |
| Battery always ~2048 (midpoint)    | VBAT_PIN disconnected                       | Check battery circuit, verify pin assignment                    |
| Flex values not changing           | Sensor stuck or calibration values inverted | Test flex with multimeter, check sensor wiring                  |
| Android shows "Calibration failed" | Flex values too close (min ≈ max)           | Ensure sensors can bend full range, check for mechanical damage |

## File Modifications Summary

- **GLoveMasterAndroid.ino**
  - Line ~350: `sendTCPData()` - Changed JSON format
  - Line ~68: Added raw ADC variable declarations
  - Line ~396: `readLocalSensors()` - Store raw ADC
  - Line ~430: `readBattery()` - Capture raw ADC battery

- **GloveSlave.ino (TODO)**
  - Update sensor reading code to send raw ADC
  - Cast raw int to float in struct for transmission

---

## Next Steps

1. ✅ Master Arduino updated (this document)
2. ⏳ Update GloveSlave.ino
3. ⏳ Update Android app to handle raw ADC calibration
4. ⏳ Create user calibration UI with min/max recording
5. ⏳ Test end-to-end with real gestures
