# Arduino ADC & Data Normalization Flow

## Data Flow dari Arduino ke CSV

```
┌─────────────────────────────────────────────────────────┐
│                   ARDUINO (ESP32)                        │
│  readLocalSensors()                                      │
│  localData.flex[i] = (float)analogRead(FLEX_PIN_i)      │
│  ↓                                                       │
│  Kirim via UDP: DATA|F:2150,1875,2345,... (ADC 0-4095) │
└─────────────────────────────────────────────────────────┘
                         ↓ UDP
┌─────────────────────────────────────────────────────────┐
│              PYTHON - DATA COLLECTION                    │
│  read_udp_data() → parse_data_line()                    │
│                                                          │
│  // STEP 1: Display raw ADC values                      │
│  flex_L_display = [2150, 1875, 2345, ...]               │
│  → Tampilkan di UI: "Tangan Kiri: [2150, 1875, ...]"   │
│                                                          │
│  // STEP 2: Calibration data tersedia?                  │
│  if calibration_values.json ada:                        │
│      min/max values loaded dari file                    │
│  else:                                                   │
│      use defaults: min=[4095]*5, max=[0]*5             │
│                                                          │
│  // STEP 3: Normalisasi menggunakan kalibrasi          │
│  normalized_value = (raw_adc - min) / (max - min)      │
│  clamp (0.0 - 1.0)                                      │
│  → Result: [0.45, 0.32, 0.58, ...]                     │
│                                                          │
│  // STEP 4: Simpan ke CSV dengan nilai normalized      │
│  CSV row: [..., 0.45, 0.32, 0.58, ...]                 │
└─────────────────────────────────────────────────────────┘
                         ↓ File I/O
┌─────────────────────────────────────────────────────────┐
│          CSV File (datashet/[category]/...)             │
│                                                          │
│  timestamp | flex1_L | flex2_L | ... | rep |            │
│  ----------|---------|---------|-----|-----|            │
│  0         | 0.45    | 0.32    | ... | 1   |            │
│  50        | 0.47    | 0.31    | ... | 1   |            │
│  100       | 0.49    | 0.33    | ... | 1   |            │
│                                                          │
│  ✅ DATA SUDAH NORMALIZED (0-1)                         │
│  ✅ SIAP UNTUK TRAINING MODEL                           │
└─────────────────────────────────────────────────────────┘
```

## Tiga Kondisi Nilai Kalibrasi

### 1. **PERTAMA KALI (Belum Kalibrasi)**

```
UI Display ADC (dari Arduino):
  Tangan Kiri:  [2150, 1875, 2345, ...]   ← Raw values

Kalibrasi Data (defaults):
  flex_min_L = [4095, 4095, 4095, 4095, 4095]
  flex_max_L = [0, 0, 0, 0, 0]

Normalized Value (TIDAK AKURAT):
  (2150 - 4095) / (0 - 4095) = -0.48... → clamped to 0.0
  (1875 - 4095) / (0 - 4095) = -0.54... → clamped to 0.0
  ❌ SEMUA MENJADI 0 (TIDAK BERGUNA)

CSV akan berisi: [0.0, 0.0, 0.0, ...]
```

**ACTION**: Kalibrasi dengan button "⚙️ KALIBRASI" sebelum mulai recording serius!

### 2. **SUDAH KALIBRASI (calibration_values.json ada)**

```
UI Display ADC (dari Arduino):
  Tangan Kiri:  [2150, 1875, 2345, ...]   ← Raw values

Kalibrasi Data (dari JSON):
  flex_min_L = [1500, 1200, 1600, 1400, 1300]
  flex_max_L = [3000, 2800, 3200, 2900, 2700]

Normalized Value (AKURAT):
  sensor 1: (2150 - 1500) / (3000 - 1500) = 650/1500 = 0.43
  sensor 2: (1875 - 1200) / (2800 - 1200) = 675/1600 = 0.42
  sensor 3: (2345 - 1600) / (3200 - 1600) = 745/1600 = 0.47
  ✅ NILAI MEANINGFUL (0-1)

CSV akan berisi: [0.43, 0.42, 0.47, ...]
```

//✅ SIAP UNTUK TRAINING

### 3. **RE-CALIBRASI (Setelah Recording)**

```
Tracking per kategori:
  - Gesture 1-9: No warning
  - Gesture 10: ⚠️ Popup → "Sudah 10 ANGKA, kalibrasi direkomendasikan"
  - Gesture 11-20: Normal, tapi log warning setiap 10
  - (User bisa kalibrasi ulang kapan saja)

Setelah kalibrasi baru:
  calibration_values.json di-update dengan nilai baru
  Genre selanjutnya akan pakai min/max baru ini
```

## Penting!

| Aspek              | Keterangan                                 |
| ------------------ | ------------------------------------------ |
| **Arduino Kirim**  | ADC Mentah (0-4095) ✓                      |
| **Python Display** | ADC Mentah real-time ✓                     |
| **Python Simpan**  | Nilai Normalized (0-1) ✓                   |
| **Kalibrasi**      | Manual via button ✓                        |
| **Warning**        | Setelah 10 gesture per kategori ✓          |
| **Re-kalibrasi**   | Bisa kapan saja, di-overwrite nilai lama ✓ |

## Checklist Sebelum Recording

- [ ] Arduino sudah upload (mengirim ADC mentah)
- [ ] Data Collection app sudah buka
- [ ] UDP Server status ONLINE
- [ ] **PENTING**: Kalibrasi manual minimal 1x sebelum recording banyak
- [ ] Lihat real-time flex values di panel
- [ ] CSV akan otomatis normalized saat disimpan
