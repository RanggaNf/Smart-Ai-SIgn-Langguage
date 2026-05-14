# Update Sistem Kalibrasi Manual + Display Sensor Real-Time

## ✅ Perubahan yang Telah Dilakukan

### 1. **Kalibrasi Manual** (bukan auto-trigger)

- ❌ Hapus auto-trigger setiap 10 gesture
- ✅ Tambah **button "⚙️ KALIBRASI"** manual di UI
- ✅ User dapat kalibrasi kapan saja dengan klik button

### 2. **System Warning untuk 10 Gesture**

Per kategori (ANGKA, HURUF, KATA, FRASA):

- Ketika mencapai **10 gesture pertama** → Muncul **messagebox** notifikasi
- Setiap **kelipatan 10 gesture** → Alert di log: "⚠️ N gestures dari [KATEGORI] - Kalibrasi direkomendasikan!"
- **Tidak otomatis** trigger kalibrasi, hanya reminder

### 3. **Real-Time Sensor Display**

Tampilan live flex values dari Arduino:

- **Tangan Kiri**: `[ADC_1, ADC_2, ADC_3, ADC_4, ADC_5]`
- **Tangan Kanan**: `[ADC_1, ADC_2, ADC_3, ADC_4, ADC_5]`
- Update setiap frame saat menerima UDP data

### 4. **Gesture Counter Per Kategori**

- Display: "Gesture dlm kategori: N"
- Update otomatis saat recording
- Membantu track kapan mencapai 10 gesture

## 📊 Alur Kerja Baru

```
Recording Gesture 1-9
    ↓ (lihat display sensor flex real-time)
Recording Gesture 10
    ↓
Warning popup → "✓ Sudah 10 gesture di kategori ANGKA!"
    ↓
User bisa klik button "⚙️ KALIBRASI" kapan saja
    ↓
Dialog kalibrasi → Buka tangan 5s → Tutup tangan 5s
    ↓
Auto-save min/max ke calibration_values.json
    ↓
Lanjut recording gesture berikutnya
```

## 🎯 Fitur Penting

| Fitur               | Sebelum                | Sekarang                |
| ------------------- | ---------------------- | ----------------------- |
| Trigger Kalibrasi   | Auto setiap 10 gesture | Manual button           |
| Warning 10 Gesture  | ✗                      | ✅ Message + Log        |
| Display Flex Sensor | ✗                      | ✅ Real-time ADC        |
| Category Counter    | ✗                      | ✅ Gesture per kategori |
| User Control        | Terbatas               | ✅ Full control         |

## 🎛️ UI Update

**Bagian Kanan (Right Column):**

```
┌─ STATUS RECORDING ──┐
│ Recording indicator │
│ Timer               │
│ Samples count       │
│ Progress            │
└─────────────────────┘

┌─ SENSOR FLEX (ADC) ─┐
│ Tangan Kiri: [...]  │
│ Tangan Kanan: [...] │
│ Category count: N   │
└─────────────────────┘

┌─ KONTROL ──────────┐
│ [START]             │
│ [RETRY]             │
│ [NEXT]              │
│ [⚙️ KALIBRASI]      │ ← NEW!
└─────────────────────┘

┌─ LOG ──────────────┐
│ ... messages ...    │
└─────────────────────┘
```

## ✅ Normalisasi Data

Tetap di Python (`normalize_flex_value()`):

```python
def normalize_flex_value(raw_adc, sensor_idx, hand):
    min_val = calibration_data[f'flex_min_{hand}'][sensor_idx]
    max_val = calibration_data[f'flex_max_{hand}'][sensor_idx]
    normalized = (raw_adc - min_val) / (max_val - min_val)
    return clamp(normalized, 0, 1)
```

- **Arduino**: Kirim ADC mentah (0-4095)
- **Python**: Tampilkan ADC mentah di UI, normalkan saat simpan CSV
- **CSV**: Data sudah 0-1, siap training

## 🚀 Cara Menggunakan

1. **Mulai Recording**
   - Start gesture 1-10
   - Lihat real-time flex values di panel kanan

2. **Setelah 10 Gesture**
   - Terima warning popup
   - Log akan tampilkan reminder

3. **Kalibrasikan**
   - Klik button "⚙️ KALIBRASI"
   - Buka tangan 5 detik
   - Tutup tangan 5 detik
   - Otomatis save

4. **Lanjut Recording**
   - Data sudah dinormalisasi dengan calibration terbaru

## 📝 Notes

- Kalibrasi adalah **manual, user-controlled**
- Warning hanya **reminder**, bukan blocking
- Display flex sensor membantu **monitoring** sensor kondisi
- Dapat kalibrasi berkali-kali, value akan di-overwrite
