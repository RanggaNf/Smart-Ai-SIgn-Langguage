"""
Smart Glove — Sensor Data Augmentation
Mengubah 5 repetisi menjadi 45 sampel per gesture (8x augmentasi)

Teknik yang dipakai (semuanya physics-valid untuk data sensor IMU + flex):
  1. gaussian_noise       — simulasi noise elektronik berbeda
  2. magnitude_scale      — variasi tekanan/amplitudo gerakan
  3. time_warp            — orang yang sama gesture lebih cepat/lambat
  4. channel_dropout      — simulasi sensor kadang dropout 1 kanal
  5. rotation_perturb     — sedikit variasi orientasi tangan
  6. combo_noise_scale    — gabungan noise + scale (paling realistis)
  7. temporal_shift       — gesture dimulai sedikit lebih awal/lambat
  8. mirror_flex          — simulasi variasi individual anatomi tangan
"""

import numpy as np
from typing import List, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# INDEX KOLOM SENSOR (sesuai format data_collection.py Anda)
# ─────────────────────────────────────────────────────────────────────────────
# Kolom CSV (setelah drop timestamp & repetition):
# [0:5]   flex1_L  .. flex5_L     (flex kiri)
# [5:8]   accX_L, accY_L, accZ_L  (accelerometer kiri)
# [8:11]  gyroX_L, gyroY_L, gyroZ_L (gyro kiri)
# [11:16] flex1_R  .. flex5_R     (flex kanan)
# [16:19] accX_R, accY_R, accZ_R  (accelerometer kanan)
# [19:22] gyroX_R, gyroY_R, gyroZ_R (gyro kanan)

FLEX_L   = slice(0, 5)
ACCEL_L  = slice(5, 8)
GYRO_L   = slice(8, 11)
FLEX_R   = slice(11, 16)
ACCEL_R  = slice(16, 19)
GYRO_R   = slice(19, 22)


# ─────────────────────────────────────────────────────────────────────────────
# TEKNIK AUGMENTASI INDIVIDUAL
# ─────────────────────────────────────────────────────────────────────────────

def gaussian_noise(seq: np.ndarray, snr_db: float = 25.0,
                   rng: np.random.Generator = None) -> np.ndarray:
    """
    Tambah Gaussian noise dengan SNR tertentu.
    SNR 25dB = noise sangat halus (nyaris tidak terasa)
    SNR 15dB = noise lebih terasa (simulasi kondisi baterai lemah)
    """
    if rng is None:
        rng = np.random.default_rng()
    seq = seq.copy()
    signal_power = np.mean(seq ** 2) + 1e-8
    noise_power  = signal_power / (10 ** (snr_db / 10))
    noise = rng.normal(0, np.sqrt(noise_power), seq.shape).astype(np.float32)
    return seq + noise


def magnitude_scale(seq: np.ndarray, scale: float = None,
                    rng: np.random.Generator = None) -> np.ndarray:
    """
    Skala amplitudo sinyal.
    Mensimulasikan variasi kuat lemah gerakan orang yang sama.
    scale=0.85..1.15 agar tidak terlalu ekstrem.
    """
    if rng is None:
        rng = np.random.default_rng()
    if scale is None:
        scale = float(rng.uniform(0.85, 1.15))
    seq = seq.copy()
    # Scale flex dan IMU secara independen (satuan berbeda)
    seq[:, FLEX_L]  *= scale
    seq[:, FLEX_R]  *= scale
    seq[:, ACCEL_L] *= scale
    seq[:, ACCEL_R] *= scale
    seq[:, GYRO_L]  *= scale
    seq[:, GYRO_R]  *= scale
    return seq.astype(np.float32)


