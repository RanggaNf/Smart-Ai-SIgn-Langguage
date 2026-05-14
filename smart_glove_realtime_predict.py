"""
Smart Glove — Realtime Prediction via UDP  (Keras BiLSTM Edition)
==================================================================
Menerima data sensor dari ESP32 lewat UDP (port 5000),
lalu menjalankan model best_gesture_model.keras setiap sliding window.

Format paket UDP dari ESP32:
  DATA|F:<f1>,<f2>,<f3>,<f4>,<f5>|A:<ax>,<ay>,<az>|G:<gx>,<gy>,<gz>|
       F:<f1>,<f2>,<f3>,<f4>,<f5>|A:<ax>,<ay>,<az>|G:<gx>,<gy>,<gz>|BAT:<batL>,<batR>

Cara pakai:
  1. Pastikan best_gesture_model.keras + model_metadata.json ada.
  2. Set IP PC ini di firmware ESP32 Master.
  3. python smart_glove_realtime_predict.py
"""

# ═══════════════════════════════════════════════════════════════
#  KONFIGURASI — EDIT SESUAI SETUP KAMU
# ═══════════════════════════════════════════════════════════════
UDP_PORT            = 5000          # harus sama dengan ESP32
WINDOW_STEP         = 10            # prediksi setiap N frame baru
CONFIDENCE_SHOW_MIN = 0.30          # gesture di bawah ini tidak ditampilkan
STABILITY_FRAMES    = 3             # gesture harus konsisten N prediksi

MODEL_PATH    = r"C:\FOLDERKU\SmartGlove\best_gesture_model.keras"
METADATA_PATH = r"C:\FOLDERKU\SmartGlove\model_metadata.json"
# ═══════════════════════════════════════════════════════════════

import os, sys, json, socket, threading, time, collections
from datetime import datetime

import numpy as np
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ── TF quiet logs ────────────────────────────────────────────────────────────
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import tensorflow as tf
from tensorflow import keras

# ── Import preprocessing dari modul project ──────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from advanced_gesture_recognition import (
    GloveSensorPreprocessor,
    AttentionLayer,
    CATEGORY_WINDOW,
    CONFIDENCE_THRESHOLD,
    NUM_TOTAL_FEATURES,
)

WINDOW_SIZE = CATEGORY_WINDOW["ALL"]   # 80 frame


# ─────────────────────────────────────────────────────────────────────────────
#  Parsing paket UDP
# ─────────────────────────────────────────────────────────────────────────────

