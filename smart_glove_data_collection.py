import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socket
import threading
import csv
import os
import json
from datetime import datetime
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class DataCollectionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Glove - Data Collection System (UDP)")
        # Set to full screen resolution
        self.root.geometry("1920x1080")
        self.root.resizable(True, True)
        # Maximize window to fill entire display
        self.root.state('zoomed')  # For Windows
        
        # UDP connection
        self.udp_socket = None
        self.udp_port = 5000  # Port harus sama dengan ESP32
        self.is_reading = False
        self.is_connected = False
        
        # Gesture list
        self.gesture_list = []
        self.current_gesture_index = 0
        self.current_repetition = 1
        self.total_repetitions = 15  # 15 repetitions per gesture
        
        # Recording state
        self.is_recording = False
        self.recorded_data = []
        self.recording_start_time = 0
        self.recording_timer = 3
        self.countdown_seconds = 0
        
        # Recording phases
        self.preparation_phase = False
        self.baseline_validation_phase = False
        self.gesture_execution_phase = False
        self.release_phase = False
        self.preparation_time = 3
        self.baseline_validation_time = 1
        self.gesture_execution_time = 0  # Adaptive, will auto-detect
        self.release_time = 1
        self.data_recording_time = 0  # Legacy, kept for compatibility
        
        # Track recording progress
        self.gesture_recording_count = {}
        self.total_recordings_completed = 0
        
        # Last data received timestamp (untuk monitor koneksi)
        self.last_data_time = 0
        
        # Category tracking
        self.selected_category = None
        self.category_buttons = {}
        self.gesture_list_buttons = {}
        
        # Calibration system
        self.calibration_data = {
            'flex_min_L': [4095, 4095, 4095, 4095, 4095],
            'flex_max_L': [0, 0, 0, 0, 0],
            'flex_min_R': [4095, 4095, 4095, 4095, 4095],
            'flex_max_R': [0, 0, 0, 0, 0]
        }
        self.is_calibrating = False
        self.calibration_dialog = None
        
        # Track gestures per category for calibration reminder
        self.category_gesture_count = {'ANGKA': 0, 'HURUF': 0, 'KATA': 0, 'FRASA': 0, 'KONTROL': 0}
        self.last_calibration_warning = None
        
        # Real-time sensor display
        self.last_flex_raw_L = [0, 0, 0, 0, 0]
        self.last_flex_raw_R = [0, 0, 0, 0, 0]
        
        # Sensor health check with persistence
        self.sensor_errors = []
        self.sensor_error_state = None  # Store last error state
        self.sensor_error_time = 0  # Timestamp of last error
        self.sensor_error_persist_duration = 2.0  # Tampilkan error selama 2 detik minimum
        self.sensor_error_logged = False  # Track jika error sudah di-log ke UI
        self.sensor_error_thresholds = {
            'percentage_tolerance': 0.20,  # 20% dari nilai MIN kalibrasi (lebih toleran untuk nilai kalibrasi yang berfluktuasi)
        }
        self.sensor_check_interval = 1.0  # Check setiap 1 detik (kurangi flashing)
        self.last_sensor_check = 0
        
        # Setup UI
        self.setup_ui()
        
        # Bind keyboard shortcuts
        self.root.bind('<space>', lambda e: self.on_space_pressed())
        self.root.bind('<Right>', lambda e: self.on_right_pressed())
        self.root.bind('<Left>', lambda e: self.on_left_pressed())
        
        # Load calibration data from JSON
        self.load_calibration()
        
        # Load gesture list
        self.load_gesture_list()
        
        # Load existing progress from saved CSV files and auto-start UDP
        self.load_progress_from_files()
        self.root.after(500, self.auto_start_udp)
        
    def auto_start_udp(self):
        """Automatically start UDP server on app startup"""
        if not self.is_connected:
            self.toggle_udp_connection()
        
    def load_gesture_list(self):
        """Load gesture list from file"""
        try:
            with open('gesture_list_15reps.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(',', maxsplit=1)
                        if len(parts) == 2:
                            gesture_type, label = parts
                            self.gesture_list.append({
                                'type': gesture_type.strip(),
                                'label': label.strip()
                            })
            
            # Initialize gesture recording count
            for i in range(len(self.gesture_list)):
                self.gesture_recording_count[i] = 0
            
            def log_startup():
                self.log(f"Loaded {len(self.gesture_list)} gestures from file")
                self.log("=" * 60)
                self.log("INSTRUKSI PENGGUNAAN (UDP MODE) - OPSI 1 ADAPTIVE:")
                self.log("1. UDP Server akan auto-start, tunggu status 'ONLINE'")
                self.log("2. Pastikan ESP32 Master sudah terkoneksi ke WiFi")
                self.log("3. Klik START untuk mulai recording")
                self.log("4. FASE: Persiapkan (3s) → Check (1s) → GO! → Gesture (auto-stop) → Release (1s)")
                self.log("5. Setelah recording selesai, klik NEXT untuk simpan")
                self.log("6. Ulangi sampai semua gesture 3x terekam (akan di-augmentasi)")
                self.log("=" * 60)
                self.log(f"UDP Port: {self.udp_port}")
                self.log(f"Pastikan IP PC ini sudah diset di ESP32 Master")
                self.log(f"Durasi pergestur: ~7.5s (3s prep + 1s check + 2-3s gesture + 1s release)")
            
            self.root.after(100, log_startup)
        except FileNotFoundError:
            messagebox.showerror("Error", "File 'gesture_list_complete.txt' not found!")
            self.root.quit()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load gesture list: {e}")
            self.root.quit()
    
    def load_calibration(self):
        """Load calibration data from JSON file"""
        calibration_file = 'calibration_values.json'
        try:
            if os.path.exists(calibration_file):
                with open(calibration_file, 'r', encoding='utf-8') as f:
                    self.calibration_data = json.load(f)
                print(f"Calibration data loaded from {calibration_file}")
            else:
                print(f"No calibration file found, using defaults")
        except Exception as e:
            print(f"Error loading calibration: {e}")
    
    def save_calibration(self):
        """Save calibration data to JSON file"""
        calibration_file = 'calibration_values.json'
        try:
            print(f"[SAVE] Writing to {calibration_file}")
            print(f"[SAVE] Data to save: {self.calibration_data}")
            with open(calibration_file, 'w', encoding='utf-8') as f:
                json.dump(self.calibration_data, f, indent=2)
            
            # Verify write
            with open(calibration_file, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            print(f"[SAVE] Verified - File content after write: {saved_data}")
            
            self.log(f"Calibration data saved to {calibration_file}")
            print(f"Calibration saved: {self.calibration_data}")
        except Exception as e:
            print(f"Error saving calibration: {e}")
    
    def normalize_flex_value(self, raw_value, sensor_index, hand):
        """
        Convert raw ADC value (0-4095) to normalized value (0-1)
        sensor_index: 0-4 for flex sensors
        hand: 'L' or 'R'
        """
        min_key = f'flex_min_{hand}'
        max_key = f'flex_max_{hand}'
        
        flex_min = self.calibration_data.get(min_key, [4095]*5)[sensor_index]
        flex_max = self.calibration_data.get(max_key, [0]*5)[sensor_index]
        
        # If calibration not done yet (min=4095, max=0), use simple linear mapping
        if flex_min >= flex_max:
            # Passthrough: divide raw 0-4095 to 0-1.0
            normalized = raw_value / 4095.0
            return max(0.0, min(1.0, normalized))  # Clamp 0-1
        
        # Normal calibration formula
        normalized = (raw_value - flex_min) / (flex_max - flex_min)
        return max(0.0, min(1.0, normalized))  # Clamp 0-1
    
    def load_progress_from_files(self):
        """Scan existing CSV files and load progress"""
        base_path = r"C:\FOLDERKU\SmartGlove\datashet"
        
        # Initialize all counts to 0
        for i in range(len(self.gesture_list)):
            self.gesture_recording_count[i] = 0
        
        if not os.path.exists(base_path):
            return 0
        
        # Scan all category directories
        for gesture_idx, gesture in enumerate(self.gesture_list):
            category = gesture['type'].lower()
            label = gesture['label'].replace(' ', '_')
            category_path = os.path.join(base_path, category)
            
            if not os.path.exists(category_path):
                continue
            
            # Count how many repetitions exist for this gesture
            rep_count = 0
            for file in os.listdir(category_path):
                if file.startswith(label + '_rep') and file.endswith('.csv'):
                    rep_count += 1
            
            self.gesture_recording_count[gesture_idx] = rep_count
            self.total_recordings_completed += rep_count
        
        # Find first incomplete gesture
        for i in range(len(self.gesture_list)):
            if self.gesture_recording_count[i] < 5:
                return i
        
        return len(self.gesture_list)  # All done
    
    def check_sensor_health(self):
        """
        Monitor sensor health dengan PERSISTENCE - error ditampilkan minimal 2 detik.
        Tidak flashing, lebih stabil.
        
        Returns: (status_ok, error_messages)
        """
        import time
        
        current_time = time.time()
        
        # Jika error masih dalam periode persist, tampilkan error lama
        if self.sensor_error_state and (current_time - self.sensor_error_time) < self.sensor_error_persist_duration:
            return False, self.sensor_error_state
        
        # Don't check too frequently
        if current_time - self.last_sensor_check < self.sensor_check_interval:
            # Return last known state
            if self.sensor_error_state and (current_time - self.sensor_error_time) < self.sensor_error_persist_duration:
                return False, self.sensor_error_state
            return True, []
        
        self.last_sensor_check = current_time
        errors = []
        
        if not self.calibration_data:
            self.sensor_error_state = None
            return True, []
        
        # Check left hand sensors
        flex_min_L = self.calibration_data.get('flex_min_L', [4095]*5)
        
        for i, raw_val in enumerate(self.last_flex_raw_L):
            min_val = flex_min_L[i]
            
            # Skip if not calibrated
            if min_val == 4095 or min_val == 0:
                continue
            
            # Hitung tolerance 20% dari nilai MIN (lebih fleksibel untuk kalibrasi yang berfluktuasi)
            tolerance = min_val * self.sensor_error_thresholds['percentage_tolerance']
            
            # Tentukan range OK: [min - tolerance, min + tolerance]
            min_ok = min_val - tolerance
            max_ok = min_val + tolerance
            
            # Jika di luar range OK, maka ERROR
            if raw_val < min_ok or raw_val > max_ok:
                gap = abs(raw_val - min_val)
                if raw_val > max_ok:
                    reason = f"TIDAK RILIS (jari tidak relaks, ADC={int(raw_val)} >> MIN={int(min_val)})"
                else:
                    reason = f"UNSTABLE (sensor tidak stabil, ADC={int(raw_val)} << MIN={int(min_val)})"
                errors.append(f"⚠️ Sensor Kiri-{i+1}: {reason} [gap={int(gap)} > {int(tolerance)}=20%]")
        
        # Check right hand sensors
        flex_min_R = self.calibration_data.get('flex_min_R', [4095]*5)
        
        for i, raw_val in enumerate(self.last_flex_raw_R):
            min_val = flex_min_R[i]
            
            # Skip if not calibrated
            if min_val == 4095 or min_val == 0:
                continue
            
            # Hitung tolerance 20%
            tolerance = min_val * self.sensor_error_thresholds['percentage_tolerance']
            
            # Tentukan range OK
            min_ok = min_val - tolerance
            max_ok = min_val + tolerance
            
            # Jika di luar range OK, maka ERROR
            if raw_val < min_ok or raw_val > max_ok:
                gap = abs(raw_val - min_val)
                if raw_val > max_ok:
                    reason = f"TIDAK RILIS (jari tidak relaks, ADC={int(raw_val)} >> MIN={int(min_val)})"
                else:
                    reason = f"UNSTABLE (sensor tidak stabil, ADC={int(raw_val)} << MIN={int(min_val)})"
                errors.append(f"⚠️ Sensor Kanan-{i+1}: {reason} [gap={int(gap)} > {int(tolerance)}=20%]")
        
        # Update error state with persistence
        if errors:
            self.sensor_error_state = errors
            self.sensor_error_time = current_time
            return False, errors
        else:
            # Clear error only after persist duration
            if self.sensor_error_state and (current_time - self.sensor_error_time) >= self.sensor_error_persist_duration:
                self.sensor_error_state = None
            return True, []
        
        self.sensor_errors = errors
        return len(errors) == 0, errors
    
    def update_sensor_status_display(self):
        """Update sensor status indicator di UI - TIDAK FLASHING.
        Error hanya ditampilkan saat tidak recording (standby/prep phase).
        Saat recording, sensor check di-skip karena normal gesture berubah nilai ADC."""
        
        # Skip sensor check saat recording - gesture natural berubah data
        if self.is_recording:
            # Tampilkan status normal saat recording
            try:
                self.sensor_status_label.config(text="◉ RECORDING...", fg="#f39c12")
                self.sensor_error_label.config(text="")
            except:
                pass
            return
        
        # Check sensor hanya saat tidak recording (standby/idle)
        status_ok, errors = self.check_sensor_health()
        
        try:
            if status_ok:
                # HIJAU - Sensor OK
                self.sensor_status_label.config(text="✓ SENSOR OK", fg="#27ae60")
                self.sensor_error_label.config(text="")
                self.sensor_error_logged = False  # Reset log flag
            else:
                # MERAH - Sensor ERROR (hanya saat tidak recording)
                self.sensor_status_label.config(text="✗ SENSOR ERROR", fg="#e74c3c")
                error_text = "\n".join(errors[:2])  # Show first 2 errors
                if len(errors) > 2:
                    error_text += f"\n+{len(errors)-2} lainnya"
                self.sensor_error_label.config(text=error_text, fg="#e74c3c")
                
                # Log error hanya SEKALI per error sequence
                if not self.sensor_error_logged and errors:
                    self.log(errors[0])  # Log ke UI saja
                    print(f"[SENSOR CHECK] {errors[0]}")  # Console untuk debug
                    self.sensor_error_logged = True
        except:
            pass  # Jika widget sudah destroy, skip
    
    def setup_ui(self):
        """Setup UI components"""
        
        # Configure style
        self.root.configure(bg="#2c3e50")
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main container - full screen, no scrollbar
        main_container = tk.Frame(self.root, bg="#2c3e50")
        main_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        # ===== HEADER =====
        header_frame = tk.Frame(main_container, bg="#1976D2", height=60)
        header_frame.pack(fill="x", pady=0)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="Smart Glove Data Collection System (UDP)", 
                fg="white", font=("Arial", 18, "bold"), bg="#1976D2").pack(side="left", padx=20, pady=15)
        
        # ===== TOP ROW: Connection + Status =====
        top_row = tk.Frame(main_container, bg="#34495e")
        top_row.pack(fill="x", pady=0)
        
        # Connection Frame (Left)
        conn_frame = tk.Frame(top_row, bg="#34495e", padx=15, pady=8)
        conn_frame.pack(side="left", fill="both", expand=True)
        
        # Display local IP
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "Unknown"
        
        tk.Label(conn_frame, text=f"PC IP: {local_ip}", 
                font=("Arial", 10, "bold"), bg="#34495e", fg="#ecf0f1").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        
        tk.Label(conn_frame, text=f"UDP Port: {self.udp_port}", 
                font=("Arial", 10), bg="#34495e", fg="#ecf0f1").grid(row=0, column=1, sticky="w", padx=5, pady=3)
        
        self.btn_connect = tk.Button(conn_frame, text="START UDP SERVER", 
                                     command=self.toggle_udp_connection,
                                     bg="#27ae60", fg="white", font=("Arial", 10, "bold"),
                                     relief="flat", padx=20, pady=8, cursor="hand2")
        self.btn_connect.grid(row=0, column=2, padx=10, pady=3)
        
        self.status_label = tk.Label(conn_frame, text="OFFLINE", fg="#e74c3c", 
                                     font=("Arial", 12, "bold"), bg="#34495e")
        self.status_label.grid(row=0, column=3, padx=15, pady=3)
        
        # Progress Frame (Right)
        progress_frame = tk.Frame(top_row, bg="#34495e", padx=15, pady=8)
        progress_frame.pack(side="right", fill="both", expand=True)
        
        self.progress_label = tk.Label(progress_frame, 
                                       text="Gesture: 0/0  •  Repetition: 0/5",
                                       font=("Arial", 12, "bold"), bg="#34495e", fg="#ecf0f1")
        self.progress_label.pack(pady=3)
        
        self.progress_bar = ttk.Progressbar(progress_frame, length=500, mode='determinate')
        self.progress_bar.pack(fill="x", padx=10, pady=5)
        
        # ===== MAIN CONTENT AREA - SPLIT INTO 3 COLUMNS =====
        content_area = tk.Frame(main_container, bg="#2c3e50")
        content_area.pack(fill="both", expand=True, padx=0, pady=0)
        
        # LEFT COLUMN: Gesture Display + Category + List (30%)
        left_column = tk.Frame(content_area, bg="#34495e", width=400)
        left_column.pack(side="left", fill="both", expand=False, padx=0, pady=0)
        left_column.pack_propagate(False)
        
        # Gesture Display
        gesture_frame = tk.Frame(left_column, bg="#2c3e50", pady=15)
        gesture_frame.pack(fill="x", padx=10, pady=5)
        
        self.gesture_display = tk.Label(gesture_frame, text="0", 
                                       font=("Arial", 48, "bold"), fg="#3498db", bg="#2c3e50",
                                       wraplength=350, justify="center")
        self.gesture_display.pack(pady=5, padx=5)
        
        self.desc_display = tk.Label(gesture_frame, text="Gesture ini akan direkam 5x",
                                    font=("Arial", 10), bg="#2c3e50", fg="#ecf0f1")
        self.desc_display.pack(pady=3)
        
        self.instruction_label = tk.Label(gesture_frame,
                                         text="Posisi Awal:\nLetakkan tangan di MEJA\nTangan TERBUKA",
                                         font=("Arial", 9, "bold"), bg="#e67e22", fg="white",
                                         relief="flat", padx=10, pady=10, justify="center")
        self.instruction_label.pack(fill="x", pady=5, padx=10)
        
        # Category buttons
        category_frame = tk.Frame(left_column, bg="#2c3e50", pady=10)
        category_frame.pack(fill="x", padx=10)
        
        tk.Label(category_frame, text="KATEGORI", font=("Arial", 10, "bold"), 
                bg="#2c3e50", fg="#ecf0f1").pack(pady=5)
        
        cat_btn_frame = tk.Frame(category_frame, bg="#2c3e50")
        cat_btn_frame.pack(fill="x")
        
        categories = ['ANGKA', 'HURUF', 'KATA', 'FRASA', 'KONTROL']
        for cat in categories:
            btn = tk.Button(cat_btn_frame, text=cat, font=("Arial", 9, "bold"),
                          bg="#27ae60" if cat == 'ANGKA' else ("#e74c3c" if cat == 'KONTROL' else "#3498db"), fg="white",
                          padx=8, pady=5, relief="flat", cursor="hand2",
                          command=lambda c=cat: self.select_category(c))
            btn.pack(fill="x", pady=2)
            self.category_buttons[cat] = btn
        
        self.selected_category = 'ANGKA'
        
        # Gesture list (scrollable)
        list_frame = tk.LabelFrame(left_column, text="DAFTAR GESTURE", 
                                  font=("Arial", 10, "bold"), bg="#2c3e50", fg="#ecf0f1",
                                  padx=5, pady=5)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Create custom style for scrollbar
        scrollbar_style = ttk.Style()
        scrollbar_style.configure("Vertical.TScrollbar", 
                                 background="#34495e",
                                 troughcolor="#2c3e50",
                                 bordercolor="#2c3e50",
                                 lightcolor="#34495e",
                                 darkcolor="#34495e",
                                 arrowcolor="#ecf0f1")
        
        list_canvas = tk.Canvas(list_frame, bg="#2c3e50", highlightthickness=0, width=350)
        self.list_canvas = list_canvas  # Store reference for scroll reset
        list_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=list_canvas.yview, style="Vertical.TScrollbar")
        self.gesture_list_frame = tk.Frame(list_canvas, bg="#2c3e50")
        
        self.gesture_list_frame.bind(
            "<Configure>",
            lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        )
        
        list_canvas.create_window((0, 0), window=self.gesture_list_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scrollbar.set)
        list_canvas.bind("<MouseWheel>", lambda e: list_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        
        list_canvas.pack(side="left", fill="both", expand=True)
        list_scrollbar.pack(side="right", fill="y", padx=(3, 0))
        
        # CENTER COLUMN: Chart Display (45%)
        center_column = tk.Frame(content_area, bg="#34495e")
        center_column.pack(side="left", fill="both", expand=True, padx=0, pady=0)
        
        chart_header = tk.Frame(center_column, bg="#2c3e50", height=40)
        chart_header.pack(fill="x")
        chart_header.pack_propagate(False)
        
        tk.Label(chart_header, text="DATA SENSOR", 
                font=("Arial", 12, "bold"), bg="#2c3e50", fg="#ecf0f1").pack(pady=8)
        
        # Chart container - ukuran lebih kecil dan proporsional
        self.chart_container = tk.Frame(center_column, bg="#2c3e50")
        self.chart_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Placeholder message
        self.chart_placeholder = tk.Label(self.chart_container, 
                                         text="Grafik akan muncul di sini setelah recording selesai",
                                         font=("Arial", 11, "italic"), 
                                         bg="#34495e", fg="#95a5a6",
                                         pady=50)
        self.chart_placeholder.pack(fill="both", expand=True)
        
        self.chart_frame = None
        self.chart_canvas = None
        
        # Chart buttons - ALWAYS VISIBLE at bottom
        chart_btn_frame = tk.Frame(center_column, bg="#2c3e50", height=60)
        chart_btn_frame.pack(fill="x", side="bottom")
        chart_btn_frame.pack_propagate(False)
        
        btn_container = tk.Frame(chart_btn_frame, bg="#2c3e50")
        btn_container.pack(expand=True)
        
        tk.Button(btn_container, text="✓ NEXT / SAVE DATA [RIGHT →]", command=self.approve_chart,
                 bg="#27ae60", fg="white", font=("Arial", 10, "bold"),
                 padx=15, pady=8, relief="flat", cursor="hand2").pack(side="left", padx=10)
        
        tk.Button(btn_container, text="✗ RETRY RECORDING [LEFT ←]", command=self.close_chart,
                 bg="#e67e22", fg="white", font=("Arial", 10, "bold"),
                 padx=15, pady=8, relief="flat", cursor="hand2").pack(side="left", padx=10)
        
        # RIGHT COLUMN: Status + Controls + Log (25%)
        right_column = tk.Frame(content_area, bg="#34495e", width=350)
        right_column.pack(side="right", fill="both", expand=False, padx=0, pady=0)
        right_column.pack_propagate(False)
        
        # Recording Status
        status_frame = tk.LabelFrame(right_column, text="STATUS RECORDING",
                                    font=("Arial", 10, "bold"), bg="#2c3e50", fg="#ecf0f1",
                                    padx=10, pady=10)
        status_frame.pack(fill="x", padx=10, pady=10)
        
        self.recording_indicator = tk.Label(status_frame, text="Ready", 
                                           font=("Arial", 12, "bold"), fg="#95a5a6", bg="#2c3e50")
        self.recording_indicator.pack(pady=5)
        
        self.timer_label = tk.Label(status_frame, text="--", 
                                   font=("Arial", 36, "bold"), fg="#3498db", bg="#2c3e50")
        self.timer_label.pack(pady=10)
        
        self.data_count_label = tk.Label(status_frame, text="Samples: 0", 
                                        font=("Arial", 10), bg="#2c3e50", fg="#ecf0f1")
        self.data_count_label.pack(pady=3)
        
        self.counter_label = tk.Label(status_frame, text="Recording: 0/5", 
                                     font=("Arial", 10, "bold"), bg="#2c3e50", fg="#e67e22")
        self.counter_label.pack(pady=3)
        
        self.overall_progress_label = tk.Label(status_frame, 
                                              text="Overall: 0%",
                                              font=("Arial", 10, "bold"), bg="#2c3e50", fg="#3498db")
        self.overall_progress_label.pack(pady=5)
        
        # Sensor Display (Real-time flex values)
        sensor_frame = tk.LabelFrame(right_column, text="SENSOR FLEX (ADC)",
                                    font=("Arial", 9, "bold"), bg="#2c3e50", fg="#ecf0f1",
                                    padx=8, pady=8)
        sensor_frame.pack(fill="x", padx=10, pady=5)
        
        self.flex_L_label = tk.Label(sensor_frame, text="Tangan Kiri:  [0.00, 0.00, 0.00, 0.00, 0.00]",
                                    font=("Consolas", 8), bg="#2c3e50", fg="#3498db", justify="left")
        self.flex_L_label.pack(anchor="w", padx=5, pady=2)
        
        self.flex_R_label = tk.Label(sensor_frame, text="Tangan Kanan: [0.00, 0.00, 0.00, 0.00, 0.00]",
                                    font=("Consolas", 8), bg="#2c3e50", fg="#e74c3c", justify="left")
        self.flex_R_label.pack(anchor="w", padx=5, pady=2)
        
        # Sensor Health Status
        self.sensor_status_frame = tk.Frame(sensor_frame, bg="#2c3e50")
        self.sensor_status_frame.pack(anchor="w", fill="x", padx=5, pady=5)
        
        self.sensor_status_label = tk.Label(self.sensor_status_frame, 
                                           text="✓ SENSOR OK", 
                                           font=("Arial", 9, "bold"), 
                                           bg="#2c3e50", fg="#27ae60", 
                                           justify="left",
                                           wraplength=280)
        self.sensor_status_label.pack(anchor="w", pady=2)
        
        self.sensor_error_label = tk.Label(self.sensor_status_frame,
                                          text="",
                                          font=("Arial", 8),
                                          bg="#2c3e50", fg="#e74c3c",
                                          justify="left",
                                          wraplength=280)
        self.sensor_error_label.pack(anchor="w", pady=2)
        
        # Category counter
        self.category_count_label = tk.Label(sensor_frame, text="Gesture dlm kategori: 0",
                                            font=("Arial", 8, "bold"), bg="#2c3e50", fg="#f39c12", justify="left")
        self.category_count_label.pack(anchor="w", padx=5, pady=3)
        
        # Control Buttons
        control_frame = tk.LabelFrame(right_column, text="KONTROL",
                                     font=("Arial", 9, "bold"), bg="#2c3e50", fg="#ecf0f1",
                                     padx=8, pady=8)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        # Button row 1 (START, RETRY)
        btn_row1 = tk.Frame(control_frame, bg="#2c3e50")
        btn_row1.pack(fill="x", pady=2)
        
        self.btn_start = tk.Button(btn_row1, text="START\n[SPACE]", 
                                   command=self.start_recording,
                                   bg="#27ae60", fg="white", 
                                   font=("Arial", 8, "bold"),
                                   padx=5, pady=6,
                                   relief="flat",
                                   cursor="hand2",
                                   state="disabled")
        self.btn_start.pack(side="left", fill="both", expand=True, padx=2)
        
        self.btn_retry = tk.Button(btn_row1, text="RETRY\n[LEFT ←]", 
                                   command=self.retry_recording,
                                   bg="#e67e22", fg="white",
                                   font=("Arial", 8, "bold"),
                                   padx=5, pady=6,
                                   relief="flat",
                                   cursor="hand2",
                                   state="disabled")
        self.btn_retry.pack(side="left", fill="both", expand=True, padx=2)
        
        # Button row 2 (NEXT, CALIBRATE)
        btn_row2 = tk.Frame(control_frame, bg="#2c3e50")
        btn_row2.pack(fill="x", pady=2)
        
        self.btn_next = tk.Button(btn_row2, text="NEXT\n[RIGHT →]", 
                                  command=self.next_repetition,
                                  bg="#3498db", fg="white",
                                  font=("Arial", 8, "bold"),
                                  padx=5, pady=6,
                                  relief="flat",
                                  cursor="hand2",
                                  state="disabled")
        self.btn_next.pack(side="left", fill="both", expand=True, padx=2)
        
        # Calibration button
        self.btn_calibrate = tk.Button(btn_row2, text="⚙️ KALIBRASI", 
                                      command=self.show_calibration_dialog,
                                      bg="#9b59b6", fg="white",
                                      font=("Arial", 8, "bold"),
                                      padx=5, pady=6,
                                      relief="flat",
                                      cursor="hand2",
                                      state="normal")
        self.btn_calibrate.pack(side="left", fill="both", expand=True, padx=2)
        
        # Log section
        log_frame = tk.LabelFrame(right_column, text="LOG",
                                 font=("Arial", 9, "bold"), bg="#2c3e50", fg="#ecf0f1",
                                 padx=5, pady=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, 
                                                  font=("Consolas", 9),
                                                  bg="#ecf0f1", fg="#1c1c1c",
                                                  relief="solid", borderwidth=1)
        self.log_text.pack(fill="both", expand=True)
        
        self.root.after(200, self.update_gesture_display)
    
    def toggle_udp_connection(self):
        """Start or stop UDP server"""
        if self.is_connected:
            # Stop UDP server
            self.is_reading = False
            self.is_connected = False
            if self.udp_socket:
                self.udp_socket.close()
                self.udp_socket = None
            
            self.status_label.config(text="OFFLINE", fg="#e74c3c")
            self.btn_connect.config(text="START UDP SERVER", bg="#27ae60")
            self.log("UDP server stopped")
            self.update_start_button()
        else:
            # Start UDP server
            try:
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_socket.bind(('0.0.0.0', self.udp_port))
                self.udp_socket.settimeout(1.0)
                
                self.is_connected = True
                self.status_label.config(text="WAITING DATA", fg="#f39c12")
                self.btn_connect.config(text="STOP UDP SERVER", bg="#e74c3c")
                self.log(f"UDP server started on port {self.udp_port}")
                self.log("Waiting for data from ESP32...")
                
                # Start monitor thread
                monitor_thread = threading.Thread(target=self.monitor_connection, daemon=True)
                monitor_thread.start()
                
                # Start UDP receive thread (always listening)
                receive_thread = threading.Thread(target=self.receive_udp_always, daemon=True)
                receive_thread.start()
                
                self.update_start_button()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start UDP server: {e}")
                self.log(f"UDP server error: {e}")
    
    def monitor_connection(self):
        """Monitor UDP connection and update status"""
        while self.is_connected:
            current_time = time.time()
            
            # Check if data received in last 2 seconds
            if self.last_data_time > 0 and (current_time - self.last_data_time) < 2:
                if self.status_label.cget('text') != "ONLINE":
                    self.root.after(0, lambda: self.status_label.config(text="ONLINE", fg="#27ae60"))
            else:
                if self.last_data_time > 0 and self.status_label.cget('text') == "ONLINE":
                    self.root.after(0, lambda: self.status_label.config(text="WAITING DATA", fg="#f39c12"))
            
            time.sleep(0.5)
    
    def select_category(self, category):
        """Select a category and update gesture list"""
        # Update button colors
        for cat, btn in self.category_buttons.items():
            btn.config(bg="#27ae60" if cat == category else "#3498db")
        
        self.selected_category = category
        self.update_gesture_list()
    
    def update_gesture_list(self):
        """Update the gesture list for selected category"""
        # Clear existing buttons
        for widget in self.gesture_list_frame.winfo_children():
            widget.destroy()
        
        self.gesture_list_buttons = {}
        
        # Reset scroll to top when category changes
        self.list_canvas.yview_moveto(0)
        
        # Count gestures in this category for numbering
        gesture_number = 1
        
        # Add buttons for each gesture in this category
        for gesture_idx, gesture in enumerate(self.gesture_list):
            if gesture['type'] != self.selected_category:
                continue
            
            count = self.gesture_recording_count.get(gesture_idx, 0)
            
            # Show status with checkmark for complete
            if count >= 3:
                status_text = "✓"
                bg_color = "#27ae60"  # Green
                fg_color = "white"
            else:
                status_text = f"{count}/3"
                bg_color = "#3498db"  # Blue
                fg_color = "white"
            
            btn_text = f"[{gesture_number:2d}] {status_text:4} {gesture['label']}"
            btn = tk.Button(
                self.gesture_list_frame,
                text=btn_text,
                font=("Arial", 9, "bold" if count >= 5 else "normal"),
                bg=bg_color, fg=fg_color,
                padx=8, pady=6, relief="flat", cursor="hand2",
                command=lambda idx=gesture_idx: self.start_recording_gesture(idx),
                anchor="w", justify="left"
            )
            btn.pack(fill="x", pady=1, padx=3)
            self.gesture_list_buttons[gesture_idx] = btn
            gesture_number += 1
    
    def start_recording_gesture(self, gesture_idx):
        """Select gesture (don't auto-start, user clicks START button)"""
        self.current_gesture_index = gesture_idx
        self.update_gesture_display()
        self.log(f"Selected: {self.gesture_list[gesture_idx]['label']} - Click START to begin recording")
    
    def receive_udp_always(self):
        """Background thread to continuously receive UDP data - update flex display REAL-TIME"""
        first_packet_logged = False
        while self.is_connected:
            try:
                if not self.udp_socket:
                    time.sleep(0.1)
                    continue
                
                try:
                    data, addr = self.udp_socket.recvfrom(1024)
                    line = data.decode('utf-8', errors='ignore').strip()
                    
                    # Update last data time even if not recording
                    if line.startswith("DATA|"):
                        self.last_data_time = time.time()
                        
                        # Log first packet to verify reception
                        if not first_packet_logged:
                            self.root.after(0, lambda: self.log("✓ Data dari ESP32 diterima via UDP!"))
                            first_packet_logged = True
                        
                        # ======== EXTRACT AND DISPLAY FLEX SENSORS REAL-TIME ========
                        try:
                            parts = line.split('|')
                            if len(parts) == 8:
                                # Extract raw ADC values (0-4095)
                                flex_L_raw = [float(x) for x in parts[1][2:].split(',')]
                                flex_R_raw = [float(x) for x in parts[4][2:].split(',')]
                                
                                # Store untuk reference lainnya
                                self.last_flex_raw_L = flex_L_raw
                                self.last_flex_raw_R = flex_R_raw
                                
                                # Format untuk display (4 digit, comma separated)
                                flex_L_str = ", ".join([f"{int(v):4d}" for v in flex_L_raw])
                                flex_R_str = ", ".join([f"{int(v):4d}" for v in flex_R_raw])
                                
                                # Update UI labels REAL-TIME
                                self.root.after(0, lambda lstr=flex_L_str, rstr=flex_R_str: (
                                    self.flex_L_label.config(text=f"Tangan Kiri:  [{lstr}]"),
                                    self.flex_R_label.config(text=f"Tangan Kanan: [{rstr}]"),
                                    self.update_sensor_status_display()
                                ))
                        except:
                            pass
                        
                        # If calibrating, extract and send to calibration dialog
                        if self.is_calibrating and self.calibration_dialog:
                            try:
                                parts = line.split('|')
                                if len(parts) == 8:
                                    flex_L_raw = [float(x) for x in parts[1][2:].split(',')]
                                    flex_R_raw = [float(x) for x in parts[4][2:].split(',')]
                                    if hasattr(self.calibration_dialog, 'calibration_update'):
                                        self.calibration_dialog.calibration_update(flex_L_raw, flex_R_raw)
                            except:
                                pass
                        
                        # If recording, parse and store the data
                        if self.is_recording:
                            parsed = self.parse_data_line(line)
                            if parsed:
                                timestamp = int((time.time() - self.recording_start_time) * 1000)
                                parsed['timestamp'] = timestamp
                                current_rep = self.gesture_recording_count.get(self.current_gesture_index, 0) + 1
                                parsed['repetition'] = current_rep
                                self.recorded_data.append(parsed)
                                self.root.after(0, lambda: self.data_count_label.config(
                                    text=f"Samples: {len(self.recorded_data)}"
                                ))
                
                except socket.timeout:
                    pass
                    
            except Exception as e:
                if self.is_connected:
                    self.log(f"[ERROR] UDP background receive error: {e}")
                break
            
            time.sleep(0.01)  # 10ms loop
    
    def update_start_button(self):
        """Enable start button if connected and not recording"""
        if (self.is_connected and not self.is_recording and 
            self.current_gesture_index < len(self.gesture_list)):
            self.btn_start.config(state="normal")
            self.btn_retry.config(state="normal")
            self.btn_next.config(state="normal")
        else:
            self.btn_start.config(state="disabled")
            if not self.is_recording:
                self.btn_retry.config(state="disabled")
                self.btn_next.config(state="disabled")
    
    def get_category_color(self, category):
        """Get color for category"""
        colors = {
            'ANGKA': ('#27ae60', 'ANGKA'),
            'HURUF': ('#3498db', 'HURUF'),
            'KATA': ('#9b59b6', 'KATA'),
            'FRASA': ('#e67e22', 'FRASA')
        }
        return colors.get(category, ('#95a5a6', '?'))
    
    def get_recording_duration(self, category):
        """Get adaptive recording duration (will auto-detect completion)"""
        # Max duration - will auto-stop when gesture stabilizes
        durations = {
            'ANGKA': 3,   # Max 3s, typically stops at 1.5-2s when stable
            'HURUF': 3,   # Max 3s, typically stops at 1.5-2s when stable
            'KATA': 3.5,  # Max 3.5s, typically stops at 2-2.5s when stable
            'FRASA': 4    # Max 4s, typically stops at 2.5-3s when stable
        }
        return durations.get(category, 3)
    
    def update_gesture_display(self):
        """Update gesture display"""
        if self.current_gesture_index < len(self.gesture_list):
            gesture = self.gesture_list[self.current_gesture_index]
            self.gesture_display.config(text=gesture['label'], fg="#3498db")
            
            category = gesture['type']
            self.selected_category = category
            
            # Update category buttons
            for cat, btn in self.category_buttons.items():
                btn.config(bg="#27ae60" if cat == category else "#3498db")
            
            current_count = self.gesture_recording_count.get(self.current_gesture_index, 0)
            phase = (current_count // 5) if current_count > 0 else 0
            total_phases = 3
            self.desc_display.config(
                text=f"Recording {current_count}/15 completed (Phase: {phase}/{total_phases})"
            )
            
            self.counter_label.config(text=f"Recording: {current_count}/15")
            
            phase = (current_count // 5) if current_count > 0 else 0
            total_phases = 3
            self.progress_label.config(
                text=f"Gesture: {self.current_gesture_index + 1}/{len(self.gesture_list)}  •  Phase: {phase}/{total_phases}  •  Reps: {current_count}/15"
            )
            
            # Update gesture list
            self.update_gesture_list()
            
            total_expected = len(self.gesture_list) * self.total_repetitions
            if total_expected > 0:
                progress_pct = int((self.total_recordings_completed / total_expected) * 100)
            else:
                progress_pct = 0
            self.overall_progress_label.config(text=f"Overall: {progress_pct}% ({self.total_recordings_completed}/{total_expected})")
        else:
            self.gesture_display.config(text="DONE!", fg="#27ae60")
            self.desc_display.config(text="All gestures completed! Ready for augmentation.")
            self.counter_label.config(text="Recording: 3/3")
            self.progress_label.config(text="All Gestures Completed!")
            total_expected = len(self.gesture_list) * self.total_repetitions
            self.overall_progress_label.config(text=f"Overall: 100% ({total_expected}/{total_expected})")
            messagebox.showinfo("Complete", "All gestures collected successfully (3x each)!\n\nSelanjutnya gunakan augmentation untuk generate variasi adicional.")
    
    def show_data_chart(self):
        """Display all sensors in one unified chart (Left & Right combined)"""
        if not self.recorded_data or len(self.recorded_data) == 0:
            return
        
        # Hide placeholder
        if self.chart_placeholder:
            self.chart_placeholder.pack_forget()
        
        # Clear previous chart if exists
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None
        
        if self.chart_frame:
            self.chart_frame.destroy()
            self.chart_frame = None
        
        # Create new chart frame inside container - centered, not expanding
        self.chart_frame = tk.Frame(self.chart_container, bg="#2c3e50")
        self.chart_frame.pack(anchor="center", pady=5)
        
        # Extract sensor data
        flex_L_list = [[] for _ in range(5)]
        accel_L_list = [[] for _ in range(3)]
        gyro_L_list = [[] for _ in range(3)]
        flex_R_list = [[] for _ in range(5)]
        accel_R_list = [[] for _ in range(3)]
        gyro_R_list = [[] for _ in range(3)]
        
        for data in self.recorded_data:
            for i in range(5):
                flex_L_list[i].append(data['flex_L'][i])
                flex_R_list[i].append(data['flex_R'][i])
            for i in range(3):
                accel_L_list[i].append(data['accel_L'][i])
                accel_R_list[i].append(data['accel_R'][i])
                gyro_L_list[i].append(data['gyro_L'][i])
                gyro_R_list[i].append(data['gyro_R'][i])
        
        # Create figure - compact and square-shaped, fixed size
        fig = Figure(figsize=(5.5, 6.2), dpi=80, facecolor='#2c3e50')
        
        # Colors for Left (solid) and Right (dashed)
        flex_colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
        axis_colors = ['#e74c3c', '#2ecc71', '#3498db']
        axis_labels = ['X', 'Y', 'Z']
        
        # === SUBPLOT 1: FLEX SENSORS (All 10 sensors) ===
        ax1 = fig.add_subplot(3, 1, 1, facecolor='#34495e')
        # Left hand (solid lines)
        for i in range(5):
            ax1.plot(flex_L_list[i], color=flex_colors[i], linewidth=2.2, 
                    linestyle='-', label=f'L{i+1}', alpha=0.9)
        # Right hand (dashed lines)
        for i in range(5):
            ax1.plot(flex_R_list[i], color=flex_colors[i], linewidth=2.2, 
                    linestyle='--', label=f'R{i+1}', alpha=0.7)
        
        ax1.set_ylabel('FLEX', fontsize=10, fontweight='bold', color='white')
        ax1.set_title(f'SENSORS - {self.gesture_list[self.current_gesture_index]["label"]}', 
                     fontsize=12, fontweight='bold', color='#ecf0f1', pad=6)
        ax1.grid(True, alpha=0.2, color='white', linewidth=0.5)
        ax1.tick_params(colors='white', labelsize=7)
        for spine in ax1.spines.values():
            spine.set_color('white')
        ax1.set_ylim(-0.1, 1.1)
        ax1.legend(loc='upper right', ncol=10, fontsize=6, framealpha=0.3)
        
        # === SUBPLOT 2: ACCELEROMETER (All 6 axes) ===
        ax2 = fig.add_subplot(3, 1, 2, facecolor='#34495e')
        # Left hand (solid lines)
        for i in range(3):
            ax2.plot(accel_L_list[i], color=axis_colors[i], linewidth=2.2, 
                    linestyle='-', label=f'L-{axis_labels[i]}', alpha=0.9)
        # Right hand (dashed lines)
        for i in range(3):
            ax2.plot(accel_R_list[i], color=axis_colors[i], linewidth=2.2, 
                    linestyle='--', label=f'R-{axis_labels[i]}', alpha=0.7)
        
        ax2.set_ylabel('ACCEL', fontsize=10, fontweight='bold', color='white')
        ax2.grid(True, alpha=0.2, color='white', linewidth=0.5)
        ax2.tick_params(colors='white', labelsize=7)
        for spine in ax2.spines.values():
            spine.set_color('white')
        ax2.legend(loc='upper right', ncol=6, fontsize=6, framealpha=0.3)
        
        # === SUBPLOT 3: GYROSCOPE (All 6 axes) ===
        ax3 = fig.add_subplot(3, 1, 3, facecolor='#34495e')
        # Left hand (solid lines)
        for i in range(3):
            ax3.plot(gyro_L_list[i], color=axis_colors[i], linewidth=2.2, 
                    linestyle='-', label=f'L-{axis_labels[i]}', alpha=0.9)
        # Right hand (dashed lines)
        for i in range(3):
            ax3.plot(gyro_R_list[i], color=axis_colors[i], linewidth=2.2, 
                    linestyle='--', label=f'R-{axis_labels[i]}', alpha=0.7)
        
        ax3.set_ylabel('GYRO', fontsize=10, fontweight='bold', color='white')
        ax3.set_xlabel('Sample', fontsize=9, fontweight='bold', color='white')
        ax3.grid(True, alpha=0.2, color='white', linewidth=0.5)
        ax3.tick_params(colors='white', labelsize=7)
        for spine in ax3.spines.values():
            spine.set_color('white')
        ax3.legend(loc='upper right', ncol=6, fontsize=6, framealpha=0.3)
        
        fig.tight_layout(pad=1.2)
        
        # Embed in chart frame - fixed size, centered
        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack()
        
        self.log(f"✓ Chart ready - {len(self.recorded_data)} samples (22 sensors)")
        
        # Auto-approve after showing chart
        self.btn_next.config(state="normal")
    
    def approve_chart(self):
        """Approve chart - same as next"""
        self.next_repetition()
    
    def close_chart(self):
        """Retry recording - clear chart and data"""
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None
        if self.chart_frame:
            self.chart_frame.destroy()
            self.chart_frame = None
        
        # Show placeholder again
        if self.chart_placeholder:
            self.chart_placeholder.pack(fill="both", expand=True)
        
        self.recorded_data = []
        self.data_count_label.config(text="Samples: 0")
        self.log("Data discarded. Click START to retry.")
        self.start_recording()
    
    def start_recording(self):
        """Start OPSI 1 recording: Preparation → Validation → Gesture (adaptive) → Release"""
        # Check if connected first
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "UDP Server not started! Click START UDP SERVER first.")
            return
        
        if self.status_label.cget('text') != "ONLINE":
            messagebox.showwarning("No Connection", f"ESP32 not connected! Status: {self.status_label.cget('text')}\nCheck Master board WiFi connection.")
            return
        
        if self.current_gesture_index >= len(self.gesture_list):
            messagebox.showinfo("Info", "All gestures completed!")
            return
        
        self.is_recording = True
        self.preparation_phase = True
        self.baseline_validation_phase = False
        self.gesture_execution_phase = False
        self.release_phase = False
        self.recorded_data = []
        
        gesture = self.gesture_list[self.current_gesture_index]
        self.gesture_execution_time = self.get_recording_duration(gesture['type'])
        
        # Total timeline: 3s (prep) + 1s (baseline) + 0.5s (GO) + 2-3s (gesture) + 1s (release)
        
        self.btn_start.config(state="disabled")
        self.btn_retry.config(state="disabled")
        self.btn_next.config(state="disabled")
        
        self.recording_indicator.config(text="GET READY", fg="#f39c12")
        self.progress_bar['value'] = 0
        
        current_count = self.gesture_recording_count.get(self.current_gesture_index, 0)
        self.log(f"Mulai recording: {gesture['type']} - {gesture['label']} ({current_count + 1}/3)")
        self.log(f"Timeline: 3s Persiapkan → 1s Check → GO! → {self.gesture_execution_time}s Gesture (auto-stop) → 1s Release")
        
        timer_thread = threading.Thread(target=self.update_recording_timer, daemon=True)
        timer_thread.start()
    
    def stop_recording(self):
        """Stop recording"""
        self.is_recording = False
        self.is_reading = False
        
        self.btn_start.config(state="disabled")
        self.btn_retry.config(state="normal")
        self.btn_next.config(state="normal")  # Langsung enable NEXT
        
        self.recording_indicator.config(text="Ready", fg="#95a5a6")
        self.timer_label.config(text="--")
        self.progress_bar['value'] = 100
        
        duration = time.time() - self.recording_start_time
        self.log(f"Recorded: {duration:.1f}s ({len(self.recorded_data)} samples)")
        
        # Show data chart if data recorded
        if len(self.recorded_data) > 0:
            self.root.after(500, self.show_data_chart)
        else:
            messagebox.showwarning("No Data", "No data recorded! Check connection and try again.")
    
    def on_space_pressed(self):
        """Handle SPACE key"""
        if self.btn_start.cget('state') == 'normal':
            self.start_recording()
    
    def on_right_pressed(self):
        """Handle RIGHT arrow key"""
        if self.btn_next.cget('state') == 'normal':
            self.next_repetition()
    
    def on_left_pressed(self):
        """Handle LEFT arrow key"""
        if self.btn_retry.cget('state') == 'normal':
            self.retry_recording()
    
    def retry_recording(self):
        """Retry recording"""
        self.recorded_data = []
        self.data_count_label.config(text="Samples: 0")
        self.log("Retrying recording - data discarded")
        self.start_recording()
    
    def update_recording_timer(self):
        """Handle OPSI 1 recording phases with adaptive gesture detection"""
        total_start_time = time.time()
        baseline_values = None
        gesture_peak_values = None
        stable_counter = 0
        min_stable_time = 0.5  # Gesture must be stable for 0.5s to auto-stop
        min_gesture_time = 0.8  # Minimum gesture time before stability check
        
        while self.is_recording:
            total_elapsed = time.time() - total_start_time
            
            # ==================== PHASE 1: PREPARATION (3 sec) ====================
            if self.preparation_phase and total_elapsed < self.preparation_time:
                remaining = self.preparation_time - total_elapsed
                countdown_int = int(remaining) + 1 if remaining % 1 > 0.5 else int(remaining)
                if countdown_int <= 0:
                    countdown_int = 1
                
                display_text = f"GET READY\n{countdown_int}"
                self.root.after(0, lambda text=display_text: 
                              self.timer_label.config(text=text, font=("Arial", 48, "bold"), fg="#f39c12") if self.is_recording else None)
                
                progress = int((total_elapsed / self.preparation_time) * 100)
                self.root.after(0, lambda p=progress: self.progress_bar.__setitem__('value', p) if self.is_recording else None)
                
                time.sleep(0.1)
            
            # ==================== PHASE 2: BASELINE VALIDATION (1 sec) ====================
            elif self.preparation_phase and total_elapsed >= self.preparation_time and total_elapsed < (self.preparation_time + self.baseline_validation_time):
                baseline_elapsed = total_elapsed - self.preparation_time
                
                display_text = "CHECK\nBASELINE"
                self.root.after(0, lambda text=display_text: 
                              self.timer_label.config(text=text, font=("Arial", 36, "bold"), fg="#3498db") if self.is_recording else None)
                
                self.root.after(0, lambda: self.recording_indicator.config(text="VALIDASI BASELINE", fg="#3498db"))
                
                progress = int((baseline_elapsed / self.baseline_validation_time) * 100)
                self.root.after(0, lambda p=progress: self.progress_bar.__setitem__('value', p) if self.is_recording else None)
                
                time.sleep(0.1)
            
            # ==================== TRANSITION: "GO!" SIGNAL ====================
            elif self.preparation_phase and total_elapsed >= (self.preparation_time + self.baseline_validation_time):
                self.preparation_phase = False
                self.baseline_validation_phase = True
                self.gesture_execution_phase = True
                self.is_reading = True
                
                gesture = self.gesture_list[self.current_gesture_index]
                current_count = self.gesture_recording_count.get(self.current_gesture_index, 0)
                
                self.root.after(0, lambda: self.timer_label.config(text="GO!", font=("Arial", 72, "bold"), fg="#27ae60"))
                self.root.after(0, lambda: self.recording_indicator.config(text="BUAT GESTURE!", fg="#27ae60"))
                self.root.after(0, lambda: self.log(f"Gesture: {gesture['label']} ({current_count + 1}/3) - Mulai buat gesture sekarang!"))
                
                # Start reading data
                read_thread = threading.Thread(target=self.read_udp_data, daemon=True)
                read_thread.start()
                
                # Reset adaptive detection variables
                gesture_start_time = time.time()
            
            # ==================== PHASE 3: GESTURE EXECUTION (ADAPTIVE) ====================
            elif self.gesture_execution_phase:
                gesture_elapsed = time.time() - gesture_start_time
                max_gesture_time = self.gesture_execution_time
                
                # Show countdown
                remaining = max_gesture_time - gesture_elapsed
                display_text = f"{remaining:.1f}s"
                self.root.after(0, lambda text=display_text: 
                              self.timer_label.config(text=text, font=("Arial", 48, "bold"), fg="#e74c3c") if self.is_recording else None)
                
                progress = int((gesture_elapsed / max_gesture_time) * 100)
                self.root.after(0, lambda p=progress: self.progress_bar.__setitem__('value', p) if self.is_recording else None)
                
                # *** ADAPTIVE AUTO-STOP LOGIC ***
                # After minimum gesture time, check if gesture is stable
                if gesture_elapsed > min_gesture_time and len(self.recorded_data) > 10:
                    # Get last 10 flex samples (last ~0.3s at ~33Hz)
                    recent_flex_L = [d['flex_L'] for d in self.recorded_data[-10:]]
                    recent_flex_R = [d['flex_R'] for d in self.recorded_data[-10:]]
                    
                    # Calculate variance to detect stability
                    avg_variance = 0
                    for i in range(5):
                        flex_values_L = [row[i] for row in recent_flex_L]
                        flex_values_R = [row[i] for row in recent_flex_R]
                        variance_L = max(flex_values_L) - min(flex_values_L)
                        variance_R = max(flex_values_R) - min(flex_values_R)
                        avg_variance += (variance_L + variance_R) / 2
                    
                    avg_variance = avg_variance / 5
                    
                    # If stable (low variance), increment counter
                    if avg_variance < 0.05:  # Threshold for stability
                        stable_counter += 1
                    else:
                        stable_counter = 0  # Reset if motion detected
                    
                    # Auto-stop when stable for min_stable_time
                    if stable_counter >= int(min_stable_time * 10):  # ~0.5s at 10Hz check
                        self.root.after(0, lambda: self.log(f"✓ Gesture stable - stopping recording (variance: {avg_variance:.3f})"))
                        self.gesture_execution_phase = False
                        self.release_phase = True
                        gesture_start_time = time.time()  # Reset for release phase
                
                # Also stop if max time reached
                elif gesture_elapsed >= max_gesture_time:
                    self.root.after(0, lambda: self.log(f"✓ Max recording time reached - stopping"))
                    self.gesture_execution_phase = False
                    self.release_phase = True
                    gesture_start_time = time.time()
                
                time.sleep(0.05)
            
            # ==================== PHASE 4: RELEASE (1 sec) ====================
            elif self.release_phase and total_elapsed < (self.preparation_time + self.baseline_validation_time + self.gesture_execution_time + self.release_time):
                release_elapsed = total_elapsed - (self.preparation_time + self.baseline_validation_time + self.gesture_execution_time)
                
                self.root.after(0, lambda: self.recording_indicator.config(text="LEPAS GESTURE", fg="#f39c12"))
                
                display_text = f"RELEASE\n{self.release_time - int(release_elapsed)}"
                self.root.after(0, lambda text=display_text: 
                              self.timer_label.config(text=text, font=("Arial", 36, "bold"), fg="#f39c12") if self.is_recording else None)
                
                time.sleep(0.1)
            
            # ==================== PHASE 5: STABILIZATION & END ====================
            else:
                self.root.after(0, self.stop_recording)
                break
            
            time.sleep(0.05)
    
    def read_udp_data(self):
        """Read data from UDP socket"""
        log_count = 0
        receive_count = 0
        
        while self.is_reading and (self.is_recording or self.is_calibrating):
            try:
                if not self.udp_socket:
                    break
                
                try:
                    data, addr = self.udp_socket.recvfrom(1024)
                    receive_count += 1
                    
                    line = data.decode('utf-8', errors='ignore').strip()
                    
                    if not line.startswith("DATA|"):
                        continue
                    
                    self.last_data_time = time.time()
                    
                    # Parse data line - extract raw ADC values before normalization
                    parts = line.split('|')
                    if len(parts) != 8:
                        continue
                    
                    try:
                        # Extract raw ADC values (before normalization)
                        flex_L_raw = [float(x) for x in parts[1][2:].split(',')]
                        flex_R_raw = [float(x) for x in parts[4][2:].split(',')]
                    except:
                        continue
                    
                    # Store raw values for display
                    self.last_flex_raw_L = flex_L_raw
                    self.last_flex_raw_R = flex_R_raw
                    
                    # Update display with raw ADC values
                    flex_L_str = ", ".join([f"{v:.0f}" for v in flex_L_raw])
                    flex_R_str = ", ".join([f"{v:.0f}" for v in flex_R_raw])
                    self.root.after(0, lambda lstr=flex_L_str, rstr=flex_R_str: (
                        self.flex_L_label.config(text=f"Tangan Kiri:  [{lstr}]"),
                        self.flex_R_label.config(text=f"Tangan Kanan: [{rstr}]"),
                        self.update_sensor_status_display()
                    ))
                    
                    # Update category gesture counter display
                    if self.current_gesture_index < len(self.gesture_list):
                        current_gesture = self.gesture_list[self.current_gesture_index]
                        category = current_gesture['type'].upper()
                        count = self.category_gesture_count.get(category, 0)
                        self.root.after(0, lambda c=count: 
                            self.category_count_label.config(text=f"Gesture dlm kategori: {c}"))
                    
                    # Update calibration dialog if active
                    if self.is_calibrating and self.calibration_dialog and hasattr(self.calibration_dialog, 'calibration_update'):
                        self.calibration_dialog.calibration_update(flex_L_raw, flex_R_raw)
                    
                    # Parse full data only if recording (not just calibrating)
                    if self.is_recording:
                        parsed = self.parse_data_line(line)
                        if parsed is None:
                            continue
                        
                        if log_count == 0:
                            self.root.after(0, lambda: self.log(f"✓ Receiving data..."))
                            log_count += 1
                        
                        timestamp = int((time.time() - self.recording_start_time) * 1000)
                        parsed['timestamp'] = timestamp
                        current_rep = self.gesture_recording_count.get(self.current_gesture_index, 0) + 1
                        parsed['repetition'] = current_rep
                        
                        self.recorded_data.append(parsed)
                        
                        self.root.after(0, lambda: self.data_count_label.config(
                            text=f"Samples: {len(self.recorded_data)}"
                        ))
                
                except socket.timeout:
                    pass
                    
            except Exception as e:
                if self.is_reading:
                    self.log(f"[ERROR] UDP read error: {e}")
                break
    
    def parse_data_line(self, line):
        """Parse data line from ESP32 - convert ADC values to normalized (0-1)"""
        try:
            parts = line.split('|')
            if len(parts) != 8:
                return None
            if (parts[0] != "DATA" or
                not parts[1].startswith("F:") or
                not parts[2].startswith("A:") or
                not parts[3].startswith("G:") or
                not parts[4].startswith("F:") or
                not parts[5].startswith("A:") or
                not parts[6].startswith("G:") or
                not parts[7].startswith("BAT:")):
                return None

            # Parse raw ADC values
            flex_L_raw  = [float(x) for x in parts[1][2:].split(',')]
            accel_L = [float(x) for x in parts[2][2:].split(',')]
            gyro_L  = [float(x) for x in parts[3][2:].split(',')]
            flex_R_raw  = [float(x) for x in parts[4][2:].split(',')]
            accel_R = [float(x) for x in parts[5][2:].split(',')]
            gyro_R  = [float(x) for x in parts[6][2:].split(',')]
            bat_str = parts[7][4:]
            bat_vals = bat_str.split(',')
            if len(bat_vals) != 2:
                return None
            bat_L = float(bat_vals[0])
            bat_R = float(bat_vals[1])

            if (len(flex_L_raw) != 5 or len(accel_L) != 3 or len(gyro_L) != 3 or
                len(flex_R_raw) != 5 or len(accel_R) != 3 or len(gyro_R) != 3):
                return None

            # Convert raw ADC values (0-4095) to normalized (0-1) using calibration
            flex_L = [self.normalize_flex_value(int(val), i, 'L') for i, val in enumerate(flex_L_raw)]
            flex_R = [self.normalize_flex_value(int(val), i, 'R') for i, val in enumerate(flex_R_raw)]

            return {
                'flex_L':  flex_L,
                'accel_L': accel_L,
                'gyro_L':  gyro_L,
                'flex_R':  flex_R,
                'accel_R': accel_R,
                'gyro_R':  gyro_R,
                'bat_L': bat_L,
                'bat_R': bat_R
            }
        except (ValueError, IndexError):
            return None
    
    def show_calibration_dialog(self):
        """Show calibration dialog with instructions"""
        if self.is_calibrating:
            return
        
        self.is_calibrating = True
        
        # Create calibration window
        cal_window = tk.Toplevel(self.root)
        cal_window.title("Sensor Calibration")
        cal_window.geometry("700x650")
        cal_window.resizable(False, False)
        cal_window.grab_set()
        self.calibration_dialog = cal_window
        
        # Center on screen
        cal_window.transient(self.root)
        
        # Title
        title = tk.Label(cal_window, text="KALIBRASI SENSOR FLEX", 
                        font=("Arial", 16, "bold"), bg="#1976D2", fg="white")
        title.pack(fill="x", padx=0, pady=0)
        
        content = tk.Frame(cal_window, bg="#2c3e50", padx=20, pady=20)
        content.pack(fill="both", expand=False)
        
        # Instructions
        inst_text = """INSTRUKSI KALIBRASI:

1. BUKA TANGAN PENUH
   - Luruskan semua jari sepenuhnya
   - Tahan posisi selama 5 DETIK
   - Jangan gerakkan tangan

2. TUTUP TANGAN (GENGGAM)
   - Kepalkan tangan sepenuhnya
   - Tahan posisi selama 5 DETIK
   - Jangan gerakkan tangan

Sistem akan merekam nilai MIN dan MAX dari sensor flex.

Tekan "START KALIBRASI" untuk memulai."""
        
        inst_label = tk.Label(content, text=inst_text, 
                             font=("Arial", 10), bg="#2c3e50", fg="#ecf0f1",
                             justify="left")
        inst_label.pack(pady=10, padx=10)
        
        # Status label
        status_label = tk.Label(content, text="Ready to start", 
                               font=("Arial", 11, "bold"), bg="#2c3e50", fg="#3498db")
        status_label.pack(pady=10)
        
        # Countdown label
        countdown_label = tk.Label(content, text="", 
                                  font=("Arial", 20, "bold"), bg="#2c3e50", fg="#e67e22")
        countdown_label.pack(pady=20)
        
        # Buttons frame
        btn_frame = tk.Frame(content, bg="#2c3e50")
        btn_frame.pack(side="bottom", pady=20, fill="x")
        
        calibration_state = {
            'phase': 0,  # 0=waiting, 1=prep_open, 2=record_open, 3=prep_close, 4=record_close, 5=done
            'countdown': 0,
            'temp_min_L': [4095]*5,
            'temp_max_L': [0]*5,
            'temp_min_R': [4095]*5,
            'temp_max_R': [0]*5,
            'buffer_open_L': [[] for _ in range(5)],  # Buffer untuk 5 detik hand open
            'buffer_open_R': [[] for _ in range(5)],
            'buffer_close_L': [[] for _ in range(5)],  # Buffer untuk 5 detik hand close
            'buffer_close_R': [[] for _ in range(5)],
        }
        
        def start_calibration():
            """Start the calibration process with 3-second prep phase first"""
            start_btn.config(state="disabled")
            calibration_state['phase'] = 1  # Start with prep phase
            calibration_state['countdown'] = 3
            status_label.config(text="PERSIAPAN TAHAP 1: SIAPKAN TANGAN TERBUKA", fg="#f39c12")
            
            def countdown_tick():
                current_phase = calibration_state['phase']
                
                if current_phase == 1:  # PREP PHASE 1
                    countdown_label.config(text=f"Persiapan...\n{calibration_state['countdown']}")
                    if calibration_state['countdown'] > 0:
                        calibration_state['countdown'] -= 1
                        cal_window.after(1000, countdown_tick)
                    else:
                        # Transition to recording open hand
                        calibration_state['phase'] = 2
                        calibration_state['countdown'] = 5
                        status_label.config(text="TAHAP 1: BUKA TANGAN PENUH (Perekaman 5 detik)", fg="#27ae60")
                        countdown_label.config(text="5")
                        # Clear buffers
                        calibration_state['buffer_open_L'] = [[] for _ in range(5)]
                        calibration_state['buffer_open_R'] = [[] for _ in range(5)]
                        cal_window.after(1000, countdown_tick)
                
                elif current_phase == 2:  # RECORD PHASE 1 (hand open)
                    countdown_label.config(text=str(calibration_state['countdown']))
                    if calibration_state['countdown'] > 0:
                        calibration_state['countdown'] -= 1
                        cal_window.after(1000, countdown_tick)
                    else:
                        # Calculate min/max from buffer_open
                        # Hand OPEN → sensor straight → ADC LOW → capture as MIN
                        for i in range(5):
                            if calibration_state['buffer_open_L'][i]:
                                calibration_state['temp_min_L'][i] = min(calibration_state['buffer_open_L'][i])
                            if calibration_state['buffer_open_R'][i]:
                                calibration_state['temp_min_R'][i] = min(calibration_state['buffer_open_R'][i])
                        
                        print(f"[CALIBRATION] Phase 2 DONE - Processed {len(calibration_state['buffer_open_L'][0])} samples")
                        print(f"  temp_min_L: {calibration_state['temp_min_L']}")
                        print(f"  temp_min_R: {calibration_state['temp_min_R']}")
                        
                        # Transition to prep phase 2
                        calibration_state['phase'] = 3
                        calibration_state['countdown'] = 3
                        status_label.config(text="PERSIAPAN TAHAP 2: SIAPKAN TANGAN MENGEPAL", fg="#f39c12")
                        countdown_label.config(text=f"Persiapan...\n{calibration_state['countdown']}")
                        cal_window.after(1000, countdown_tick)
                
                elif current_phase == 3:  # PREP PHASE 2
                    if calibration_state['countdown'] > 0:
                        calibration_state['countdown'] -= 1
                        countdown_label.config(text=f"Persiapan...\n{calibration_state['countdown']}")
                        cal_window.after(1000, countdown_tick)
                    else:
                        # Transition to recording closed hand
                        calibration_state['phase'] = 4
                        calibration_state['countdown'] = 5
                        status_label.config(text="TAHAP 2: TUTUP TANGAN (Perekaman 5 detik)", fg="#e67e22")
                        countdown_label.config(text="5")
                        # Clear buffers
                        calibration_state['buffer_close_L'] = [[] for _ in range(5)]
                        calibration_state['buffer_close_R'] = [[] for _ in range(5)]
                        cal_window.after(1000, countdown_tick)
                
                elif current_phase == 4:  # RECORD PHASE 2 (hand closed)
                    countdown_label.config(text=str(calibration_state['countdown']))
                    if calibration_state['countdown'] > 0:
                        calibration_state['countdown'] -= 1
                        cal_window.after(1000, countdown_tick)
                    else:
                        # Calculate min/max from buffer_close
                        # Hand CLOSE → sensor bent → ADC HIGH → capture as MAX
                        for i in range(5):
                            if calibration_state['buffer_close_L'][i]:
                                calibration_state['temp_max_L'][i] = max(calibration_state['buffer_close_L'][i])
                            if calibration_state['buffer_close_R'][i]:
                                calibration_state['temp_max_R'][i] = max(calibration_state['buffer_close_R'][i])
                        
                        print(f"[CALIBRATION] Phase 4 DONE - Processed {len(calibration_state['buffer_close_L'][0])} samples")
                        print(f"  temp_max_L: {calibration_state['temp_max_L']}")
                        print(f"  temp_max_R: {calibration_state['temp_max_R']}")
                        
                        # Calibration done
                        calibration_state['phase'] = 5
                        countdown_label.config(text="")
                        finish_calibration()
            
            countdown_tick()
        
        def finish_calibration():
            """Finish calibration and save data"""
            status_label.config(text="✓ Kalibrasi selesai!", fg="#27ae60")
            
            print(f"[CALIBRATION] FINAL VALUES BEFORE SAVE:")
            print(f"  temp_min_L: {calibration_state['temp_min_L']}")
            print(f"  temp_max_L: {calibration_state['temp_max_L']}")
            print(f"  temp_min_R: {calibration_state['temp_min_R']}")
            print(f"  temp_max_R: {calibration_state['temp_max_R']}")
            
            # Update calibration data with recorded min/max
            self.calibration_data['flex_min_L'] = calibration_state['temp_min_L']
            self.calibration_data['flex_max_L'] = calibration_state['temp_max_L']
            self.calibration_data['flex_min_R'] = calibration_state['temp_min_R']
            self.calibration_data['flex_max_R'] = calibration_state['temp_max_R']
            
            print(f"[CALIBRATION] FINAL VALUES AFTER UPDATE TO self:")
            print(f"  self.calibration_data: {self.calibration_data}")
            
            # Save calibration
            self.save_calibration()
            self.log("Calibration saved!")
            
            # Reset counter
            self.gestures_since_calibration = 0
            
            # Close dialog
            cal_window.after(1000, lambda: cal_window.destroy())
            self.is_calibrating = False
            self.btn_start.config(state="normal")
            
            # Clear any pending dialog reference
            if self.calibration_dialog == cal_window:
                self.calibration_dialog = None
        
        def update_calibration_from_data(flex_L_raw, flex_R_raw):
            """Collect sensor data into buffers during recording phases"""
            # Phase 2: Recording hand open (collecting MAX values)
            if calibration_state['phase'] == 2:
                for i in range(5):
                    calibration_state['buffer_open_L'][i].append(int(flex_L_raw[i]))
                    calibration_state['buffer_open_R'][i].append(int(flex_R_raw[i]))
                
                # Log buffer size every 50 samples
                if len(calibration_state['buffer_open_L'][0]) % 50 == 0:
                    print(f"[CALIBRATION] Phase 2 - Buffer collected: {len(calibration_state['buffer_open_L'][0])} samples")
                    print(f"  L: {[calibration_state['buffer_open_L'][i][-1] for i in range(5)]}")
                    print(f"  R: {[calibration_state['buffer_open_R'][i][-1] for i in range(5)]}")
            
            # Phase 4: Recording hand closed (collecting MIN values)
            elif calibration_state['phase'] == 4:
                for i in range(5):
                    calibration_state['buffer_close_L'][i].append(int(flex_L_raw[i]))
                    calibration_state['buffer_close_R'][i].append(int(flex_R_raw[i]))
                
                # Log buffer size every 50 samples
                if len(calibration_state['buffer_close_L'][0]) % 50 == 0:
                    print(f"[CALIBRATION] Phase 4 - Buffer collected: {len(calibration_state['buffer_close_L'][0])} samples")
                    print(f"  L: {[calibration_state['buffer_close_L'][i][-1] for i in range(5)]}")
                    print(f"  R: {[calibration_state['buffer_close_R'][i][-1] for i in range(5)]}")
        
        # Store the update function for callback
        cal_window.calibration_update = update_calibration_from_data
        
        start_btn = tk.Button(btn_frame, text="START KALIBRASI", 
                             command=start_calibration,
                             bg="#27ae60", fg="white", font=("Arial", 12, "bold"),
                             padx=40, pady=15, relief="raised", cursor="hand2")
        start_btn.pack(side="left", padx=20, pady=10)
        
        cancel_btn = tk.Button(btn_frame, text="CANCEL", 
                              command=lambda: (cal_window.destroy(), 
                                             setattr(self, 'is_calibrating', False),
                                             self.btn_start.config(state="normal")),
                              bg="#e74c3c", fg="white", font=("Arial", 12, "bold"),
                              padx=40, pady=15, relief="raised", cursor="hand2")
        cancel_btn.pack(side="left", padx=20, pady=10)
    
    def next_repetition(self):
        """Save recording and move to next (3 repetitions + augmentation)"""
        if len(self.recorded_data) == 0:
            messagebox.showwarning("Warning", "No data recorded! Check connection and try again.")
            return
        
        try:
            self.save_csv()
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")
            return
        
        current_count = self.gesture_recording_count.get(self.current_gesture_index, 0)
        self.gesture_recording_count[self.current_gesture_index] = current_count + 1
        self.total_recordings_completed += 1
        
        # Track gestures per category
        current_gesture = self.gesture_list[self.current_gesture_index]
        category = current_gesture['type'].upper()
        self.category_gesture_count[category] = self.category_gesture_count.get(category, 0) + 1
        
        if self.gesture_recording_count[self.current_gesture_index] >= 15:
            self.current_gesture_index += 1
            self.recorded_data = []
            self.data_count_label.config(text="Samples: 0")
            
            if self.current_gesture_index < len(self.gesture_list):
                gesture = self.gesture_list[self.current_gesture_index]
                self.log(f"✓ Gesture completed! Next: {gesture['type']} - {gesture['label']}")
            else:
                self.log("=" * 60)
                self.log("✓✓✓ SEMUA GESTURE SELESAI! 3x setiap gesture telah terekam.")
                self.log("=" * 60)
                self.log("Selanjutnya:")
                self.log("1. Gunakan data augmentation untuk generate variasi tambahan")
                self.log("2. Atau langsung training model dengan 3 repetisi + augmentation")
                self.log("=" * 60)
                self.btn_start.config(state="disabled")
                self.btn_retry.config(state="disabled")
                self.btn_next.config(state="disabled")
        else:
            self.recorded_data = []
            self.data_count_label.config(text="Samples: 0")
            count = self.gesture_recording_count[self.current_gesture_index]
            self.log(f"✓ Recording {count}/3 tersimpan!")
        
        # Clear chart and show placeholder
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None
        if self.chart_frame:
            self.chart_frame.destroy()
            self.chart_frame = None
        
        # Show placeholder again
        if self.chart_placeholder:
            self.chart_placeholder.pack(fill="both", expand=True)
        
        self.update_gesture_display()
        self.update_start_button()
    
    def save_csv(self):
        """Save recorded data to CSV"""
        if not self.recorded_data:
            return
        
        gesture = self.gesture_list[self.current_gesture_index]
        gesture_type = gesture['type'].lower()
        label = gesture['label'].replace(' ', '_')
        
        current_count = self.gesture_recording_count.get(self.current_gesture_index, 0) + 1
        
        output_dir = r"C:\FOLDERKU\SmartGlove\datashet\{}".format(gesture_type)
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_rep{current_count}_{timestamp}.csv"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            header = ['timestamp']
            for i in range(1, 6):
                header.append(f'flex{i}_L')
            for axis in ['X', 'Y', 'Z']:
                header.append(f'acc{axis}_L')
            for axis in ['X', 'Y', 'Z']:
                header.append(f'gyro{axis}_L')
            for i in range(1, 6):
                header.append(f'flex{i}_R')
            for axis in ['X', 'Y', 'Z']:
                header.append(f'acc{axis}_R')
            for axis in ['X', 'Y', 'Z']:
                header.append(f'gyro{axis}_R')
            header.append('repetition')
            writer.writerow(header)
            for data in self.recorded_data:
                row = [data['timestamp']]
                row.extend(data['flex_L'])
                row.extend(data['accel_L'])
                row.extend(data['gyro_L'])
                row.extend(data['flex_R'])
                row.extend(data['accel_R'])
                row.extend(data['gyro_R'])
                row.append(data['repetition'])
                writer.writerow(row)
        self.log(f"Saved: {filename} ({len(self.recorded_data)} samples)")
    
    def log(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def on_closing(self):
        """Handle window close"""
        if self.is_recording:
            if messagebox.askokcancel("Quit", "Recording in progress. Are you sure?"):
                self.is_reading = False
                if self.udp_socket:
                    self.udp_socket.close()
                self.root.destroy()
        else:
            self.is_reading = False
            if self.udp_socket:
                self.udp_socket.close()
            self.root.destroy()


# ===== MAIN =====
if __name__ == "__main__":
    root = tk.Tk()
    app = DataCollectionApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()