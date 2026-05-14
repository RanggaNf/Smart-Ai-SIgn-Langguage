# Gesture RILIS - Release Marker Guide

## Deskripsi

Gesture **RILIS** adalah gesture kontrol yang digunakan untuk menandai "pelepasan" atau "release" posisi tangan. Gesture ini berfungsi sebagai signal bahwa pengguna telah selesai dengan gesture sebelumnya dan siap untuk gesture berikutnya.

## Kategori

- **Kategori**: KONTROL
- **Label**: rilis
- **Format**: `KONTROL,rilis`
- **Total dalam Gesture List**: 1 gesture

## Penggunaan

### 1. **Perekaman Data (Data Collection)**

Saat merekam data gesture rilis:

- Mulai dengan tangan di posisi relaks/rilek (neutral position)
- Pastikan tidak memegang gesture apa pun
- Gerakan tangan kembali ke posisi netral/rilek
- Rekam 5 repetisi untuk setiap session

Simpan ke folder: `datashet/rilis/` atau `datashet1/rilis/`

### 2. **Pelatihan Model (Training)**

Gesture rilis akan dilatih bersama gesture lainnya:

```
Total gesture: 104
- HURUF: 26
- ANGKA: 15
- FRASA: 19
- KATA: 79
- KONTROL: 1 (rilis)

Total sampel = 104 × 5 reps × 9x augmentasi = 4.680 sampel
```

### 3. **Prediksi Real-time (Prediction)**

Saat menggunakan model untuk prediksi real-time:

- Model akan mengklasifikasi input sensor ke salah satu 104 gesture
- Ketika prediksi keluar sebagai "rilis", sistem mengetahui bahwa gesture sebelumnya telah selesai
- Confidence threshold khusus untuk "rilis" dapat dikonfigurasi

### 4. **Implementasi di Code**

Dalam script prediksi, Anda dapat menggunakan output "rilis" untuk:

```python
if predicted_gesture == "rilis":
    # Tandai bahwa gesture sebelumnya telah selesai
    gesture_complete = True
    print("Gesture rilis terdeteksi - ready untuk gesture berikutnya")
elif predicted_gesture != "rilis":
    # Proses gesture normal (huruf, angka, kata, frasa)
    process_gesture(predicted_gesture)
```

## Petunjuk Perekaman Data

### File CSV Format

Ketika merekam gesture rilis, pastikan CSV file memiliki format sesuai dengan gesture lain:

```
sensor1_x, sensor1_y, sensor1_z, sensor2_x, ..., sensorN_z
```

### Naming Convention

```
<gesture_index>_rep<repetition>_<timestamp>.csv
Contoh: 0_rep1_20260405_142813.csv
```

## Statistik Update

```
Sebelum: 103 gesture
Sesudah: 104 gesture (+1 untuk RILIS)

Sampel per gesture (dengan 5 reps + 8x augmentasi):
- Rata-rata: 36-40 sampel per class
- Total training: 3.744 sampel (80%)
- Status: LAYAK untuk produksi
```

## Rekomendasi Implementasi

### Phase 1: Data Collection

- [ ] Rekam 5 repetisi gesture "rilis" (tangan di posisi netral)
- [ ] Simpan ke `datashet/rilis/`
- [ ] Validasi bahwa file tersimpan dengan benar

### Phase 2: Model Training

- [ ] Update dataset dengan sampel "rilis"
- [ ] Jalankan training script dengan gesture list terbaru
- [ ] Verifikasi accuracy untuk class "rilis"
- [ ] Target accuracy: 80%+ untuk class rilis

### Phase 3: Integration

- [ ] Update real-time prediction script untuk handle "rilis"
- [ ] Implementasi logic untuk end-of-gesture detection
- [ ] Test accuracy di environment sesungguhnya

### Phase 4: Deployment

- [ ] Deploy model terbaru ke Arduino/Device
- [ ] Test full pipeline dengan sensor real
- [ ] Dokumentasi gesture sequence akhir

## Notes

- Gesture "rilis" WAJIB tidak boleh tertarik oleh gesture lain
- Confidence untuk "rilis" harus distinctive dari gesture komunikasi
- Pertimbangkan untuk menggunakan threshold berbeda jika diperlukan
- Rekam dengan variasi posisi tangan yang berbeda untuk robust detection

---

**Last Updated**: 2026-04-05
**Version**: 1.0
