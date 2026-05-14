# 🧤 Smart Glove - Real-Time Gesture Prediction

## Pengenalan
Script `smartglove_realtime_predict.py` melakukan **prediksi gerakan real-time** dari UDP stream ESP32.

## Prasyarat ✅
1. **Model sudah dilatih**: Jalankan `smartglove_predict (2).ipynb` Cell 1-5
   - Hasilnya: `model.pkl`, `scaler.pkl`, `meta.pkl` di folder `model_output/`
2. **Python + Dependencies**: 
   ```bash
   pip install scikit-learn pandas numpy matplotlib joblib
   ```
3. **UDP streaming**: Data collection app atau ESP32 harus mengirim UDP ke port 5000

---

## Cara Pakai

### Step 1: Pastikan Model Ada
```bash
# Cek folder model_output
ls C:\FOLDERKU\SmartGlove\model_output\
```
Harus ada:
- `model.pkl`
- `scaler.pkl`
- `meta.pkl`

### Step 2: Mulai Data Collection atau Test Mode
#### Option A: Dari Data Collection GUI
```bash
python smart_glove_data_collection.py
# Klik "START UDP SERVER"
```

#### Option B: Langsung dengan File CSV (Simulate UDP)
Buat file `simulate_udp.py` untuk testing tanpa hardware

### Step 3: Jalankan Real-Time Predictor
```bash
python smartglove_realtime_predict.py
```

Jendela GUI akan muncul dengan:
- 📡 **KONTROL**: Start/Stop listening
- 📊 **STATISTIK**: Frame buffer, FPS counter
- 🎯 **HASIL PREDIKSI**: Gesture + confidence score
- 📈 **GRAFIK**: Sensor data visualization
- 📋 **LOG**: Status messages

### Step 4: Klik "▶ START LISTENING"
- App akan dengarkan UDP port 5000
- Buffer akan terisi dengan sensor data
- Setelah 80 frame terkumpul, prediksi mulai berjalan
- Hasil ditampilkan real-time

---

## Fitur

✅ **Real-time Processing**
- Buffer 80 frame (sesuai training window)
- Prediksi setiap buffer penuh
- Update UI setiap 100ms

✅ **Visualisasi**
- Grafik Flex sensors (tangan kiri)
- Grafik Accelerometer
- Confidence bar chart per gesture
- Animasi confidence percentage

✅ **Monitoring**
- Frame counter (current / max)
- Buffer size tracker
- Connection status
- FPS indicator

✅ **Robustness**
- Error handling untuk UDP parsing
- Graceful reconnection
- Threaded architecture (receive + predict separateway)

---

## Troubleshooting

### ❌ "Model tidak ditemukan"
**Solusi**: Pastikan sudah jalankan training di notebook terlebih dahulu
```bash
# Cell 3-5 di smartglove_predict (2).ipynb
```

### ❌ "UDP binding failed"
**Solusi**: Port 5000 sudah digunakan
```bash
# Cek port:
netstat -an | findstr :5000
# Kill process atau ubah UDP_PORT di script
```

### ❌ "Buffer tidak terisi"
**Solusi**: 
1. Cek UDP data ada yang masuk (lihat log message)
2. Pastikan data collection app mengirim ke IP PC yang benar
3. Ping dari ESP32: `ping 192.168.x.x`

### ❌ "Prediksi melambat"
**Solusi**:
- Model processing biasanya < 50ms
- Jika masih lambat, kurangi update chart frequency

---

## Configuration Options

Edit di file `smartglove_realtime_predict.py`:

```python
UDP_PORT = 5000              # Port listening
WINDOW_SIZE = 80             # Frame per prediksi (harus sama training)
MODEL_DIR = r"C:\FOLDERKU\SmartGlove\model_output"  # Folder model
```

---

## Testing Tanpa Hardware

Buat file `test_realtime_simulator.py`:

```python
import socket
import numpy as np
import time

def send_fake_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Random data 20 channel (10 flex + 6 accel + 6 gyro)
    while True:
        flex = ','.join([str(np.random.uniform(0.3, 0.9)) for _ in range(10)])
        accel = ','.join([str(np.random.normal(0, 0.5)) for _ in range(6)])
        gyro = ','.join([str(np.random.normal(0, 2)) for _ in range(6)])
        
        msg = f"DATA|F:{flex}|A:{accel}|G:{gyro}|BAT:4.2,4.1"
        sock.sendto(msg.encode(), ("127.0.0.1", 5000))
        time.sleep(0.02)  # 50 Hz

if __name__ == "__main__":
    send_fake_udp()
```

Jalankan kedua:
1. Terminal 1: `python test_realtime_simulator.py` (send fake UDP)
2. Terminal 2: `python smartglove_realtime_predict.py` (receive + predict)

---

## Output / Logging

Log di UI menampilkan:
- ✓ Model loaded
- ▶ Listening started
- ⚠ Warning (UDP errors, missing columns)
- ❌ Critical errors

Semua logged dengan timestamp untuk debugging.

---

## Performance Tips

| Parameter | Value | Effect |
|-----------|-------|--------|
| WINDOW_SIZE | 80 | Lebih besar = lebih akurat tapi latency tinggi |
| Update frequency | 100ms | Bisa dikurangi untuk UI update lebih smooth |
| Thread sleep | 50ms | Reduce untuk response lebih cepat |

---

## Next Steps

1. **Improve confidence threshold**
   - Tambah mode "confidence filtering" (hanya catat jika > 80%)
   
2. **Recording results**
   - Simpan prediction history ke CSV
   - Timestamp + gesture + confidence
   
3. **Multi-hand support**
   - Visualisasi tangan kiri + kanan terpisah

4. **Mobile deployment**
   - Export ke Android/iOS untuk real-time preview

---

## Support

Jika ada error, share:
1. Full error message
2. Model training accuracy
3. UDP data sample (dari log)

Happy predicting! 🎉
