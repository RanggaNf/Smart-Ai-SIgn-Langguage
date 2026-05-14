# ⚠️ PENTING: Arduino Code Update Required

Sistem kalibrasi baru memerlukan update Arduino code!

## Perubahan Arduino:

### GloveMaster.ino & GloveSlave.ino

- **Sebelum**: Mengirim nilai **normalized (0-1)** dari ADC
- **Sesudah**: Mengirim nilai **ADC mentah (0-4095)**

### Apa yang diganti:

```cpp
// SEBELUM (OLD):
localData.flex[0] = normalizeFlexValue(analogRead(FLEX_PIN_1), 0);

// SESUDAH (NEW):
localData.flex[0] = (float)analogRead(FLEX_PIN_1);
```

## ACTION REQUIRED:

1. **Upload Arduino code baru** ke kedua ESP32:
   - ✅ GloveMaster.ino (sudah diperbarui)
   - ✅ GloveSlave.ino (sudah diperbarui)

2. **Verifikasi Serial Monitor**:
   - Data flex harus menunjukkan nilai **0-4095** (bukan 0-1)
   - Contoh: `Flex:[2150.00, 1875.00, ...]` bukan `Flex:[0.45, 0.32, ...]`

3. **Jalankan Data Collection**:
   - Sistem akan otomatis minta kalibrasi setiap 10 gesture
   - Nilai min-max akan di-record otomatis

## Status Perubahan:

| File                           | Status     | Perubahan               |
| ------------------------------ | ---------- | ----------------------- |
| GloveMaster.ino                | ✅ Updated | Kirim ADC mentah        |
| GloveSlave.ino                 | ✅ Updated | Kirim ADC mentah        |
| smart_glove_data_collection.py | ✅ Updated | Normalisasi + kalibrasi |
| calibration_values.json        | 🆕 New     | Min-max storage         |

## Catatan Teknis:

- **Nilai ADC**: 0-4095 (dari `analogRead()`)
- **Normalisasi dilakukan di**: Python (`normalize_flex_value()`)
- **Saat disimpan ke CSV**: Sudah dalam format 0-1
- **Kalibrasi interval**: Setiap 10 gesture

## Next Step:

```
1. Upload Arduino code → Verify output showing 0-4095
2. Jalankan data collection
3. Record 10 gesture → Dialog kalibrasi muncul otomatis
4. Ikuti instruksi kalibrasi (buka tangan 5s, tutup tangan 5s)
5. Selesai! System akan normalize semua data menggunakan calibration ini
```
