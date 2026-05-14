"""
Smart Glove — Advanced Gesture Recognition System
Versi produksi untuk percakapan dua arah realtime BISINDO

Perbaikan dari versi lama:
- Sliding window per-kategori (50–120 frame) — bukan 200 frame flat
- Bug residual connection Transformer diperbaiki
- Bug shape mismatch Seq2Seq Attention diperbaiki
- Delta + acceleration features aktif dipakai
- Adaptive threshold segmenter dengan kalibrasi baseline
- Confidence gating — tidak ada output saat tangan diam
- Padding di BELAKANG (post-padding) bukan depan
- Inference engine siap untuk Android TFLite
"""

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, Model
from sklearn.preprocessing import StandardScaler
import json
import os
import collections


# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

SAMPLING_RATE = 100          # Hz — sesuai ESP32 Anda
NUM_RAW_FEATURES = 22        # 5L flex + 3L accel + 3L gyro + 5R flex + 3R accel + 3R gyro
NUM_DELTA_FEATURES = 22      # velocity (Δ per frame)
NUM_ACCEL_FEATURES = 22      # acceleration (ΔΔ per frame)
NUM_TOTAL_FEATURES = NUM_RAW_FEATURES + NUM_DELTA_FEATURES + NUM_ACCEL_FEATURES  # 66

# Window per kategori (frames @ 100Hz)
# HURUF/ANGKA = 500ms, KATA = 700ms, FRASA = 1200ms
CATEGORY_WINDOW = {
    'HURUF': 50,
    'ANGKA': 50,
    'KATA':  70,
    'FRASA': 120,
    'ALL':   80,   # window gabungan untuk satu model universal
}

# Stride sliding window
INFERENCE_STRIDE     = 15   # prediksi setiap 150ms
CONFIDENCE_THRESHOLD = 0.72  # buang prediksi di bawah ini
STABILITY_WINDOW     = 3    # gesture harus konsisten N prediksi berturut-turut


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — ATTENTION LAYER (diperbaiki: query/value shape konsisten)
# ─────────────────────────────────────────────────────────────────────────────

