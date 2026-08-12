<div align="center">

<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%" />

# 🧤 SmartGlove

**Sistem Penerjemah Bahasa Isyarat (SIBI) Berbasis Sensor & Machine Learning**

Menerjemahkan gestur tangan menjadi bahasa isyarat SIBI secara real-time menggunakan sensor flex, IMU MPU6050, dan model machine learning hierarchical berbasis TensorFlow.

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-FF6F00?style=for-the-badge&logo=tensorflow&logoColor=white)](https://www.tensorflow.org/)
[![Arduino](https://img.shields.io/badge/Arduino-00979D?style=for-the-badge&logo=arduino&logoColor=white)](https://www.arduino.cc/)
[![IoT](https://img.shields.io/badge/IoT-00ADD8?style=for-the-badge&logo=internetofthings&logoColor=white)](https://en.wikipedia.org/wiki/Internet_of_things)

`Sensor Flex` `IMU MPU6050` `TFLite` `UDP` `NumPy` `Pandas`

</div>

---

## 📋 Deskripsi

**SmartGlove** adalah sistem penerjemah **Bahasa Isyarat Indonesia (SIBI)** yang menggabungkan sensor flex dan IMU MPU6050 untuk menangkap gerakan tangan, lalu menerjemahkannya menjadi teks/gesture menggunakan model *machine learning* berbasis TensorFlow.

Sistem ini mencakup alur kerja lengkap: dari **data collection**, **training model hierarchical** (klasifikasi kategori lalu gesture spesifik), hingga **real-time prediction** melalui koneksi UDP dari sarung tangan ke aplikasi penerima. Model yang dihasilkan dikonversi ke **TFLite** agar ringan dan siap deploy pada perangkat embedded.

Project ini merupakan bagian dari portfolio pengembangan software oleh **Mohamad Rangga Nur Faizin**, yang mencakup berbagai bidang mulai dari *Android Development*, *Backend Engineering*, *Internet of Things (IoT)*, *Machine Learning*, hingga *Web Development*.

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
|---|---|
| 📥 **Data Collection Tool** | Alat pengumpulan data sensor untuk membangun dataset gesture |
| 🧠 **Hierarchical Model Training** | Training model bertingkat: klasifikasi kategori → klasifikasi gesture spesifik |
| ⚡ **Real-time Prediction** | Prediksi gesture secara langsung saat sarung tangan digunakan |
| 📡 **UDP Sensor Streaming** | Pengiriman data sensor secara real-time melalui protokol UDP |
| 📊 **Model Evaluation** | Evaluasi performa model (akurasi, confusion matrix, dll) |
| 📦 **TFLite Conversion** | Konversi model ke TensorFlow Lite untuk deployment ringan |
| 📚 **Dokumentasi Lengkap** | Panduan penggunaan dari data collection hingga deployment |

---

## 🛠️ Teknologi yang Digunakan

**Bahasa & Framework**
- 🐍 **Python** — Bahasa pemrograman utama untuk pipeline ML
- 🧮 **TensorFlow / Keras** — Framework untuk membangun dan melatih model machine learning
- 📦 **TFLite** — Format model ringan untuk deployment di perangkat embedded

**Hardware & IoT**
- 🔌 **Arduino** — Mikrokontroler untuk membaca sensor pada sarung tangan
- 🧲 **Sensor Flex** — Mendeteksi tekukan jari
- 🧭 **IMU MPU6050** — Mendeteksi orientasi dan pergerakan tangan
- 🌐 **UDP** — Protokol streaming data sensor secara real-time

**Data Processing**
- 🔢 **NumPy** — Komputasi numerik untuk pemrosesan data sensor
- 🐼 **Pandas** — Manipulasi dan analisis dataset

---

## 📁 Struktur Project

```
SmartGlove/
├── src/                    # Source code utama
│   ├── data_collection/    # Script pengumpulan data sensor
│   ├── training/           # Script training model hierarchical
│   ├── prediction/         # Real-time prediction via UDP
│   └── evaluation/         # Evaluasi & analisis performa model
├── firmware/                # Kode Arduino untuk sarung tangan
├── models/                  # Model hasil training (.h5, .tflite)
├── assets/                  # Asset (gambar, diagram, dll)
├── config/                  # Konfigurasi project
├── README.md                # Dokumentasi project
└── .gitignore                # File yang diabaikan Git
```

---

## 🚀 Cara Menjalankan

### Prasyarat

Pastikan tools berikut sudah terinstall di sistem Anda:

- [Python](https://www.python.org/) 3.8 atau lebih baru
- [Arduino IDE](https://www.arduino.cc/en/software) (untuk flashing firmware sarung tangan)
- Hardware: mikrokontroler kompatibel Arduino, sensor flex, dan modul IMU MPU6050

### Instalasi

```bash
# 1. Clone repository
git clone https://github.com/RanggaNf/SmartGlove.git
cd SmartGlove

# 2. Install dependencies Python
pip install -r requirements.txt
```

### Menjalankan

```bash
# 1. Flash firmware ke mikrokontroler menggunakan Arduino IDE
#    (buka folder firmware/ dan upload ke board)

# 2. Jalankan data collection (jika ingin membuat dataset baru)
python src/data_collection/collect.py

# 3. Jalankan training model
python src/training/train.py

# 4. Jalankan real-time prediction
python src/prediction/predict.py
```

---

## 📸 Screenshot

<img width="1672" height="941" alt="ChatGPT Image 12 Agu 2026, 09 27 14" src="https://github.com/user-attachments/assets/bf30e7b9-19e7-4007-a393-1232754762fd" />


<div align="center">
  <img src="https://via.placeholder.com/800x400?text=SmartGlove" alt="SmartGlove Screenshot" width="600"/>
</div>

---

## 📊 Status Project

| Info | Detail |
|---|---|
| **Status** | ✅ Completed |
| **Kategori** | IoT & Machine Learning |
| **Periode** | 2024 – 2025 |

---

## 🤝 Kontribusi

Project ini adalah project personal untuk portfolio. Namun, jika Anda tertarik untuk berkontribusi atau memberikan saran, silakan ikuti langkah berikut:

1. **Fork** repository ini
2. Buat branch fitur baru
   ```bash
   git checkout -b fitur-keren
   ```
3. Commit perubahan Anda
   ```bash
   git commit -m "Menambahkan fitur keren"
   ```
4. Push ke branch Anda
   ```bash
   git push origin fitur-keren
   ```
5. Buat **Pull Request**

---

## 📝 Lisensi

Project ini dibuat untuk keperluan **portfolio** dan **pembelajaran**.

---

## 👤 Author

<div align="center">

<a href="https://github.com/RanggaNf">
  <img src="https://github.com/RanggaNf.png" width="100" style="border-radius: 50%;" alt="RanggaNf"/>
</a>

### Mohamad Rangga Nur Faizin

[![GitHub](https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white)](https://github.com/RanggaNf)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/rangganf)

🚀 Android Developer | IoT Engineer | Backend Developer | ML Enthusiast

</div>

---

<div align="center">

<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%" />

⭐ **Jangan lupa beri bintang jika project ini bermanfaat!**

</div>
