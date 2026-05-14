import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socket
import threading
import csv
import os
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
        self.total_repetitions = 5
        
        # Recording state
        self.is_recording = False
        self.recorded_data = []
        self.recording_start_time = 0
        self.recording_timer = 3
        self.countdown_seconds = 0
        
        # Recording phases
        self.preparation_phase = False
        self.data_recording_phase = False
        self.preparation_time = 3
        self.data_recording_time = 0
        
        # Track recording progress
        self.gesture_recording_count = {}
        self.total_recordings_completed = 0
        
        # Last data received timestamp (untuk monitor koneksi)
        self.last_data_time = 0

        # ── Sensor health detection ─────────────────────────────────────────
        # Threshold dari perilaku hardware nyata:
        #   Flex terlepas  → stuck di 1.0 (pull-up)  atau 0.0 (short)
        #   Gyro baterai   → semua axis saturasi mendekati 1.0 atau -1.0
        self._FLEX_HIGH        = 0.96   # flex >= ini = kemungkinan terlepas
        self._FLEX_LOW         = 0.04   # flex <= ini = kemungkinan short
        self._GYRO_SAT         = 0.95   # |gyro| >= ini pada semua axis = baterai drop
        self._STUCK_FRAMES     = 8      # frame berturut stuck → error (8×10ms = 80ms)

        self._flex_R_cnt  = [0] * 5    # counter stuck per jari kanan
        self._flex_L_cnt  = [0] * 5    # counter stuck per jari kiri
        self._health_ok   = True       # False = ada sensor error aktif
        self._health_msg  = ""         # pesan error terakhir
        self._last_health_warn = 0     # throttle popup

        # Category tracking
        self.selected_category = None
        self.category_buttons = {}
        self.gesture_list_buttons = {}
        
        # Setup UI
        self.setup_ui()
        
        # Bind keyboard shortcuts
        self.root.bind('<space>', lambda e: self.on_space_pressed())
        self.root.bind('<Right>', lambda e: self.on_right_pressed())
        self.root.bind('<Left>', lambda e: self.on_left_pressed())
        
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
            with open('bisindo_gesture_list.txt', 'r', encoding='utf-8') as f:
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
                self.log("INSTRUKSI PENGGUNAAN (UDP MODE):")
                self.log("1. UDP Server akan auto-start, tunggu status 'ONLINE'")
                self.log("2. Pastikan ESP32 Master sudah terkoneksi ke WiFi")
                self.log("3. Klik START untuk mulai recording")
                self.log("4. Setelah recording selesai, klik NEXT untuk simpan")
                self.log("5. Ulangi sampai semua gesture 5x terekam")
                self.log("=" * 60)
                self.log(f"UDP Port: {self.udp_port}")
                self.log(f"Pastikan IP PC ini sudah diset di ESP32 Master")
            
            self.root.after(100, log_startup)
        except FileNotFoundError:
            messagebox.showerror("Error", "File 'gesture_list_complete.txt' not found!")
            self.root.quit()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load gesture list: {e}")
            self.root.quit()
    
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
                if file.startswith(label) and file.endswith('.csv'):
                    rep_count += 1
            
            self.gesture_recording_count[gesture_idx] = rep_count
            self.total_recordings_completed += rep_count
        
        # Find first incomplete gesture
        for i in range(len(self.gesture_list)):
            if self.gesture_recording_count[i] < 5:
                return i
        
        return len(self.gesture_list)  # All done
    
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

        # ── Sensor Health Panel ─────────────────────────────────────────────
        health_frame = tk.Frame(gesture_frame, bg="#2c3e50")
        health_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(health_frame, text="STATUS SENSOR",
                 font=("Arial", 8, "bold"), bg="#2c3e50", fg="#95a5a6").pack(anchor="w")

        # Grid 2×6: Flex R dan L per jari
        grid_frame = tk.Frame(health_frame, bg="#2c3e50")
        grid_frame.pack(fill="x")

        self._flex_leds = {'R': [], 'L': []}
        for col, side in enumerate(['R', 'L']):
            tk.Label(grid_frame, text=f"Flex {side}", font=("Arial", 8),
                     bg="#2c3e50", fg="#95a5a6").grid(row=0, column=col*6, columnspan=5,
                     sticky="w", padx=(8 if col else 2, 2))
            for j in range(5):
                lbl = tk.Label(grid_frame, text=f"{j+1}", width=3,
                               font=("Arial", 8, "bold"), bg="#27ae60", fg="white",
                               relief="flat")
                lbl.grid(row=1, column=col*6 + j, padx=1, pady=1)
                self._flex_leds[side].append(lbl)

        # IMU + Gyro status
        imu_frame = tk.Frame(health_frame, bg="#2c3e50")
        imu_frame.pack(fill="x", pady=2)

        self._imu_leds = {}
        for i, name in enumerate(['IMU-R', 'GYRO-R', 'IMU-L', 'GYRO-L']):
            lbl = tk.Label(imu_frame, text=name, font=("Arial", 8, "bold"),
                           bg="#27ae60", fg="white", padx=6, pady=2, relief="flat")
            lbl.pack(side="left", padx=2)
            self._imu_leds[name] = lbl

        # Pesan error sensor
        self.sensor_warn_label = tk.Label(health_frame, text="",
                                          font=("Arial", 8, "bold"),
                                          bg="#2c3e50", fg="#e74c3c",
                                          wraplength=340, justify="left")
        self.sensor_warn_label.pack(fill="x", pady=2)
        
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
        
        # Control Buttons
        control_frame = tk.LabelFrame(right_column, text="KONTROL",
                                     font=("Arial", 9, "bold"), bg="#2c3e50", fg="#ecf0f1",
                                     padx=8, pady=8)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        self.btn_start = tk.Button(control_frame, text="START\n[SPACE]", 
                                   command=self.start_recording,
                                   bg="#27ae60", fg="white", 
                                   font=("Arial", 9, "bold"),
                                   padx=10, pady=8,
                                   relief="flat",
                                   cursor="hand2",
                                   state="disabled")
        self.btn_start.pack(fill="x", pady=3)
        
        self.btn_retry = tk.Button(control_frame, text="RETRY\n[LEFT ←]", 
                                   command=self.retry_recording,
                                   bg="#e67e22", fg="white",
                                   font=("Arial", 9, "bold"),
                                   padx=10, pady=8,
                                   relief="flat",
                                   cursor="hand2",
                                   state="disabled")
        self.btn_retry.pack(fill="x", pady=3)
        
        self.btn_next = tk.Button(control_frame, text="NEXT\n[RIGHT →]", 
                                  command=self.next_repetition,
                                  bg="#3498db", fg="white",
                                  font=("Arial", 9, "bold"),
                                  padx=10, pady=8,
                                  relief="flat",
                                  cursor="hand2",
                                  state="disabled")
        self.btn_next.pack(fill="x", pady=3)
        
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
            if count >= 5:
                status_text = "✓"
                bg_color = "#27ae60"  # Green
                fg_color = "white"
            else:
                status_text = f"{count}/5"
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

    # ── Sensor Health Detection ───────────────────────────────────────────────
    def check_sensor_health(self, parsed):
        """
        Deteksi kegagalan sensor dari satu frame data.
        Dipanggil setiap frame masuk — baik saat recording maupun tidak.

        Kegagalan yang dideteksi (berdasarkan perilaku hardware nyata):
          - Flex >= 0.96 selama 8 frame → sensor terlepas (pull-up ke HIGH)
          - Flex <= 0.04 selama 8 frame → sensor short/ground terlepas
          - Semua gyro axis >= 0.95 atau <= -0.95 → baterai drop/habis
          - Accel semua 0.0 → MPU6050 disconnect (I2C putus)
        """
        errors = []

        # ── Flex RIGHT (tangan kanan / Master) ───────────────────────────────
        for i, val in enumerate(parsed['flex_R']):
            if val >= self._FLEX_HIGH or val <= self._FLEX_LOW:
                self._flex_R_cnt[i] = min(self._flex_R_cnt[i] + 1, self._STUCK_FRAMES + 1)
            else:
                self._flex_R_cnt[i] = max(0, self._flex_R_cnt[i] - 2)  # recover cepat

            err = self._flex_R_cnt[i] >= self._STUCK_FRAMES
            color = "#e74c3c" if err else "#27ae60"
            self.root.after(0, lambda c=color, idx=i: (
                self._flex_leds['R'][idx].config(bg=c)
            ))
            if err:
                tip = "terlepas" if val >= self._FLEX_HIGH else "short/0"
                errors.append(f"Flex KANAN jari {i+1} {tip} ({val:.2f})")

        # ── Flex LEFT (tangan kiri / Slave) ──────────────────────────────────
        for i, val in enumerate(parsed['flex_L']):
            if val >= self._FLEX_HIGH or val <= self._FLEX_LOW:
                self._flex_L_cnt[i] = min(self._flex_L_cnt[i] + 1, self._STUCK_FRAMES + 1)
            else:
                self._flex_L_cnt[i] = max(0, self._flex_L_cnt[i] - 2)

            err = self._flex_L_cnt[i] >= self._STUCK_FRAMES
            color = "#e74c3c" if err else "#27ae60"
            self.root.after(0, lambda c=color, idx=i: (
                self._flex_leds['L'][idx].config(bg=c)
            ))
            if err:
                tip = "terlepas" if val >= self._FLEX_HIGH else "short/0"
                errors.append(f"Flex KIRI jari {i+1} {tip} ({val:.2f})")

        # ── IMU RIGHT — accel disconnect ──────────────────────────────────────
        ax, ay, az = parsed['accel_R']
        imu_R_disc = (ax == 0.0 and ay == 0.0 and az == 0.0)
        imu_R_color = "#e74c3c" if imu_R_disc else "#27ae60"
        self.root.after(0, lambda c=imu_R_color: self._imu_leds['IMU-R'].config(bg=c))
        if imu_R_disc:
            errors.append("IMU KANAN disconnect (I2C putus)")

        # ── IMU LEFT — accel disconnect ───────────────────────────────────────
        ax, ay, az = parsed['accel_L']
        imu_L_disc = (ax == 0.0 and ay == 0.0 and az == 0.0)
        imu_L_color = "#e74c3c" if imu_L_disc else "#27ae60"
        self.root.after(0, lambda c=imu_L_color: self._imu_leds['IMU-L'].config(bg=c))
        if imu_L_disc:
            errors.append("IMU KIRI disconnect (I2C putus)")

        # ── Gyro saturasi (baterai drop) ─────────────────────────────────────
        def gyro_saturated(g):
            return all(abs(v) >= self._GYRO_SAT for v in g)

        gyro_R_err = gyro_saturated(parsed['gyro_R'])
        gyro_L_err = gyro_saturated(parsed['gyro_L'])

        gyro_R_color = "#e74c3c" if gyro_R_err else "#27ae60"
        gyro_L_color = "#e74c3c" if gyro_L_err else "#27ae60"
        self.root.after(0, lambda c=gyro_R_color: self._imu_leds['GYRO-R'].config(bg=c))
        self.root.after(0, lambda c=gyro_L_color: self._imu_leds['GYRO-L'].config(bg=c))

        if gyro_R_err:
            errors.append(f"GYRO KANAN saturasi — baterai kanan hampir habis!")
        if gyro_L_err:
            errors.append(f"GYRO KIRI saturasi — baterai kiri hampir habis!")

        # ── Update status ─────────────────────────────────────────────────────
        self._health_ok  = len(errors) == 0
        self._health_msg = " | ".join(errors) if errors else ""

        # Update label peringatan di UI
        warn_text = ("⚠ " + self._health_msg) if errors else ""
        self.root.after(0, lambda t=warn_text: self.sensor_warn_label.config(text=t))

        # Jika sedang recording dan ada error → stop otomatis + log peringatan
        if errors and self.is_recording:
            now = time.time()
            if now - self._last_health_warn > 2.0:  # throttle 2 detik
                self._last_health_warn = now
                for e in errors:
                    self.root.after(0, lambda msg=e: self.log(f"[SENSOR ERROR] {msg}"))

                # Jika error baterai → stop recording langsung (data akan rusak semua)
                is_battery = any("baterai" in e for e in errors)
                if is_battery:
                    self.root.after(0, self._stop_for_sensor_error)

    def _stop_for_sensor_error(self):
        """Hentikan recording karena kegagalan sensor kritis."""
        if not self.is_recording:
            return
        self.is_recording = False
        self.is_reading = False
        self.recorded_data = []
        self.data_count_label.config(text="Samples: 0")
        self.recording_indicator.config(text="ERROR SENSOR", fg="#e74c3c")
        self.timer_label.config(text="!", font=("Arial", 72, "bold"), fg="#e74c3c")
        self.update_start_button()
        messagebox.showerror(
            "Sensor Error",
            f"Recording dihentikan!\n\n{self._health_msg}\n\n"
            "Periksa baterai dan koneksi sensor,\nlalu coba lagi."
        )

    def receive_udp_always(self):
        """Background thread to continuously receive UDP data (update status to ONLINE)"""
        first_packet_logged = False
        while self.is_connected:
            try:
                if not self.udp_socket:
                    time.sleep(0.1)
                    continue

                try:
                    data, addr = self.udp_socket.recvfrom(1024)
                    line = data.decode('utf-8', errors='ignore').strip()

                    if line.startswith("DATA|"):
                        self.last_data_time = time.time()

                        if not first_packet_logged:
                            self.root.after(0, lambda: self.log("Data from ESP32 received via UDP!"))
                            first_packet_logged = True

                        # Cek kesehatan sensor setiap frame
                        parsed_frame = self.parse_data_line(line)
                        if parsed_frame:
                            self.check_sensor_health(parsed_frame)

                        # Simpan hanya jika sensor sehat
                        if self.is_recording and parsed_frame and self._health_ok:
                            timestamp = int((time.time() - self.recording_start_time) * 1000)
                            parsed_frame['timestamp'] = timestamp
                            parsed_frame['repetition'] = (
                                self.gesture_recording_count.get(self.current_gesture_index, 0) + 1
                            )
                            self.recorded_data.append(parsed_frame)
                            self.root.after(0, lambda: self.data_count_label.config(
                                text=f"Samples: {len(self.recorded_data)}"
                            ))

                except socket.timeout:
                    pass

            except Exception as e:
                if self.is_connected:
                    self.log(f"[ERROR] UDP background receive error: {e}")
                break

            time.sleep(0.01)

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
        """Get recording duration based on category"""
        durations = {
            'ANGKA': 3,
            'HURUF': 3,
            'KATA': 4,
            'FRASA': 5
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
            self.desc_display.config(
                text=f"Recording {current_count}/5 completed"
            )
            
            self.counter_label.config(text=f"Recording: {current_count}/5")
            
            self.progress_label.config(
                text=f"Gesture: {self.current_gesture_index + 1}/{len(self.gesture_list)}  •  Progress: {current_count}/5"
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
            self.desc_display.config(text="All gestures completed!")
            self.counter_label.config(text="Recording: 5/5")
            self.progress_label.config(text="All Gestures Completed!")
            total_expected = len(self.gesture_list) * self.total_repetitions
            self.overall_progress_label.config(text=f"Overall: 100% ({total_expected}/{total_expected})")
            messagebox.showinfo("Complete", "All gestures collected successfully!")
    
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
        """Start preparation countdown before data recording"""
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
        self.data_recording_phase = False
        self.recorded_data = []
        self.recording_start_time = time.time()
        
        gesture = self.gesture_list[self.current_gesture_index]
        self.data_recording_time = self.get_recording_duration(gesture['type'])
        self.countdown_seconds = self.preparation_time
        
        self.btn_start.config(state="disabled")
        self.btn_retry.config(state="disabled")
        self.btn_next.config(state="disabled")
        
        self.recording_indicator.config(text="GET READY", fg="#f39c12")
        self.progress_bar['value'] = 0
        
        current_count = self.gesture_recording_count.get(self.current_gesture_index, 0)
        self.log(f"Preparation (3s)... {gesture['type']} - {gesture['label']} ({current_count + 1}/5)")
        
        self.timer_thread = threading.Thread(target=self.update_recording_timer, daemon=True)
        self.timer_thread.start()
    
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
        """Handle recording phases"""
        phase_start_time = time.time()
        transition_phase = False
        transition_time = 0.5
        
        while self.is_recording:
            elapsed = time.time() - self.recording_start_time
            
            # PHASE 1: PREPARATION
            if self.preparation_phase and elapsed < self.preparation_time:
                remaining = self.preparation_time - elapsed
                countdown_int = int(remaining) + 1 if remaining % 1 > 0.5 else int(remaining)
                if countdown_int <= 0:
                    countdown_int = 1
                
                display_text = str(countdown_int)
                self.root.after(0, lambda text=display_text: 
                              self.timer_label.config(text=text, font=("Arial", 72, "bold"), fg="#f39c12") if self.is_recording else None)
                
                progress = int((elapsed / self.preparation_time) * 100)
                if self.is_recording:
                    self.progress_bar['value'] = progress
                
                time.sleep(0.1)
            
            # TRANSITION: Show "GO!"
            elif self.preparation_phase and elapsed >= self.preparation_time and not transition_phase:
                transition_phase = True
                phase_start_time = time.time()
                
                self.root.after(0, lambda: self.timer_label.config(text="GO!", font=("Arial", 72, "bold"), fg="#27ae60"))
                self.root.after(0, lambda: self.recording_indicator.config(text="START NOW", fg="#27ae60"))
            
            elif self.preparation_phase and transition_phase:
                transition_elapsed = time.time() - phase_start_time
                
                if transition_elapsed >= transition_time:
                    self.preparation_phase = False
                    self.data_recording_phase = True
                    self.recording_start_time = time.time()
                    
                    self.is_reading = True
                    gesture = self.gesture_list[self.current_gesture_index]
                    current_count = self.gesture_recording_count.get(self.current_gesture_index, 0)
                    self.root.after(0, lambda: (
                        self.recording_indicator.config(text="RECORDING", fg="#e74c3c"),
                        self.log(f"Recording for {self.data_recording_time}s... ({current_count + 1}/5)")
                    ))
                    
                    read_thread = threading.Thread(target=self.read_udp_data, daemon=True)
                    read_thread.start()
                
                time.sleep(0.05)
            
            # PHASE 2: DATA RECORDING
            elif self.data_recording_phase:
                elapsed_recording = time.time() - self.recording_start_time
                remaining = self.data_recording_time - elapsed_recording
                
                if remaining <= 0:
                    self.root.after(0, self.stop_recording)
                    break
                
                display_text = f"{remaining:.1f}"
                self.root.after(0, lambda text=display_text: 
                              self.timer_label.config(text=text, font=("Arial", 48, "bold"), fg="#27ae60") if self.is_recording else None)
                
                progress = int((elapsed_recording / self.data_recording_time) * 100)
                if self.is_recording:
                    self.progress_bar['value'] = progress
                
                time.sleep(0.1)
            else:
                break
    
    def read_udp_data(self):
        """Read data from UDP socket"""
        log_count = 0
        receive_count = 0
        
        while self.is_reading and self.is_recording:
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
        """Parse data line from ESP32"""
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

            flex_L  = [float(x) for x in parts[1][2:].split(',')]
            accel_L = [float(x) for x in parts[2][2:].split(',')]
            gyro_L  = [float(x) for x in parts[3][2:].split(',')]
            flex_R  = [float(x) for x in parts[4][2:].split(',')]
            accel_R = [float(x) for x in parts[5][2:].split(',')]
            gyro_R  = [float(x) for x in parts[6][2:].split(',')]
            bat_str = parts[7][4:]
            bat_vals = bat_str.split(',')
            if len(bat_vals) != 2:
                return None
            bat_L = float(bat_vals[0])
            bat_R = float(bat_vals[1])

            if (len(flex_L) != 5 or len(accel_L) != 3 or len(gyro_L) != 3 or
                len(flex_R) != 5 or len(accel_R) != 3 or len(gyro_R) != 3):
                return None

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
    
    def next_repetition(self):
        """Save recording and move to next"""
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
        
        if self.gesture_recording_count[self.current_gesture_index] >= 5:
            self.current_gesture_index += 1
            self.recorded_data = []
            self.data_count_label.config(text="Samples: 0")
            
            if self.current_gesture_index < len(self.gesture_list):
                gesture = self.gesture_list[self.current_gesture_index]
                self.log(f"Gesture completed! Next: {gesture['type']} - {gesture['label']}")
            else:
                self.log("ALL GESTURES COMPLETED!")
                self.btn_start.config(state="disabled")
                self.btn_retry.config(state="disabled")
                self.btn_next.config(state="disabled")
        else:
            self.recorded_data = []
            self.data_count_label.config(text="Samples: 0")
            count = self.gesture_recording_count[self.current_gesture_index]
            self.log(f"Recording {count}/5 saved!")
        
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