class AttentionLayer(layers.Layer):
    """
    Bahdanau-style additive attention.
    Dipakai sebagai modul internal BiLSTM model.
    Input:
        values  — (batch, T, H)   encoder hidden states
    Output:
        context — (batch, H)      weighted sum
        weights — (batch, T, 1)   attention weights
    """

    def __init__(self, units=128, **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.W = layers.Dense(units, use_bias=False)
        self.V = layers.Dense(1, use_bias=False)

    def call(self, values):
        # values: (batch, T, H)
        score = self.V(tf.nn.tanh(self.W(values)))          # (batch, T, 1)
        weights = tf.nn.softmax(score, axis=1)              # (batch, T, 1)
        context = tf.reduce_sum(weights * values, axis=1)   # (batch, H)
        return context, weights

    def get_config(self):
        cfg = super().get_config()
        cfg['units'] = self.units
        return cfg
    
    @classmethod
    def from_config(cls, config):
        return cls(**config)


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — MODEL UTAMA: BiLSTM + Self-Attention (universal, satu model)
# ─────────────────────────────────────────────────────────────────────────────

def build_bilstm_attention_model(
    num_gestures: int,
    window_size: int = 80,
    num_features: int = NUM_TOTAL_FEATURES,  # 66 dengan delta+accel
    lstm_units: int = 128,
    dense_units: int = 128,
    dropout_rate: float = 0.35,
) -> Model:
    """
    BiLSTM + Attention untuk klasifikasi gesture single-label.

    Input  : (batch, window_size, num_features)
    Output : (batch, num_gestures)  softmax probabilities

    Arsitektur:
        Input → BiLSTM(128) → Self-Attention → Dense(128) → Dropout → Dense(64) → Softmax

    Catatan:
    - num_features=66: raw(22) + delta(22) + accel(22)
    - window_size berbeda per kategori, tapi model universal pakai CATEGORY_WINDOW['ALL']=80
    """

    inp = layers.Input(shape=(window_size, num_features), name='sensor_input')

    # ── Layer 1: Bidirectional LSTM ──────────────────────────────────────────
    x = layers.Bidirectional(
        layers.LSTM(lstm_units, return_sequences=True, dropout=0.2, recurrent_dropout=0.1),
        name='bilstm_1'
    )(inp)
    # x shape: (batch, window_size, lstm_units*2 = 256)

    # ── Layer 2: Second BiLSTM (deeper temporal understanding) ───────────────
    x = layers.Bidirectional(
        layers.LSTM(lstm_units // 2, return_sequences=True, dropout=0.2),
        name='bilstm_2'
    )(x)
    # x shape: (batch, window_size, lstm_units = 128)

    # ── Layer 3: Self-Attention ───────────────────────────────────────────────
    context, attn_weights = AttentionLayer(units=64, name='self_attention')(x)
    # context shape: (batch, 128)

    # ── Layer 4: Dense head ───────────────────────────────────────────────────
    x = layers.Dense(dense_units, activation='relu',
                     kernel_regularizer=keras.regularizers.l2(1e-4),
                     name='dense_1')(context)
    x = layers.BatchNormalization(name='bn_1')(x)
    x = layers.Dropout(dropout_rate, name='dropout_1')(x)

    x = layers.Dense(64, activation='relu', name='dense_2')(x)
    x = layers.Dropout(dropout_rate * 0.5, name='dropout_2')(x)

    out = layers.Dense(num_gestures, activation='softmax', name='output')(x)

    model = Model(inputs=inp, outputs=out, name='GloveSpeak_BiLSTM_Attention')
    return model


# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — MODEL ALTERNATIF: TCN (Temporal Convolutional Network)
#          Lebih cepat dari LSTM, sangat baik untuk sinyal sensor
# ─────────────────────────────────────────────────────────────────────────────

def _tcn_residual_block(x, filters: int, kernel_size: int, dilation: int,
                         dropout_rate: float, name_prefix: str):
    """
    TCN residual block dengan dilated causal convolution.
    residual = input + Conv1D(input) — koneksi residual yang benar.
    """
    # Dilated causal conv
    conv = layers.Conv1D(
        filters, kernel_size, padding='causal',
        dilation_rate=dilation, activation='relu',
        kernel_initializer='he_normal',
        name=f'{name_prefix}_conv1'
    )(x)
    conv = layers.LayerNormalization(name=f'{name_prefix}_ln1')(conv)
    conv = layers.SpatialDropout1D(dropout_rate, name=f'{name_prefix}_drop1')(conv)

    conv = layers.Conv1D(
        filters, kernel_size, padding='causal',
        dilation_rate=dilation, activation='relu',
        kernel_initializer='he_normal',
        name=f'{name_prefix}_conv2'
    )(conv)
    conv = layers.LayerNormalization(name=f'{name_prefix}_ln2')(conv)
    conv = layers.SpatialDropout1D(dropout_rate, name=f'{name_prefix}_drop2')(conv)

    # Residual projection jika dimensi berbeda
    if x.shape[-1] != filters:
        x = layers.Conv1D(filters, 1, padding='same',
                          name=f'{name_prefix}_proj')(x)

    return layers.Add(name=f'{name_prefix}_add')([conv, x])


def build_tcn_model(
    num_gestures: int,
    window_size: int = 80,
    num_features: int = NUM_TOTAL_FEATURES,
    filters: int = 64,
    kernel_size: int = 3,
    dropout_rate: float = 0.2,
) -> Model:
    """
    Temporal Convolutional Network untuk gesture recognition.

    Keunggulan vs LSTM:
    - Inferensi ~3× lebih cepat (tidak ada state yang harus di-carry)
    - Dapat di-parallelisasi sepenuhnya
    - Receptive field eksplisit dan dapat dikontrol lewat dilation

    Dilation rates: [1, 2, 4, 8] → receptive field = 1+2+4+8 = 15× kernel_size
    """
    inp = layers.Input(shape=(window_size, num_features), name='sensor_input')

    x = layers.Conv1D(filters, 1, padding='same', name='input_proj')(inp)

    # Stack dilated blocks — receptive field tumbuh eksponensial
    for i, dilation in enumerate([1, 2, 4, 8]):
        x = _tcn_residual_block(
            x, filters=filters, kernel_size=kernel_size,
            dilation=dilation, dropout_rate=dropout_rate,
            name_prefix=f'tcn_{i}'
        )

    # Global average pool + head
    x = layers.GlobalAveragePooling1D(name='gap')(x)
    x = layers.Dense(128, activation='relu',
                     kernel_regularizer=keras.regularizers.l2(1e-4),
                     name='dense_1')(x)
    x = layers.Dropout(dropout_rate, name='dropout_final')(x)
    out = layers.Dense(num_gestures, activation='softmax', name='output')(x)

    model = Model(inputs=inp, outputs=out, name='GloveSpeak_TCN')
    return model


# ─────────────────────────────────────────────────────────────────────────────
# PART 4 — PREPROCESSING: delta + acceleration features, post-padding
# ─────────────────────────────────────────────────────────────────────────────

class GloveSensorPreprocessor:
    """
    Preprocessing pipeline untuk data sensor sarung tangan.

    Fitur yang dihasilkan (22 → 66):
      [0:22]  raw sensor (normalized)
      [22:44] delta / velocity  (Δ frame)
      [44:66] acceleration       (ΔΔ frame)

    Padding: POST-PADDING (nol di akhir, bukan di awal) — model tidak
    melihat noise di awal seperti versi lama.
    """

    def __init__(self, scaler_mean=None, scaler_scale=None):
        self.scaler_mean  = scaler_mean   # np.array (22,)
        self.scaler_scale = scaler_scale  # np.array (22,)
        self._fitted = (scaler_mean is not None)

    # ── Fit dari data training ────────────────────────────────────────────────
    def fit(self, X_raw_list: list):
        """
        Hitung mean & std dari semua frame di seluruh dataset.
        X_raw_list: list of np.array shape (T_i, 22)
        """
        all_frames = np.vstack(X_raw_list)   # (N_total, 22)
        self.scaler_mean  = all_frames.mean(axis=0)
        self.scaler_scale = all_frames.std(axis=0) + 1e-7
        self._fitted = True
        return self

    def transform_sequence(self, raw: np.ndarray, window_size: int) -> np.ndarray:
        """
        Transformasi satu sequence mentah ke tensor siap model.

        Args:
            raw         : np.array (T, 22) — bisa T < atau > window_size
            window_size : target frame

        Returns:
            np.array (window_size, 66)
        """
        assert self._fitted, "Panggil fit() terlebih dahulu"
        raw = np.array(raw, dtype=np.float32)

        # 1. Truncate dari AKHIR jika terlalu panjang (simpan gerakan terbaru)
        if len(raw) > window_size:
            raw = raw[-window_size:]

        # 2. Normalize
        normed = (raw - self.scaler_mean) / self.scaler_scale  # (T, 22)

        # 3. Delta (velocity): Δ[t] = normed[t] - normed[t-1]
        delta = np.zeros_like(normed)
        delta[1:] = normed[1:] - normed[:-1]

        # 4. Acceleration: ΔΔ[t] = delta[t] - delta[t-1]
        accel = np.zeros_like(normed)
        accel[1:] = delta[1:] - delta[:-1]

        # 5. Concatenate → (T, 66)
        combined = np.concatenate([normed, delta, accel], axis=-1)

        # 6. POST-PADDING jika kurang dari window_size (pad di akhir dengan nol)
        if len(combined) < window_size:
            pad = np.zeros((window_size - len(combined), combined.shape[1]),
                           dtype=np.float32)
            combined = np.concatenate([combined, pad], axis=0)

        return combined.astype(np.float32)

    def batch_transform(self, X_raw_list: list, window_size: int) -> np.ndarray:
        """
        Transformasi list sequence → batch tensor (N, window_size, 66)
        """
        return np.array([
            self.transform_sequence(seq, window_size) for seq in X_raw_list
        ], dtype=np.float32)

    def to_dict(self) -> dict:
        """Serialisasi ke dict untuk disimpan di model_metadata.json"""
        return {
            'mean':  self.scaler_mean.tolist(),
            'scale': self.scaler_scale.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            scaler_mean=np.array(d['mean'],  dtype=np.float32),
            scaler_scale=np.array(d['scale'], dtype=np.float32),
        )


# ─────────────────────────────────────────────────────────────────────────────
# PART 5 — SEGMENTER: adaptive threshold, noise-robust
# ─────────────────────────────────────────────────────────────────────────────

class AdaptiveGestureSegmenter:
    """
    Mendeteksi batas awal/akhir gesture dari stream sensor secara realtime.

    Perbaikan dari versi lama:
    - Threshold ADAPTIF berdasarkan baseline kalibrasi (tangan diam)
    - Hysteresis: onset threshold > offset threshold — menghindari chatter
    - Minimum gesture duration — abaikan spike pendek bukan gesture
    - Cooldown antar gesture — tidak double-detect
    """

    def __init__(
        self,
        onset_multiplier: float = 3.0,   # threshold = baseline * multiplier
        offset_multiplier: float = 1.5,
        smoothing_window: int = 10,       # frame
        min_gesture_frames: int = 20,     # gesture minimal 200ms
        cooldown_frames: int = 10,        # jeda antar gesture 100ms
    ):
        self.onset_mult   = onset_multiplier
        self.offset_mult  = offset_multiplier
        self.smooth_win   = smoothing_window
        self.min_frames   = min_gesture_frames
        self.cooldown     = cooldown_frames

        self.baseline_energy: float = 0.05   # di-update saat kalibrasi
        self._onset_thr: float  = 0.15
        self._offset_thr: float = 0.075

    def calibrate(self, rest_frames: np.ndarray):
        """
        Kalibrasi dengan 1–2 detik data tangan diam (wajib dipanggil sekali).
        rest_frames: (N, 22) — data saat tangan tidak bergerak
        """
        energies = np.array([self._frame_energy(f) for f in rest_frames])
        self.baseline_energy = float(np.percentile(energies, 90)) + 1e-6
        self._onset_thr  = self.baseline_energy * self.onset_mult
        self._offset_thr = self.baseline_energy * self.offset_mult
        return self

    def _frame_energy(self, frame: np.ndarray) -> float:
        """
        Energy gabungan flex + IMU.
        Accelerometer dan gyro diberi bobot lebih karena lebih informatif.
        """
        flex_L  = frame[0:5];   accel_L = frame[5:8];   gyro_L = frame[8:11]
        flex_R  = frame[11:16]; accel_R = frame[16:19]; gyro_R = frame[19:22]

        e_flex  = np.var(np.concatenate([flex_L, flex_R]))
        e_accel = np.var(np.concatenate([accel_L, accel_R])) * 8.0
        e_gyro  = np.var(np.concatenate([gyro_L, gyro_R]))  * 5.0
        return float(e_flex + e_accel + e_gyro)

    def detect_segments(self, stream: np.ndarray) -> list:
        """
        Deteksi gesture segments dari stream sensor.

        Args:
            stream: (T, 22) — sensor stream (bisa panjang)

        Returns:
            List of (start_idx, end_idx) dalam satuan frame
        """
        T = len(stream)
        energies = np.array([self._frame_energy(f) for f in stream])

        # Moving average smoothing
        kernel = np.ones(self.smooth_win) / self.smooth_win
        smoothed = np.convolve(energies, kernel, mode='same')

        segments = []
        in_gesture = False
        start = 0
        cooldown_counter = 0

        for i, e in enumerate(smoothed):
            if cooldown_counter > 0:
                cooldown_counter -= 1
                continue

            if not in_gesture:
                if e > self._onset_thr:
                    start = i
                    in_gesture = True
            else:
                if e < self._offset_thr:
                    duration = i - start
                    if duration >= self.min_frames:
                        segments.append((start, i))
                        cooldown_counter = self.cooldown
                    in_gesture = False

        # Gesture masih berjalan di akhir stream
        if in_gesture and (T - start) >= self.min_frames:
            segments.append((start, T))

        return segments

    def is_gesture_active(self, recent_frames: np.ndarray) -> bool:
        """
        Cek apakah gesture sedang terjadi dari buffer terbaru.
        Dipakai oleh sliding window inference agar tidak output saat diam.
        recent_frames: (N, 22) — N frame terakhir (misal 10 frame)
        """
        if len(recent_frames) == 0:
            return False
        avg_energy = np.mean([self._frame_energy(f) for f in recent_frames])
        return avg_energy > self._onset_thr


# ─────────────────────────────────────────────────────────────────────────────
# PART 6 — GRAMMAR POST-PROCESSOR (diperbaiki: tidak swap sembarangan)
# ─────────────────────────────────────────────────────────────────────────────

class GrammarPostprocessor:
    """
    Post-processing prediksi gesture untuk menghasilkan kalimat koheren.

    Perbaikan dari versi lama:
    - Tidak swap gesture sembarangan berdasarkan hardcoded list kecil
    - Confidence-gated: gesture dengan confidence < threshold diabaikan
    - Dedup: gesture yang sama berulang langsung (< 0.5 detik) di-merge
    - Sentence builder yang lebih natural
    """

    def __init__(self, min_confidence: float = CONFIDENCE_THRESHOLD):
        self.min_conf = min_confidence

        # Mapping gesture label → kalimat TTS yang lebih natural
        self.tts_map = {
            'namamu siapa'     : 'Siapa nama Anda?',
            'perkenalkan nama saya': 'Perkenalkan, nama saya...',
            'apa kabar'        : 'Apa kabar?',
            'terima kasih'     : 'Terima kasih.',
            'sama sama'        : 'Sama-sama.',
            'maaf'             : 'Maaf.',
            'tidak tahu'       : 'Saya tidak tahu.',
            'tidak mengerti'   : 'Saya tidak mengerti.',
            'tidak apa apa'    : 'Tidak apa-apa.',
            'ada bahaya'       : 'Ada bahaya! Tolong!',
            'panggil ambulan'  : 'Tolong panggil ambulans!',
            'saya tersesat'    : 'Saya tersesat, tolong bantu.',
            'sampai jumpa'     : 'Sampai jumpa.',
            'selamat jalan'    : 'Selamat jalan.',
            'selamat datang'   : 'Selamat datang.',
            'lama tidak bertemu': 'Lama tidak bertemu!',
            'hati hati'        : 'Hati-hati ya.',
            'assalamu alaykum wr wb': 'Assalamualaikum warahmatullahi wabarakatuh.',
        }

    def filter_and_deduplicate(
        self,
        predictions: list,   # list of {'gesture': str, 'confidence': float, 'timestamp_ms': int}
        merge_window_ms: int = 600,
    ) -> list:
        """
        Filter confidence rendah + deduplikasi gesture berulang dalam window waktu.
        """
        filtered = [p for p in predictions if p['confidence'] >= self.min_conf]

        if not filtered:
            return []

        # Dedup: gabungkan gesture yang sama dalam merge_window_ms
        merged = [filtered[0]]
        for p in filtered[1:]:
            last = merged[-1]
            time_diff = p.get('timestamp_ms', 0) - last.get('timestamp_ms', 0)
            same_gesture = p['gesture'] == last['gesture']
            if same_gesture and time_diff < merge_window_ms:
                # Pertahankan prediksi dengan confidence lebih tinggi
                if p['confidence'] > last['confidence']:
                    merged[-1] = p
            else:
                merged.append(p)

        return merged

    def to_sentence(self, gesture_sequence: list) -> str:
        """
        Ubah list gesture menjadi kalimat yang natural.
        gesture_sequence: list of str (gesture labels)
        """
        if not gesture_sequence:
            return ''

        words = []
        for g in gesture_sequence:
            tts_text = self.tts_map.get(g, g)
            words.append(tts_text)

        # Kapitalisasi awal, tambah titik di akhir jika belum ada
        sentence = ' '.join(words).strip()
        if sentence and sentence[0].isalpha():
            sentence = sentence[0].upper() + sentence[1:]
        if sentence and sentence[-1] not in '.!?':
            sentence += '.'

        return sentence

    def build_tts_output(self, predictions: list) -> dict:
        """
        Pipeline lengkap: filter → dedup → kalimat.

        Returns:
            {
              'sentence'  : str   kalimat untuk TTS
              'gestures'  : list  gesture labels yang valid
              'confidence': float rata-rata confidence
            }
        """
        clean = self.filter_and_deduplicate(predictions)
        if not clean:
            return {'sentence': '', 'gestures': [], 'confidence': 0.0}

        gesture_labels = [p['gesture'] for p in clean]
        avg_conf = float(np.mean([p['confidence'] for p in clean]))
        sentence = self.to_sentence(gesture_labels)

        return {
            'sentence'  : sentence,
            'gestures'  : gesture_labels,
            'confidence': avg_conf,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PART 7 — SLIDING WINDOW INFERENCE ENGINE (realtime, TFLite-ready)
# ─────────────────────────────────────────────────────────────────────────────

class RealtimeInferenceEngine:
    """
    Engine inferensi realtime dengan sliding window.

    Cara kerja:
    1. Frame sensor dari ESP32 masuk satu-satu via push_frame()
    2. Setiap INFERENCE_STRIDE frame, jalankan prediksi
    3. Stability check: gesture harus konsisten N kali berturut-turut
    4. Output gesture yang stabil ke callback (untuk TTS + UI)

    Dirancang agar mudah diport ke Android (TFLite):
    - State disimpan di buffer sederhana (deque)
    - Tidak ada dependency external saat inference
    - TFLite interpreter bisa menggantikan Keras model.predict()
    """

    def __init__(
        self,
        model,                           # Keras model atau TFLite interpreter
        preprocessor: GloveSensorPreprocessor,
        segmenter: AdaptiveGestureSegmenter,
        gesture_labels: list,
        window_size: int = CATEGORY_WINDOW['ALL'],
        stride: int = INFERENCE_STRIDE,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        stability_n: int = STABILITY_WINDOW,
        on_gesture_callback=None,        # dipanggil saat gesture stabil terdeteksi
        use_tflite: bool = False,
    ):
        self.model            = model
        self.preprocessor     = preprocessor
        self.segmenter        = segmenter
        self.labels           = gesture_labels
        self.window_size      = window_size
        self.stride           = stride
        self.conf_threshold   = confidence_threshold
        self.stability_n      = stability_n
        self.on_gesture       = on_gesture_callback
        self.use_tflite       = use_tflite

        # Buffer frame mentah (rolling, ukuran = window_size + sedikit extra)
        self._buffer = collections.deque(maxlen=window_size * 2)
        self._frame_counter = 0

        # Stability tracker
        self._recent_predictions = collections.deque(maxlen=stability_n)
        self._last_output: str = ''
        self._last_output_time: int = 0

    def push_frame(self, frame: np.ndarray, timestamp_ms: int = 0):
        """
        Masukkan satu frame sensor (22 nilai float).
        Dipanggil setiap kali data UDP diterima dari ESP32.

        Args:
            frame        : np.array (22,)
            timestamp_ms : waktu dalam ms (opsional, untuk grammar dedup)
        """
        self._buffer.append(frame)
        self._frame_counter += 1

        # Jalankan inferensi setiap STRIDE frame
        if self._frame_counter % self.stride != 0:
            return None

        # Butuh minimal window_size frame
        if len(self._buffer) < self.window_size:
            return None

        # Cek apakah gesture sedang aktif (tidak output saat tangan diam)
        recent = np.array(list(self._buffer))[-15:]  # 150ms terakhir
        if not self.segmenter.is_gesture_active(recent):
            self._recent_predictions.clear()
            return None

        # Ambil window terbaru
        window_raw = np.array(list(self._buffer))[-self.window_size:]

        # Preprocess
        tensor = self.preprocessor.transform_sequence(window_raw, self.window_size)
        tensor_batch = tensor[np.newaxis, ...]   # (1, window, 66)

        # Inferensi
        if self.use_tflite:
            result = self._tflite_infer(tensor_batch)
        else:
            result = self.model.predict(tensor_batch, verbose=0)[0]

        gesture_idx = int(np.argmax(result))
        confidence  = float(result[gesture_idx])

        if confidence < self.conf_threshold:
            self._recent_predictions.clear()
            return None

        predicted_label = self.labels[gesture_idx]
        top3 = [(self.labels[i], float(result[i]))
                for i in np.argsort(result)[-3:][::-1]]

        # Stability check
        self._recent_predictions.append(predicted_label)

        stable = (
            len(self._recent_predictions) == self.stability_n and
            len(set(self._recent_predictions)) == 1
        )

        output = {
            'gesture'   : predicted_label,
            'confidence': confidence,
            'top3'      : top3,
            'stable'    : stable,
            'timestamp_ms': timestamp_ms,
        }

        if stable:
            # Hindari output gesture yang sama terlalu cepat (< 800ms)
            if (predicted_label != self._last_output or
                    timestamp_ms - self._last_output_time > 800):
                self._last_output = predicted_label
                self._last_output_time = timestamp_ms
                if self.on_gesture:
                    self.on_gesture(output)
                self._recent_predictions.clear()

        return output

    def _tflite_infer(self, tensor_batch: np.ndarray) -> np.ndarray:
        """
        Inferensi menggunakan TFLite interpreter.
        Dipakai saat use_tflite=True (Android via pybind atau langsung di Kotlin).
        """
        interp = self.model   # di sini model adalah tf.lite.Interpreter
        inp_idx = interp.get_input_details()[0]['index']
        out_idx = interp.get_output_details()[0]['index']
        interp.set_tensor(inp_idx, tensor_batch)
        interp.invoke()
        return interp.get_tensor(out_idx)[0]

    def reset(self):
        """Reset buffer — panggil saat sesi percakapan baru dimulai."""
        self._buffer.clear()
        self._frame_counter = 0
        self._recent_predictions.clear()
        self._last_output = ''
        self._last_output_time = 0


# ─────────────────────────────────────────────────────────────────────────────
# PART 8 — PRODUCTION INFERENCE ENGINE (file-based, untuk testing offline)
# ─────────────────────────────────────────────────────────────────────────────

class ProductionInferenceEngine:
    """
    Wrapper untuk testing offline: load model dari file, jalankan pada CSV data.
    Interface publik sama dengan versi lama agar notebook tidak perlu banyak ubah.
    """

    def __init__(
        self,
        model_path: str,
        metadata_path: str,
        gesture_list_path: str,
        use_tflite: bool = False,
    ):
        # Load gesture list
        self.gestures = self._load_gesture_list(gesture_list_path)
        self.num_gestures = len(self.gestures)

        # Load preprocessor
        with open(metadata_path) as f:
            meta = json.load(f)
        self.metadata = meta
        self.preprocessor = GloveSensorPreprocessor.from_dict(meta['scaler'])
        self.window_size = meta.get('window_size', CATEGORY_WINDOW['ALL'])

        # Load model
        self.use_tflite = use_tflite
        if use_tflite:
            self.interpreter = tf.lite.Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()
            self.model = self.interpreter
        else:
            self.model = keras.models.load_model(
                model_path,
                custom_objects={'AttentionLayer': AttentionLayer}
            )

        # Komponen pendukung
        self.segmenter = AdaptiveGestureSegmenter()
        self.grammar   = GrammarPostprocessor()

    def _load_gesture_list(self, path: str) -> list:
        gestures = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(',', 1)
                    if len(parts) == 2:
                        gestures.append(parts[1].strip())
        return gestures

    def infer_single_gesture(self, sensor_data: np.ndarray) -> dict:
        """
        Prediksi satu gesture dari satu sequence data.
        sensor_data: (T, 22) numpy array
        """
        tensor = self.preprocessor.transform_sequence(
            sensor_data, self.window_size
        )
        tensor_batch = tensor[np.newaxis, ...]  # (1, W, 66)

        if self.use_tflite:
            probs = self._tflite_infer(tensor_batch)
        else:
            probs = self.model.predict(tensor_batch, verbose=0)[0]

        idx  = int(np.argmax(probs))
        conf = float(probs[idx])
        top5 = [(self.gestures[i], float(probs[i]))
                for i in np.argsort(probs)[-5:][::-1]]

        return {
            'gesture'    : self.gestures[idx],
            'gesture_idx': idx,
            'confidence' : conf,
            'top5'       : top5,
            'all_probs'  : probs,
        }

    def infer_stream(self, sensor_stream: np.ndarray, calibrate_first_n: int = 50) -> dict:
        """
        Inferensi pada continuous sensor stream menggunakan sliding window.
        sensor_stream: (T, 22) numpy array (keseluruhan rekaman)
        calibrate_first_n: jumlah frame awal untuk kalibrasi segmenter
        """
        # Kalibrasi segmenter dengan frame awal (anggap tangan diam di awal)
        if calibrate_first_n > 0 and len(sensor_stream) > calibrate_first_n:
            self.segmenter.calibrate(sensor_stream[:calibrate_first_n])

        # Collect outputs
        outputs = []
        buffer = []

        for t, frame in enumerate(sensor_stream):
            buffer.append(frame)

            if len(buffer) < self.window_size:
                continue

            if t % INFERENCE_STRIDE != 0:
                continue

            window = np.array(buffer[-self.window_size:])
            recent = window[-15:]
            if not self.segmenter.is_gesture_active(recent):
                continue

            tensor = self.preprocessor.transform_sequence(window, self.window_size)
            tensor_batch = tensor[np.newaxis, ...]

            if self.use_tflite:
                probs = self._tflite_infer(tensor_batch)
            else:
                probs = self.model.predict(tensor_batch, verbose=0)[0]

            idx  = int(np.argmax(probs))
            conf = float(probs[idx])

            if conf >= CONFIDENCE_THRESHOLD:
                outputs.append({
                    'gesture'     : self.gestures[idx],
                    'confidence'  : conf,
                    'timestamp_ms': t * (1000 // SAMPLING_RATE),
                })

        result = self.grammar.build_tts_output(outputs)
        result['raw_outputs'] = outputs
        return result

    def _tflite_infer(self, tensor_batch: np.ndarray) -> np.ndarray:
        inp_idx = self.interpreter.get_input_details()[0]['index']
        out_idx = self.interpreter.get_output_details()[0]['index']
        self.interpreter.set_tensor(inp_idx, tensor_batch.astype(np.float32))
        self.interpreter.invoke()
        return self.interpreter.get_tensor(out_idx)[0]


# ─────────────────────────────────────────────────────────────────────────────
# PART 9 — BACKWARD COMPATIBILITY ALIASES
#          (agar notebook lama yang import nama kelas lama tetap jalan)
# ─────────────────────────────────────────────────────────────────────────────

# Kelas lama yang di-import oleh notebook — di-alias ke implementasi baru
class Seq2SeqGestureModel:
    """
    Alias backward-compatible.
    Notebook import Seq2SeqGestureModel — diarahkan ke BiLSTM+Attention.
    Seq2Seq asli TIDAK dipakai untuk realtime karena overhead decoder.
    """
    def __init__(self, num_gestures, max_sequence_length=20, **kwargs):
        self.num_gestures = num_gestures
        self._model = build_bilstm_attention_model(
            num_gestures=num_gestures,
            window_size=CATEGORY_WINDOW['ALL'],
            num_features=NUM_TOTAL_FEATURES,
        )

    def compile(self, learning_rate=0.001):
        self._model.compile(
            optimizer=keras.optimizers.Adam(learning_rate, clipnorm=1.0),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )

    def get_model(self):
        return self._model


class TransformerGestureModel:
    """
    Alias backward-compatible → TCN (bug residual Transformer sudah diperbaiki
    di TCN, dipakai sebagai model alternatif).
    """
    def __init__(self, num_gestures, max_sequence_length=20, **kwargs):
        self.num_gestures = num_gestures
        self._model = build_tcn_model(
            num_gestures=num_gestures,
            window_size=CATEGORY_WINDOW['ALL'],
            num_features=NUM_TOTAL_FEATURES,
        )

    def compile(self, learning_rate=0.001):
        self._model.compile(
            optimizer=keras.optimizers.Adam(learning_rate, clipnorm=1.0),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )

    def get_model(self):
        return self._model


# Nama lama lainnya
RealTimeGestureSegmenter = AdaptiveGestureSegmenter
AdvancedDataPreprocessor = GloveSensorPreprocessor


# ─────────────────────────────────────────────────────────────────────────────
print("""
╔══════════════════════════════════════════════════════════════════╗
║  GloveSpeak — Advanced Gesture Recognition v2.0                 ║
╠══════════════════════════════════════════════════════════════════╣
║  Model    : BiLSTM+Attention (utama) · TCN (alternatif)         ║
║  Features : 66 (raw + delta + accel)  · Window: 80 frame/800ms  ║
║  Realtime : Sliding window · Stride 15 · Latency ~150ms         ║
║  Fixes    : residual bug · shape mismatch · adaptive threshold   ║
║             post-padding · dead delta code · confidence gate     ║
╚══════════════════════════════════════════════════════════════════╝
""")