def parse_udp_packet(line: str):
    """
    Parse format: DATA|F:f1,..,f5|A:ax,ay,az|G:gx,gy,gz|F:...|A:...|G:...|BAT:bL,bR
    Return np.array (22,) atau None jika invalid.
    Urutan: flex_L(5) + accel_L(3) + gyro_L(3) + flex_R(5) + accel_R(3) + gyro_R(3)
    """
    try:
        parts = line.strip().split('|')
        if len(parts) < 8:
            return None
        if parts[0] != 'DATA':
            return None
        if not (parts[1].startswith('F:') and parts[2].startswith('A:') and
                parts[3].startswith('G:') and parts[4].startswith('F:') and
                parts[5].startswith('A:') and parts[6].startswith('G:') and
                parts[7].startswith('BAT:')):
            return None

        flex_L  = [float(x) for x in parts[1][2:].split(',')]
        accel_L = [float(x) for x in parts[2][2:].split(',')]
        gyro_L  = [float(x) for x in parts[3][2:].split(',')]
        flex_R  = [float(x) for x in parts[4][2:].split(',')]
        accel_R = [float(x) for x in parts[5][2:].split(',')]
        gyro_R  = [float(x) for x in parts[6][2:].split(',')]

        if (len(flex_L) != 5 or len(accel_L) != 3 or len(gyro_L) != 3 or
                len(flex_R) != 5 or len(accel_R) != 3 or len(gyro_R) != 3):
            return None

        frame = flex_L + accel_L + gyro_L + flex_R + accel_R + gyro_R  # 22 nilai
        return np.array(frame, dtype=np.float32)

    except (ValueError, IndexError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Load model & metadata
# ─────────────────────────────────────────────────────────────────────────────

def load_model_and_meta(model_path, meta_path):
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    gestures = meta.get('gesture_labels', [])
    scaler_data = meta.get('scaler', {})
    preprocessor = GloveSensorPreprocessor(
        scaler_mean  = np.array(scaler_data['mean'],  dtype=np.float32),
        scaler_scale = np.array(scaler_data['scale'], dtype=np.float32),
    )

    model = keras.models.load_model(
        model_path,
        custom_objects={'AttentionLayer': AttentionLayer}
    )
    return model, preprocessor, gestures, meta


# ─────────────────────────────────────────────────────────────────────────────
#  GUI App
# ─────────────────────────────────────────────────────────────────────────────

class SmartGloveApp:
    # ── Warna tema ────────────────────────────────────────────────────────────
    C_BG       = "#0D1117"
    C_PANEL    = "#161B22"
    C_CARD     = "#1F2937"
    C_BLUE     = "#1565C0"
    C_GREEN    = "#27AE60"
    C_ORANGE   = "#F39C12"
    C_RED      = "#E74C3C"
    C_ACCENT   = "#3498DB"
    C_TEXT     = "#E6EDF3"
    C_MUTED    = "#8B949E"
    C_BORDER   = "#30363D"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("⬡ Smart Glove — Realtime BISINDO (Keras)")
        self.root.configure(bg=self.C_BG)
        self.root.geometry("1280x800")
        try:
            self.root.state('zoomed')
        except Exception:
            pass

        # ── State ─────────────────────────────────────────────────────────────
        self.model        = None
        self.preprocessor = None
        self.gestures     = []
        self.meta         = {}
        self.conf_thr     = CONFIDENCE_THRESHOLD

        self.udp_socket   = None
        self.is_listening = False
        self.last_rx_ts   = 0.0

        # rolling frame buffer (deque(maxlen=WINDOW_SIZE) — raw 22D frames)
        self.frame_buf    = collections.deque(maxlen=WINDOW_SIZE)
        self.frames_new   = 0       # frame sejak prediksi terakhir

        # ── Motion Detection ──────────────────────────────────────────────────
        self.motion_threshold    = 0.05      # std deviation threshold untuk deteksi gerakan
        self.motion_active       = False     # apakah sedang ada gerakan
        self.motion_start_time   = None      # waktu mulai gerakan terdeteksi
        self.motion_window_min   = 1.0       # min timing setelah gerakan untuk prediksi (detik)
        self.motion_window_max   = 3.0       # max timing setelah gerakan untuk prediksi (detik)
        self.last_motion_time    = 0.0       # waktu gerakan terakhir terdeteksi

        # stability check
        self.recent_preds = collections.deque(maxlen=STABILITY_FRAMES)
        self.last_stable  = ""

        # stats
        self.pkt_total    = 0
        self.pkt_fps_cnt  = 0
        self.pkt_fps_ts   = time.time()
        self.pred_total   = 0
        self.pred_history = collections.deque(maxlen=15)

        # ── UI ────────────────────────────────────────────────────────────────
        self._build_ui()
        self.root.after(400, self._boot_load_model)

    # ─────────────────────────────────────────────────────────────────────────
    #  UI Builder
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._style_ttk()

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=self.C_BLUE, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="⬡  Smart Glove — Realtime BISINDO  ⬡",
                 font=("Segoe UI", 15, "bold"), fg="white", bg=self.C_BLUE
                 ).pack(side="left", padx=20, pady=12)

        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
        self.lbl_ip = tk.Label(hdr, text=f"PC IP: {ip}  |  UDP Port: {UDP_PORT}",
                               font=("Segoe UI", 10), fg="#90CAF9", bg=self.C_BLUE)
        self.lbl_ip.pack(side="right", padx=20)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = tk.Frame(self.root, bg="#1C2128", height=46)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        self.btn_udp = tk.Button(toolbar, text="▶  START UDP",
                                 command=self._toggle_udp,
                                 bg=self.C_GREEN, fg="white",
                                 font=("Segoe UI", 10, "bold"),
                                 relief="flat", padx=18, pady=5, cursor="hand2")
        self.btn_udp.pack(side="left", padx=12, pady=8)

        self.lbl_status = tk.Label(toolbar, text="● OFFLINE",
                                   fg=self.C_RED, font=("Segoe UI", 11, "bold"),
                                   bg="#1C2128")
        self.lbl_status.pack(side="left", padx=8)

        self.lbl_fps = tk.Label(toolbar, text="FPS: —",
                                font=("Segoe UI", 10), fg=self.C_MUTED, bg="#1C2128")
        self.lbl_fps.pack(side="left", padx=20)

        self.lbl_model = tk.Label(toolbar, text="Model: Loading…",
                                  font=("Segoe UI", 10, "bold"), fg=self.C_ORANGE,
                                  bg="#1C2128")
        self.lbl_model.pack(side="right", padx=20)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=self.C_BG)
        body.pack(fill="both", expand=True)

        # LEFT column (420px)
        left = tk.Frame(body, bg=self.C_PANEL, width=440)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self._build_left(left)

        # RIGHT column
        right = tk.Frame(body, bg=self.C_BG)
        right.pack(side="right", fill="both", expand=True)
        self._build_right(right)

        # Periodic tick
        self.root.after(250, self._tick)

    def _style_ttk(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("green.Horizontal.TProgressbar",
                    troughcolor=self.C_CARD, background=self.C_GREEN, thickness=8)
        s.configure("blue.Horizontal.TProgressbar",
                    troughcolor=self.C_CARD, background=self.C_ACCENT, thickness=10)
        s.configure("conf.Horizontal.TProgressbar",
                    troughcolor=self.C_CARD, background=self.C_ACCENT, thickness=18)

    def _build_left(self, parent):
        # ── Big prediction card ────────────────────────────────────────────
        card = tk.Frame(parent, bg=self.C_CARD, pady=18)
        card.pack(fill="x", padx=14, pady=(14, 6))

        tk.Label(card, text="GESTURE TERDETEKSI",
                 font=("Segoe UI", 9, "bold"), fg=self.C_MUTED,
                 bg=self.C_CARD).pack()

        self.lbl_pred = tk.Label(card, text="—",
                                 font=("Segoe UI", 80, "bold"),
                                 fg=self.C_ACCENT, bg=self.C_CARD,
                                 wraplength=400, justify="center")
        self.lbl_pred.pack(pady=6)

        self.lbl_conf = tk.Label(card, text="Menunggu data…",
                                 font=("Segoe UI", 13), fg=self.C_TEXT,
                                 bg=self.C_CARD)
        self.lbl_conf.pack()

        # Confidence bar
        self.conf_bar = ttk.Progressbar(card, length=380, maximum=100,
                                        style="conf.Horizontal.TProgressbar")
        self.conf_bar.pack(pady=10, padx=20)

        # Stability indicator
        self.lbl_stable = tk.Label(card, text="🟡 Menunggu…",
                                   font=("Segoe UI", 10), fg=self.C_ORANGE,
                                   bg=self.C_CARD)
        self.lbl_stable.pack(pady=(0, 6))

        # Motion detection indicator
        self.lbl_motion = tk.Label(card, text="⚪ Siap (Deteksi Gerakan)",
                                   font=("Segoe UI", 9), fg=self.C_MUTED,
                                   bg=self.C_CARD)
        self.lbl_motion.pack(pady=(0, 8))

        # ── Buffer bar ─────────────────────────────────────────────────────
        buf_frame = tk.Frame(parent, bg=self.C_PANEL)
        buf_frame.pack(fill="x", padx=14, pady=4)
        tk.Label(buf_frame, text="Buffer Frame",
                 font=("Segoe UI", 9), fg=self.C_MUTED,
                 bg=self.C_PANEL).pack(anchor="w")
        self.buf_bar = ttk.Progressbar(buf_frame, length=400, maximum=100,
                                       style="blue.Horizontal.TProgressbar")
        self.buf_bar.pack(fill="x")
        self.lbl_buf = tk.Label(buf_frame, text="0 / 80 frames",
                                font=("Segoe UI", 9), fg=self.C_MUTED,
                                bg=self.C_PANEL)
        self.lbl_buf.pack(anchor="e")

        # ── Top-5 predictions ─────────────────────────────────────────────
        top5_card = tk.LabelFrame(parent, text=" Top-5 Gesture ",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=self.C_PANEL, fg=self.C_TEXT,
                                  padx=10, pady=8)
        top5_card.pack(fill="x", padx=14, pady=6)

        self.top5_labels = []
        self.top5_bars   = []
        for i in range(5):
            row = tk.Frame(top5_card, bg=self.C_PANEL)
            row.pack(fill="x", pady=2)
            lbl_name = tk.Label(row, text=f"—", width=22,
                                font=("Consolas", 10, "bold"),
                                fg=self.C_TEXT, bg=self.C_PANEL, anchor="w")
            lbl_name.pack(side="left")
            bar = ttk.Progressbar(row, length=160, maximum=100,
                                  style="green.Horizontal.TProgressbar")
            bar.pack(side="left", padx=4)
            lbl_pct = tk.Label(row, text=" 0%", width=6,
                               font=("Consolas", 10), fg=self.C_MUTED,
                               bg=self.C_PANEL)
            lbl_pct.pack(side="left")
            self.top5_labels.append((lbl_name, lbl_pct))
            self.top5_bars.append(bar)

        # ── Stats ─────────────────────────────────────────────────────────
        stats = tk.Frame(parent, bg=self.C_PANEL)
        stats.pack(fill="x", padx=14, pady=4)
        self.lbl_stats = tk.Label(stats,
                                  text="Prediksi: 0  |  Paket: 0",
                                  font=("Segoe UI", 10), fg=self.C_MUTED,
                                  bg=self.C_PANEL)
        self.lbl_stats.pack(anchor="w")

    def _build_right(self, parent):
        # ── History ───────────────────────────────────────────────────────
        hist_card = tk.LabelFrame(parent, text=" Riwayat Gesture (Stabil) ",
                                  font=("Segoe UI", 10, "bold"),
                                  bg=self.C_BG, fg=self.C_TEXT,
                                  padx=10, pady=8)
        hist_card.pack(fill="x", padx=14, pady=(12, 6))

        self.lbl_history = tk.Label(hist_card,
                                    text="(menunggu prediksi stabil…)",
                                    font=("Consolas", 11), fg=self.C_MUTED,
                                    bg=self.C_BG, justify="left", anchor="w")
        self.lbl_history.pack(fill="x")

        # ── Log ───────────────────────────────────────────────────────────
        log_card = tk.LabelFrame(parent, text=" Log ",
                                 font=("Segoe UI", 9, "bold"),
                                 bg=self.C_BG, fg=self.C_TEXT,
                                 padx=6, pady=6)
        log_card.pack(fill="both", expand=True, padx=14, pady=6)

        self.log_box = scrolledtext.ScrolledText(log_card,
                                                 font=("Consolas", 9),
                                                 bg="#0D1117", fg=self.C_TEXT,
                                                 relief="flat",
                                                 insertbackground=self.C_TEXT)
        self.log_box.pack(fill="both", expand=True)

    # ─────────────────────────────────────────────────────────────────────────
    #  Model Loading
    # ─────────────────────────────────────────────────────────────────────────
    def _boot_load_model(self):
        self.log("⏳ Memuat model Keras…")
        t = threading.Thread(target=self._load_model_thread, daemon=True)
        t.start()

    def _load_model_thread(self):
        try:
            model, preprocessor, gestures, meta = load_model_and_meta(
                MODEL_PATH, METADATA_PATH)
            self.model        = model
            self.preprocessor = preprocessor
            self.gestures     = gestures
            self.meta         = meta
            self.conf_thr     = float(meta.get('confidence_threshold', CONFIDENCE_THRESHOLD))

            self.root.after(0, self._on_model_loaded)
        except Exception as e:
            self.root.after(0, lambda: self._on_model_error(str(e)))

    def _on_model_loaded(self):
        n = len(self.gestures)
        self.lbl_model.config(
            text=f"Model: ✓  ({n} gesture)",
            fg=self.C_GREEN)
        self.log(f"✓ Model dimuat: {n} gesture, window={WINDOW_SIZE}, conf_thr={self.conf_thr:.2f}")
        self.log(f"  Input shape: {self.model.input_shape}")
        # Auto-start UDP
        self.root.after(500, self._toggle_udp)

    def _on_model_error(self, msg):
        self.lbl_model.config(text="Model: ERROR", fg=self.C_RED)
        self.log(f"✗ Gagal muat model: {msg}")
        messagebox.showerror("Model Error",
                             f"Tidak bisa memuat model:\n{msg}\n\n"
                             f"Pastikan file ada:\n{MODEL_PATH}\n{METADATA_PATH}")

    # ─────────────────────────────────────────────────────────────────────────
    #  UDP Server
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_udp(self):
        if self.is_listening:
            self.is_listening = False
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except Exception:
                    pass
                self.udp_socket = None
            self.lbl_status.config(text="● OFFLINE", fg=self.C_RED)
            self.btn_udp.config(text="▶  START UDP", bg=self.C_GREEN)
            self.log("UDP server dihentikan.")
        else:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('0.0.0.0', UDP_PORT))
                sock.settimeout(1.0)
                self.udp_socket   = sock
                self.is_listening = True
                self.lbl_status.config(text="● MENUNGGU ESP32…", fg=self.C_ORANGE)
                self.btn_udp.config(text="■  STOP UDP", bg=self.C_RED)
                self.log(f"✓ UDP server aktif — port {UDP_PORT}  (menunggu ESP32…)")
                threading.Thread(target=self._rx_loop, daemon=True).start()
            except Exception as e:
                messagebox.showerror("UDP Error", str(e))
                self.log(f"✗ Gagal start UDP: {e}")

    def _rx_loop(self):
        """Thread penerima paket UDP."""
        first = True
        while self.is_listening:
            try:
                data, addr = self.udp_socket.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                break

            line = data.decode('utf-8', errors='ignore').strip()
            frame = parse_udp_packet(line)
            if frame is None:
                continue

            self.last_rx_ts = time.time()
            self.pkt_total += 1
            self.pkt_fps_cnt += 1

            if first:
                first = False
                ip = addr[0]
                self.root.after(0, lambda a=ip: (
                    self.lbl_status.config(text=f"● ONLINE  ({a})", fg=self.C_GREEN),
                    self.log(f"✓ Paket pertama dari ESP32  [{a}]")
                ))

            if self.model is None:
                continue

            self.frame_buf.append(frame)
            self.frames_new += 1

            # Update buffer bar setiap frame
            bl  = len(self.frame_buf)
            bpct = int(bl / WINDOW_SIZE * 100)
            self.root.after(0, lambda b=bl, p=bpct: (
                self.buf_bar.config(value=p),
                self.lbl_buf.config(text=f"{b} / {WINDOW_SIZE} frames")
            ))

            # ── Motion Detection ──────────────────────────────────────────────
            # Gunakan minimum 20 frame untuk deteksi gerakan yang stabil
            if len(self.frame_buf) >= 20:
                is_moving = self._detect_motion()
                
                if is_moving and not self.motion_active:
                    # Start motion detection
                    self.motion_active = True
                    self.motion_start_time = time.time()
                    self.root.after(0, lambda: self.log("🔴 Gerakan terdeteksi - Menunggu 1-3 detik untuk prediksi..."))
                
                elif not is_moving and self.motion_active:
                    # Motion stopped
                    self.motion_active = False
                    self.motion_start_time = None
                    self.root.after(0, lambda: self.log("⚪ Gerakan berhenti"))
                
                # Prediksi hanya jika: buffer penuh AND gerakan aktif AND sudah lewat timing window
                if (bl >= WINDOW_SIZE and self.motion_active and 
                    self.motion_start_time is not None):
                    elapsed = time.time() - self.motion_start_time
                    
                    # Prediksi jika sudah dalam window 1-3 detik
                    if elapsed >= self.motion_window_min:
                        self._predict()
                        
                        # Reset motion untuk deteksi gerakan berikutnya
                        if elapsed >= self.motion_window_max:
                            self.motion_active = False
                            self.motion_start_time = None

    def _detect_motion(self):
        """Deteksi gerakan dengan menghitung std deviation dari recent frames.
        
        Returns:
            bool: True jika ada gerakan, False jika statis
        """
        if len(self.frame_buf) < 20:
            return False
        
        # Ambil 20 frame terakhir
        recent = np.array(list(self.frame_buf)[-20:], dtype=np.float32)
        
        # Hitung standard deviation per channel
        # Recent shape: (20, 22)
        std_per_channel = np.std(recent, axis=0)
        
        # Hitung mean std deviation
        mean_std = np.mean(std_per_channel)
        
        # Ada gerakan jika mean_std > threshold
        is_motion = mean_std > self.motion_threshold
        
        return is_motion

    def _predict(self):
        """Jalankan inferensi model — dipanggil dari rx thread."""
        try:
            # Ambil window terbaru → (WINDOW_SIZE, 22)
            raw_window = np.array(list(self.frame_buf)[-WINDOW_SIZE:], dtype=np.float32)

            # Preprocess → (WINDOW_SIZE, 66)
            tensor = self.preprocessor.transform_sequence(raw_window, WINDOW_SIZE)

            # Predict → (136,) probs
            probs = self.model.predict(tensor[np.newaxis, ...], verbose=0)[0]

            pred_idx  = int(np.argmax(probs))
            pred_conf = float(probs[pred_idx])
            pred_name = self.gestures[pred_idx] if pred_idx < len(self.gestures) else "?"

            # Top-5
            top5_idx  = np.argsort(probs)[::-1][:5]
            top5      = [(self.gestures[i] if i < len(self.gestures) else "?",
                          float(probs[i])) for i in top5_idx]

            self.pred_total += 1

            # Stability check
            self.recent_preds.append(pred_name)
            stable = (len(self.recent_preds) == STABILITY_FRAMES and
                      len(set(self.recent_preds)) == 1)

            self.root.after(0, lambda n=pred_name, c=pred_conf,
                            t5=top5, st=stable: self._update_ui(n, c, t5, st))

        except Exception as e:
            self.root.after(0, lambda m=str(e): self.log(f"[PREDICT ERR] {m}"))

    # ─────────────────────────────────────────────────────────────────────────
    #  Update UI
    # ─────────────────────────────────────────────────────────────────────────
    def _update_ui(self, gesture, conf, top5, stable):
        # Warna berdasarkan confidence
        if conf >= 0.85:
            fg = self.C_GREEN
        elif conf >= self.conf_thr:
            fg = self.C_ORANGE
        else:
            fg = self.C_RED

        # Teks gesture — pendek: font besar, panjang: lebih kecil
        font_size = 80 if len(gesture) <= 4 else (50 if len(gesture) <= 10 else 30)
        self.lbl_pred.config(text=gesture, fg=fg,
                             font=("Segoe UI", font_size, "bold"))
        self.lbl_conf.config(text=f"Confidence: {conf*100:.1f}%", fg=fg)
        self.conf_bar.config(value=int(conf * 100))

        # Stability label
        if stable:
            self.lbl_stable.config(text=f"🟢 STABIL  »  {gesture}", fg=self.C_GREEN)
            # Tambahkan ke history hanya jika beda dgn entry terakhir
            if gesture != self.last_stable and conf >= self.conf_thr:
                self.last_stable = gesture
                ts = datetime.now().strftime("%H:%M:%S")
                self.pred_history.appendleft(
                    f"[{ts}] {gesture:<20} {conf*100:5.1f}%")
                self.lbl_history.config(
                    text="\n".join(list(self.pred_history)))
                self.log(f"⬡ STABIL → {gesture}  ({conf*100:.1f}%)")
        else:
            self.lbl_stable.config(text=f"🟡 {gesture}  ({conf*100:.1f}%)", fg=self.C_ORANGE)

        # Top-5 bars
        for i, (name, pct) in enumerate(top5):
            if i < len(self.top5_labels):
                lname, lpct = self.top5_labels[i]
                disp = name if name != gesture else f"▶ {name}"
                lname.config(text=disp[:22])
                lpct.config(text=f"{pct*100:4.0f}%")
                self.top5_bars[i].config(value=int(pct * 100))

        # Stats
        self.lbl_stats.config(
            text=f"Prediksi: {self.pred_total}  |  Paket: {self.pkt_total}")

    # ─────────────────────────────────────────────────────────────────────────
    #  Periodic tick (FPS + status)
    # ─────────────────────────────────────────────────────────────────────────
    def _tick(self):
        now = time.time()

        # Status & FPS
        if self.is_listening and self.last_rx_ts > 0:
            age = now - self.last_rx_ts
            if age > 3.0:
                self.lbl_status.config(text="● MENUNGGU DATA", fg=self.C_ORANGE)

        # Update motion detection indicator
        if self.motion_active and self.motion_start_time is not None:
            elapsed = now - self.motion_start_time
            if elapsed < self.motion_window_min:
                self.lbl_motion.config(
                    text=f"🔴 Gerakan! Tunggu {self.motion_window_min - elapsed:.1f}s...",
                    fg=self.C_ORANGE
                )
            else:
                self.lbl_motion.config(
                    text=f"🟢 Memprediksi ({elapsed:.1f}s)",
                    fg=self.C_GREEN
                )
        else:
            self.lbl_motion.config(
                text="⚪ Siap (Deteksi Gerakan)",
                fg=self.C_MUTED
            )

        elapsed = now - self.pkt_fps_ts
        if elapsed >= 2.0:
            fps = self.pkt_fps_cnt / elapsed
            self.lbl_fps.config(text=f"FPS: {fps:.1f}")
            self.pkt_fps_cnt = 0
            self.pkt_fps_ts  = now

        self.root.after(250, self._tick)

    # ─────────────────────────────────────────────────────────────────────────
    #  Log
    # ─────────────────────────────────────────────────────────────────────────
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_box.see(tk.END)

    # ─────────────────────────────────────────────────────────────────────────
    #  Cleanup
    # ─────────────────────────────────────────────────────────────────────────
    def on_close(self):
        self.is_listening = False
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass
        self.root.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = SmartGloveApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
