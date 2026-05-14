# Sistem Kalibrasi Sensor Flex SmartGlove

## Penjelasan Singkat

Sistem kalibrasi memastikan data sensor flex yang akurat dengan merekam nilai min-max setiap 10 gesture.

### Alur Kalibrasi:

1. **Setiap 10 gesture selesai**, dialog "SENSOR CALIBRATION" muncul otomatis
2. **Fase 1 (5 detik)**: Buka tangan penuh sepenuhnya → Sistem catat MAX value setiap sensor
3. **Fase 2 (5 detik)**: Tutup tangan (genggam) → Sistem catat MIN value setiap sensor
4. **Auto-save**: Nilai min-max otomatis disimpan ke `calibration_values.json`

## File Kalibrasi

**File**: `calibration_values.json`

Struktur:

```json
{
  "flex_min_L": [nilai_min_sensor1, nilai_min_sensor2, ...],
  "flex_max_L": [nilai_max_sensor1, nilai_max_sensor2, ...],
  "flex_min_R": [nilai_min_sensor1, nilai_min_sensor2, ...],
  "flex_max_R": [nilai_max_sensor1, nilai_max_sensor2, ...]
}
```

- **Nilai digital**: 0-4095 (ADC raw)
- **Nilai di CSV**: 0-1 (sudah dinormalisasi)

## Aliran Data

### Arduino → Python:

```
ADC Raw (0-4095)
     ↓ [UDP]
  Python
     ↓ [normalize_flex_value()]
  CSV (0-1)
```

### Proses Normalisasi:

```python
normalized = (raw_adc - min_calib) / (max_calib - min_calib)
# Hasil di clamp ke 0-1
```

## Poin Penting

- ✅ **Arduino mengirim ADC mentah**, bukan value yang sudah dinormalisasi
- ✅ **Kalibrasi dilakukan di Python**, bukan Arduino
- ✅ **Min-Max di-update setiap 10 gesture**, untuk adaptasi terhadap kondisi
- ✅ **Data di CSV sudah dinormalisasi 0-1**, siap untuk training

## Testing

Untuk test kalibrasi:

1. Jalankan `smart_glove_data_collection.py`
2. Mulai recording gesture
3. Setelah 10 gesture, dialog kalibrasi akan muncul
4. Ikuti instruksi di dialog
5. Check `calibration_values.json` sudah terupdate

## Troubleshooting

**Kalibrasi tidak muncul?**

- Pastikan UDP server sudah ONLINE
- Pastikan gesture sudah mencapai 10 buah

**Nilai normalisasi aneh (semua 0 atau semua 1)?**

- Kalibrasi mungkin belum dilakukan → lakukan manual kalibrasi
- Atau nilai min-max mungkin sama → pastikan membuka/tutup tangan dengan maksimal

**Reset kalibrasi?**

- Hapus `calibration_values.json`, sistem akan gunakan default values
- Pada recording berikutnya, dialog kalibrasi akan muncul di gesture ke-10