def time_warp(seq: np.ndarray, warp_factor: float = None,
              rng: np.random.Generator = None) -> np.ndarray:
    """
    Peregangan/kompresi waktu dengan interpolasi linear.
    warp_factor 0.9 = gesture 10% lebih cepat
    warp_factor 1.1 = gesture 10% lebih lambat
    Output selalu memiliki panjang sama dengan input.
    """
    if rng is None:
        rng = np.random.default_rng()
    if warp_factor is None:
        warp_factor = float(rng.uniform(0.88, 1.12))

    T, F = seq.shape
    # Buat timeline baru
    src_times = np.linspace(0, T - 1, T)
    dst_times = np.linspace(0, T - 1, int(T * warp_factor))

    # Interpolasi setiap fitur
    warped = np.zeros((int(T * warp_factor), F), dtype=np.float32)
    for f in range(F):
        warped[:, f] = np.interp(dst_times, src_times, seq[:, f])

    # Truncate atau pad ke panjang asli
    if len(warped) >= T:
        return warped[:T]
    else:
        pad = np.zeros((T - len(warped), F), dtype=np.float32)
        return np.vstack([warped, pad]).astype(np.float32)


def channel_dropout(seq: np.ndarray, drop_prob: float = 0.05,
                    rng: np.random.Generator = None) -> np.ndarray:
    """
    Zero-out channel sensor acak dengan probabilitas kecil.
    Mensimulasikan sensor flex yang sesekali kehilangan kontak.
    Hanya drop pada flex sensor (bukan IMU) karena lebih sering terjadi.
    """
    if rng is None:
        rng = np.random.default_rng()
    seq = seq.copy()
    # Pilih satu flex sensor acak untuk di-drop (bukan semua)
    flex_indices = list(range(5)) + list(range(11, 16))
    if rng.random() < drop_prob * len(flex_indices):
        drop_col = int(rng.choice(flex_indices))
        # Drop hanya pada sebagian frame (bukan seluruh sequence)
        drop_start = int(rng.integers(0, len(seq) // 2))
        drop_end   = drop_start + int(rng.integers(5, 15))
        seq[drop_start:drop_end, drop_col] = 0.0
    return seq.astype(np.float32)


def rotation_perturb(seq: np.ndarray, max_deg: float = 5.0,
                     rng: np.random.Generator = None) -> np.ndarray:
    """
    Perturb sinyal accelerometer dan gyro dengan rotasi kecil.
    Mensimulasikan variasi posisi tangan yang tidak persis sama setiap rekaman.
    Hanya rotasi pada bidang XY (paling umum variasi dalam penggunaan nyata).
    """
    if rng is None:
        rng = np.random.default_rng()
    angle = float(rng.uniform(-max_deg, max_deg)) * np.pi / 180
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    rot_2d = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float32)

    seq = seq.copy()
    for sl in [ACCEL_L, ACCEL_R, GYRO_L, GYRO_R]:
        xy = seq[:, sl.start:sl.start + 2]          # ambil X, Y
        seq[:, sl.start:sl.start + 2] = xy @ rot_2d.T
    return seq.astype(np.float32)


def temporal_shift(seq: np.ndarray, max_shift: int = 8,
                   rng: np.random.Generator = None) -> np.ndarray:
    """
    Geser sequence secara temporal (pad nol di awal atau akhir).
    Mensimulasikan variasi kapan gesture mulai dalam window rekaman.
    """
    if rng is None:
        rng = np.random.default_rng()
    shift = int(rng.integers(-max_shift, max_shift + 1))
    if shift == 0:
        return seq.copy()
    if shift > 0:
        return np.vstack([
            np.zeros((shift, seq.shape[1]), dtype=np.float32),
            seq[:-shift]
        ]).astype(np.float32)
    else:
        return np.vstack([
            seq[-shift:],
            np.zeros((-shift, seq.shape[1]), dtype=np.float32)
        ]).astype(np.float32)


def mirror_flex(seq: np.ndarray, rng: np.random.Generator = None) -> np.ndarray:
    """
    Refleksi kecil pada nilai flex sensor (simulasi variasi anatomi tangan).
    Setiap jari berbeda sedikit panjang/kekakuannya antar orang.
    Skala acak 0.92–1.08 per jari secara independen.
    """
    if rng is None:
        rng = np.random.default_rng()
    seq = seq.copy()
    for i in range(5):
        scale_l = float(rng.uniform(0.92, 1.08))
        scale_r = float(rng.uniform(0.92, 1.08))
        seq[:, i]      *= scale_l   # flex L
        seq[:, 11 + i] *= scale_r   # flex R
    return seq.astype(np.float32)


def combo_noise_scale(seq: np.ndarray,
                      rng: np.random.Generator = None) -> np.ndarray:
    """Kombinasi noise halus + magnitude scale — paling realistis."""
    if rng is None:
        rng = np.random.default_rng()
    seq = gaussian_noise(seq, snr_db=float(rng.uniform(18, 30)), rng=rng)
    seq = magnitude_scale(seq, rng=rng)
    return seq


# ─────────────────────────────────────────────────────────────────────────────
# AUGMENTOR UTAMA
# ─────────────────────────────────────────────────────────────────────────────

class SensorDataAugmenter:
    """
    Menghasilkan N augmented samples dari satu sequence original.

    Teknik yang dipakai (8 augmentasi per sampel):
      0. noise_soft      — gaussian noise SNR 28dB
      1. noise_hard      — gaussian noise SNR 18dB
      2. scale_down      — magnitude 0.88x
      3. scale_up        — magnitude 1.12x
      4. time_fast       — time warp 0.90x (lebih cepat)
      5. time_slow       — time warp 1.10x (lebih lambat)
      6. combo           — noise + scale
      7. full_augment    — noise + scale + warp + shift + mirror

    Total: 1 original + 8 augmentasi = 9 sampel per rekaman asli
    Dengan 5 rekaman: 5 × 9 = 45 sampel per gesture
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def augment_one(self, seq: np.ndarray) -> List[np.ndarray]:
        """
        Hasilkan 8 augmented versions dari satu sequence.
        Args:
            seq: np.array (T, 22)
        Returns:
            list of 8 np.array (T, 22)
        """
        r = self.rng
        return [
            gaussian_noise(seq,     snr_db=28.0,        rng=r),   # 0: noise halus
            gaussian_noise(seq,     snr_db=18.0,        rng=r),   # 1: noise lebih keras
            magnitude_scale(seq,    scale=0.88,         rng=r),   # 2: amplitudo kecil
            magnitude_scale(seq,    scale=1.12,         rng=r),   # 3: amplitudo besar
            time_warp(seq,          warp_factor=0.90,   rng=r),   # 4: lebih cepat
            time_warp(seq,          warp_factor=1.10,   rng=r),   # 5: lebih lambat
            combo_noise_scale(seq,                      rng=r),   # 6: noise+scale
            self._full_augment(seq),                               # 7: kombinasi semua
        ]

    def _full_augment(self, seq: np.ndarray) -> np.ndarray:
        """Kombinasi lengkap semua teknik."""
        r = self.rng
        seq = gaussian_noise(seq,   snr_db=float(r.uniform(20, 28)), rng=r)
        seq = magnitude_scale(seq,                                    rng=r)
        seq = time_warp(seq,                                          rng=r)
        seq = temporal_shift(seq,   max_shift=6,                     rng=r)
        seq = mirror_flex(seq,                                        rng=r)
        seq = rotation_perturb(seq, max_deg=4.0,                     rng=r)
        return seq

    def augment_dataset(
        self,
        X_raw: List[np.ndarray],
        y: List[int],
        include_original: bool = True,
        verbose: bool = True,
    ) -> Tuple[List[np.ndarray], List[int]]:
        """
        Augmentasi seluruh dataset.

        Args:
            X_raw           : list of (T_i, 22) arrays
            y               : list of int label indices
            include_original: sertakan data asli (default True)
            verbose         : print progress

        Returns:
            X_aug, y_aug — dataset yang sudah diperbesar ~9x
        """
        X_aug, y_aug = [], []

        if include_original:
            X_aug.extend(X_raw)
            y_aug.extend(y)

        for i, (seq, label) in enumerate(zip(X_raw, y)):
            augmented = self.augment_one(np.array(seq, dtype=np.float32))
            X_aug.extend(augmented)
            y_aug.extend([label] * len(augmented))

            if verbose and (i + 1) % 50 == 0:
                print(f"  Augmentasi: {i+1}/{len(X_raw)} sequences diproses...")

        if verbose:
            orig = len(X_raw) if include_original else 0
            added = len(X_raw) * 8
            print(f"\nAugmentasi selesai:")
            print(f"  Original   : {orig}")
            print(f"  Augmented  : {added}")
            print(f"  Total      : {len(X_aug)}")

            # Hitung distribusi per kelas
            y_arr = np.array(y_aug)
            unique, counts = np.unique(y_arr, return_counts=True)
            print(f"  Sampel per kelas: min={counts.min()}, max={counts.max()}, mean={counts.mean():.1f}")

        return X_aug, y_aug

    def augment_balanced(
        self,
        X_raw: List[np.ndarray],
        y: List[int],
        target_per_class: int = 45,
        verbose: bool = True,
    ) -> Tuple[List[np.ndarray], List[int]]:
        """
        Augmentasi dengan target sampel per kelas (untuk dataset tidak seimbang).
        Gesture dengan rekaman sedikit mendapat lebih banyak augmentasi.

        Args:
            target_per_class: target minimum sampel per gesture
        """
        from collections import defaultdict

        # Kelompokkan per kelas
        class_samples = defaultdict(list)
        for seq, label in zip(X_raw, y):
            class_samples[label].append(np.array(seq, dtype=np.float32))

        X_aug, y_aug = [], []

        for label, seqs in class_samples.items():
            # Selalu sertakan original
            X_aug.extend(seqs)
            y_aug.extend([label] * len(seqs))

            # Hitung berapa augmentasi yang dibutuhkan
            needed = max(0, target_per_class - len(seqs))
            if needed == 0:
                continue

            # Cycle melalui sampel original untuk augmentasi
            aug_count = 0
            cycle_idx = 0
            while aug_count < needed:
                seq = seqs[cycle_idx % len(seqs)]
                augmented = self.augment_one(seq)
                # Pilih augmentasi acak
                pick = augmented[int(self.rng.integers(0, len(augmented)))]
                X_aug.append(pick)
                y_aug.append(label)
                aug_count += 1
                cycle_idx += 1

        if verbose:
            y_arr = np.array(y_aug)
            unique, counts = np.unique(y_arr, return_counts=True)
            print(f"Balanced augmentation selesai:")
            print(f"  Total samples: {len(X_aug)}")
            print(f"  Per kelas: min={counts.min()}, max={counts.max()}, mean={counts.mean():.1f}")

        return X_aug, y_aug


# ─────────────────────────────────────────────────────────────────────────────
# VALIDASI AUGMENTASI (pastikan tidak merusak distribusi data)
# ─────────────────────────────────────────────────────────────────────────────

def validate_augmentation(X_orig: np.ndarray, X_aug_list: List[np.ndarray],
                           sample_idx: int = 0, feature_idx: int = 5) -> None:
    """
    Plot original vs augmented untuk verifikasi visual.
    Jalankan di notebook setelah augmentasi.
    """
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 3, figsize=(14, 8), sharey=True)
        titles = ['original', 'noise halus', 'noise keras', 'scale kecil',
                  'scale besar', 'cepat', 'lambat', 'combo', 'full augment']

        all_data = [X_orig[sample_idx]] + X_aug_list

        for ax, data, title in zip(axes.flat, all_data, titles):
            ax.plot(data[:, feature_idx], linewidth=1.5, color='#3B82F6')
            ax.set_title(title, fontsize=9)
            ax.grid(alpha=0.3)
            ax.set_ylabel('accX_L' if feature_idx == 5 else f'col_{feature_idx}', fontsize=8)

        plt.suptitle(f'Augmentasi Sample #{sample_idx} — Feature {feature_idx}',
                     fontsize=12, fontweight='bold')
        plt.tight_layout()
        plt.savefig('augmentation_validation.png', dpi=100, bbox_inches='tight')
        plt.show()
        print("Saved: augmentation_validation.png")

    except ImportError:
        print("matplotlib tidak tersedia — skip visualisasi")


print("""
╔══════════════════════════════════════════════════════════════╗
║  Sensor Data Augmenter — 8 teknik untuk data sensor glove   ║
║  5 rep × 9 (orig+aug) = 45 sampel/gesture                   ║
║  103 gesture × 45 = 4.635 sampel total                      ║
╚══════════════════════════════════════════════════════════════╝
""")
