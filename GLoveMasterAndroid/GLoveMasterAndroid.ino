/*
 * SMART GLOVE - ESP32-S3 MASTER (Tangan Kanan)  [FIXED v2]
 * KOMUNIKASI: WiFi Hotspot HP → TCP JSON ke Android
 *
 * SETUP HOTSPOT HP:
 *   SSID    : SmartGlove
 *   Password: smartglove1234
 *   Android IP (gateway): 192.168.43.1
 *   Port TCP: 8080
 *
 * ESP-NOW : Slave → Master (tangan kiri)
 * TCP JSON: Master → Android via hotspot HP
 *
 * ╔══════════════════════════════════════════════════════════╗
 * ║  FIX UTAMA: Urutan JSON sekarang PERSIS sama dengan      ║
 * ║  feature_order di model_info.json & scaler_params.json:  ║
 * ║                                                          ║
 * ║  [fL0..fL4, aLx,aLy,aLz, gLx,gLy,gLz,                  ║
 * ║   fR0..fR4, aRx,aRy,aRz, gRx,gRy,gRz]                  ║
 * ║                                                          ║
 * ║  = 22 fitur, urutan sama dengan FEATURE_COLS di          ║
 * ║    notebook training Python                              ║
 * ╚══════════════════════════════════════════════════════════╝
 *
 * Format JSON ke Android:
 * {
 *   "fL":[f1,f2,f3,f4,f5],   ← flex kiri  (raw ADC 0-4095)
 *   "aL":[x,y,z],            ← accel kiri  (g)
 *   "gL":[x,y,z],            ← gyro kiri   (deg/s)
 *   "fR":[f1,f2,f3,f4,f5],   ← flex kanan (raw ADC 0-4095)
 *   "aR":[x,y,z],            ← accel kanan (g)
 *   "gR":[x,y,z],            ← gyro kanan  (deg/s)
 *   "bL":volt, "bR":volt,   ← FIX Bug #4: keduanya dalam Volt (bukan raw ADC)
 *   "sl":0/1, "ts":ms
 * }
 *
 * PENTING: struct_message HARUS SAMA PERSIS dengan GloveSlave.ino
 */

#include <WiFi.h>
#include <WiFiClient.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>

// ==================== HOTSPOT CONFIG ====================
#define HOTSPOT_SSID     "SmartGlove"
#define HOTSPOT_PASSWORD "smartglove1234"
#define ANDROID_IP       "192.168.43.1"
#define TCP_PORT         8080

// ==================== DATA STRUCTURE ====================
// Struct ini HARUS SAMA PERSIS dengan GloveSlave.ino
typedef struct struct_message {
    float flex[5];          // raw ADC flex (0–4095)
    float accel[3];         // g
    float gyro[3];          // deg/s
    float batteryVoltage;   // raw ADC baterai master / Volt slave
    int   batteryPercentage;
    unsigned long timestamp;
} struct_message;

typedef struct channel_info {
    uint8_t channel;
    char identifier[10];
} channel_info;

struct_message rxData;    // data dari slave (tangan kiri)
struct_message localData; // data master (tangan kanan)

// ==================== PIN CONFIGURATION ====================
const int FLEX_PIN[5] = {1, 2, 3, 4, 5};
const int SDA_PIN  = 9;
const int SCL_PIN  = 8;
const int VBAT_PIN = 7;
const int LED_PIN  = 6;

// ==================== MPU6050 ====================
const uint8_t MPU_ADDR = 0x68;

void mpuWrite(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

void mpuRead(uint8_t reg, uint8_t *buf, uint8_t len) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU_ADDR, len);
    for (uint8_t i = 0; i < len; i++) buf[i] = Wire.read();
}

bool mpuInit() {
    mpuWrite(0x6B, 0x00); delay(100);
    mpuWrite(0x1C, 0x00); // accel ±2g
    mpuWrite(0x1B, 0x00); // gyro ±250°/s
    uint8_t who = 0;
    mpuRead(0x75, &who, 1);
    return (who == 0x68);
}

void mpuGetMotion6(int16_t *ax, int16_t *ay, int16_t *az,
                   int16_t *gx, int16_t *gy, int16_t *gz) {
    uint8_t buf[14];
    mpuRead(0x3B, buf, 14);
    *ax = (buf[0]  << 8) | buf[1];
    *ay = (buf[2]  << 8) | buf[3];
    *az = (buf[4]  << 8) | buf[5];
    *gx = (buf[8]  << 8) | buf[9];
    *gy = (buf[10] << 8) | buf[11];
    *gz = (buf[12] << 8) | buf[13];
}

// ==================== TCP CLIENT ====================
WiFiClient tcpClient;

// ==================== STATE ====================
unsigned long lastDataReceived     = 0;
unsigned long lastPrint            = 0;
unsigned long lastTCPSend          = 0;
unsigned long lastWiFiAttempt      = 0;
unsigned long lastChannelBroadcast = 0;
unsigned long lastLedBlink         = 0;
unsigned long lastTCPAttempt       = 0;
unsigned long wifiRetryDelay       = 5000;
unsigned long tcpRetryDelay        = 2000;
unsigned long bootTime             = 0;

bool    slaveConnected = false;
bool    wifiConnected  = false;
bool    tcpConnected   = false;
uint8_t currentChannel = 1;

// FIX Bug #6: Slave loop delay(50) → ~20Hz, master TCP 20ms → 50Hz.
// Guard ini mencegah frame slave dikirim 2-3x ke Android.
unsigned long lastSlaveTimestamp = 0;

uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// ==================== FORWARD DECLARATIONS ====================
void checkAndRetryWiFi();
void checkAndRetryTCP();
void readLocalSensors();
void controlLED();
void sendTCPData();
void broadcastChannelInfo();
void syncESPNowChannel();
void printStatus();

// ==================== ESP-NOW CALLBACK ====================
void OnDataRecv(const esp_now_recv_info *info,
                const uint8_t *incomingData, int len)
{
    memcpy(&rxData, incomingData, sizeof(rxData));
    // FIX Bug #6: simpan timestamp slave untuk cek duplikat di sendTCPData()
    lastSlaveTimestamp = rxData.timestamp;
    lastDataReceived   = millis();
    slaveConnected     = true;
}

// ==================== SETUP ====================
void setup() {
    Serial.begin(115200);
    delay(3000);

    Serial.println("\n=====================================");
    Serial.println(" SMART GLOVE MASTER v2 - TCP ANDROID");
    Serial.println("=====================================");

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);

    Serial.printf("[WiFi] Connecting to '%s'...\n", HOTSPOT_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(HOTSPOT_SSID, HOTSPOT_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500); Serial.print("."); attempts++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        wifiConnected  = true;
        currentChannel = WiFi.channel();
        Serial.printf("[WiFi] OK! IP: %s  Ch: %d\n",
                      WiFi.localIP().toString().c_str(), currentChannel);
        Serial.printf("[TCP]  Target Android: %s:%d\n", ANDROID_IP, TCP_PORT);
    } else {
        Serial.println("[WiFi] FAILED — retry di loop");
    }

    Serial.printf("[MAC] %s\n", WiFi.macAddress().c_str());

    Serial.println("[ESP-NOW] Initializing...");
    if (esp_now_init() != ESP_OK) {
        Serial.println("[ESP-NOW] ERROR: init failed!");
    } else {
        esp_now_register_recv_cb(OnDataRecv);
        esp_now_peer_info_t peerInfo = {};
        memcpy(peerInfo.peer_addr, broadcastAddress, 6);
        peerInfo.channel = 0;
        peerInfo.encrypt = false;
        esp_now_add_peer(&peerInfo);
        Serial.println("[ESP-NOW] OK");
        syncESPNowChannel();
    }

    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);
    delay(200);
    Serial.println(mpuInit() ? "[MPU6050] OK" : "[MPU6050] WARNING: tidak terdeteksi!");

    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);
    Serial.println("[ADC] OK — 12-bit (0–4095)");

    Serial.println("\n[READY] Menunggu koneksi Android...\n");
    bootTime = millis();
    delay(1000);
}

// ==================== LOOP ====================
void loop() {
    checkAndRetryWiFi();
    if (wifiConnected) checkAndRetryTCP();

    if (millis() - lastChannelBroadcast >= 2000) {
        broadcastChannelInfo();
        lastChannelBroadcast = millis();
    }

    readLocalSensors();
    controlLED();

    // Kirim 50Hz (20ms interval)
    if (tcpConnected && millis() - lastTCPSend >= 20) {
        sendTCPData();
        lastTCPSend = millis();
    }

    if (millis() - bootTime > 10000 && millis() - lastPrint >= 5000) {
        printStatus();
        lastPrint = millis();
    }

    delay(5);
}

// ==================== READ LOCAL SENSORS ====================
void readLocalSensors() {
    localData.timestamp = millis();

    for (int i = 0; i < 5; i++)
        localData.flex[i] = (float)analogRead(FLEX_PIN[i]);

    int16_t ax, ay, az, gx, gy, gz;
    mpuGetMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    localData.accel[0] = ax / 16384.0f;
    localData.accel[1] = ay / 16384.0f;
    localData.accel[2] = az / 16384.0f;
    localData.gyro[0]  = gx / 131.0f;
    localData.gyro[1]  = gy / 131.0f;
    localData.gyro[2]  = gz / 131.0f;

    // FIX Bug #4: Konversi ke Volt (sama seperti GloveSlave.ino)
    // Slave sudah kirim Volt → master juga harus Volt agar satuan bL == bR
    int rawBat = analogRead(VBAT_PIN);
    localData.batteryVoltage    = (rawBat / 4095.0f) * 3.3f * 2.0f; // voltage divider ratio 2.0
    float pct = ((localData.batteryVoltage - 3.0f) / (4.2f - 3.0f)) * 100.0f;
    localData.batteryPercentage = (int)constrain(pct, 0, 100);
}

// ==================== SEND TCP DATA ====================
/*
 * PERBAIKAN KRITIS: Urutan key JSON sekarang PERSIS sama dengan
 * feature_order = [fL0..fL4, aLx,aLy,aLz, gLx,gLy,gLz,
 *                  fR0..fR4, aRx,aRy,aRz, gRx,gRy,gRz]
 *
 * Versi lama salah: fL, fR, aL, aR, gL, gR
 * Versi ini benar : fL, aL, gL, fR, aR, gR
 */
void sendTCPData() {
    if (!tcpClient.connected()) {
        tcpConnected = false;
        return;
    }

    bool slaveOk = slaveConnected && (millis() - lastDataReceived < 2000);

    // FIX Bug #6: Kirim hanya jika ada frame slave baru (timestamp berbeda).
    // Slave ~20Hz, master loop 5ms → tanpa guard ini tiap frame slave
    // terkirim 2-3x ke Android, mendistorsi temporal pattern.
    // Ketika slave tidak terhubung, tetap kirim data master saja (sl=0).
    static unsigned long lastSentSlaveTs = 0;
    bool slaveFrameNew = (lastSlaveTimestamp != lastSentSlaveTs);
    if (slaveOk && !slaveFrameNew) {
        return; // frame slave belum diperbarui, skip
    }
    if (slaveOk) lastSentSlaveTs = lastSlaveTimestamp;

    char json[600];
    int len = snprintf(json, sizeof(json),
        "{"
        // ── KIRI dulu (semua): flex → accel → gyro ──
        "\"fL\":[%d,%d,%d,%d,%d],"
        "\"aL\":[%.4f,%.4f,%.4f],"
        "\"gL\":[%.4f,%.4f,%.4f],"
        // ── KANAN (semua): flex → accel → gyro ──
        "\"fR\":[%d,%d,%d,%d,%d],"
        "\"aR\":[%.4f,%.4f,%.4f],"
        "\"gR\":[%.4f,%.4f,%.4f],"
        // meta — bL dan bR sekarang sama-sama dalam VOLT (FIX Bug #4)
        "\"bL\":%.2f,"
        "\"bR\":%.2f,"
        "\"sl\":%d,"
        "\"ts\":%lu"
        "}",
        // fL — flex kiri raw ADC (dari slave)
        (int)rxData.flex[0], (int)rxData.flex[1], (int)rxData.flex[2],
        (int)rxData.flex[3], (int)rxData.flex[4],
        // aL — accel kiri (g)
        rxData.accel[0], rxData.accel[1], rxData.accel[2],
        // gL — gyro kiri (deg/s)
        rxData.gyro[0],  rxData.gyro[1],  rxData.gyro[2],
        // fR — flex kanan raw ADC (dari master/lokal)
        (int)localData.flex[0], (int)localData.flex[1], (int)localData.flex[2],
        (int)localData.flex[3], (int)localData.flex[4],
        // aR — accel kanan (g)
        localData.accel[0], localData.accel[1], localData.accel[2],
        // gR — gyro kanan (deg/s)
        localData.gyro[0],  localData.gyro[1],  localData.gyro[2],
        // meta — FIX Bug #4: keduanya Volt
        rxData.batteryVoltage,        // bL = Volt dari slave ✓
        localData.batteryVoltage,     // bR = Volt dari master (sudah dikonversi) ✓
        slaveOk ? 1 : 0,
        localData.timestamp
    );

    if (len > 0 && len < (int)sizeof(json)) {
        tcpClient.println(json);
    }
}

// ==================== SYNC ESP-NOW CHANNEL ====================
void syncESPNowChannel() {
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(false);
    delay(50);
}

// ==================== BROADCAST CHANNEL INFO ====================
void broadcastChannelInfo() {
    channel_info chInfo;
    chInfo.channel = currentChannel;
    strcpy(chInfo.identifier, "MASTER_CH");
    esp_now_send(broadcastAddress, (uint8_t *)&chInfo, sizeof(chInfo));
}

// ==================== CHECK & RETRY WIFI ====================
void checkAndRetryWiFi() {
    if (WiFi.status() == WL_CONNECTED) {
        if (!wifiConnected) {
            wifiConnected  = true;
            wifiRetryDelay = 5000;
            uint8_t newCh  = WiFi.channel();
            if (newCh != currentChannel) {
                currentChannel = newCh;
                syncESPNowChannel();
            }
            Serial.printf("[WiFi] Reconnected! IP: %s\n",
                          WiFi.localIP().toString().c_str());
        } else {
            static unsigned long lastChCheck = 0;
            if (millis() - lastChCheck >= 10000) {
                uint8_t newCh = WiFi.channel();
                if (newCh != currentChannel) {
                    currentChannel = newCh;
                    syncESPNowChannel();
                }
                lastChCheck = millis();
            }
        }
    } else {
        if (wifiConnected) {
            wifiConnected = false;
            tcpConnected  = false;
            tcpClient.stop();
            Serial.println("[WiFi] Disconnected!");
        }
        if (millis() - lastWiFiAttempt >= wifiRetryDelay) {
            lastWiFiAttempt = millis();
            Serial.printf("[WiFi] Retrying '%s'...\n", HOTSPOT_SSID);
            WiFi.begin(HOTSPOT_SSID, HOTSPOT_PASSWORD);
            int att = 0;
            while (WiFi.status() != WL_CONNECTED && att < 20) {
                delay(500); att++;
            }
            if (WiFi.status() == WL_CONNECTED) {
                wifiConnected  = true;
                wifiRetryDelay = 5000;
                currentChannel = WiFi.channel();
                syncESPNowChannel();
                Serial.println("[WiFi] Reconnected!");
            } else {
                if (wifiRetryDelay < 30000) wifiRetryDelay *= 2;
            }
        }
    }
}

// ==================== CHECK & RETRY TCP ====================
void checkAndRetryTCP() {
    if (tcpClient.connected()) {
        if (!tcpConnected) {
            tcpConnected = true;
            Serial.printf("[TCP] Connected ke Android %s:%d\n", ANDROID_IP, TCP_PORT);
        }
        return;
    }

    if (tcpConnected) {
        tcpConnected = false;
        tcpClient.stop();
        Serial.println("[TCP] Disconnected dari Android");
    }

    if (millis() - lastTCPAttempt >= tcpRetryDelay) {
        lastTCPAttempt = millis();
        if (tcpClient.connect(ANDROID_IP, TCP_PORT)) {
            tcpConnected  = true;
            tcpRetryDelay = 2000;
            Serial.println("[TCP] Connected! Streaming ke Android...");
        } else {
            if (tcpRetryDelay < 15000) tcpRetryDelay += 1000;
        }
    }
}

// ==================== CONTROL LED ====================
void controlLED() {
    unsigned long now = millis();
    bool slaveOk = slaveConnected && (millis() - lastDataReceived < 2000);

    if (!wifiConnected) {
        if (now - lastLedBlink >= 1000) { lastLedBlink = now; digitalWrite(LED_PIN, !digitalRead(LED_PIN)); }
    } else if (!tcpConnected) {
        if (now - lastLedBlink >= 300)  { lastLedBlink = now; digitalWrite(LED_PIN, !digitalRead(LED_PIN)); }
    } else if (!slaveOk) {
        if (now - lastLedBlink >= 700)  { lastLedBlink = now; digitalWrite(LED_PIN, !digitalRead(LED_PIN)); }
    } else {
        digitalWrite(LED_PIN, LOW);
    }
}

// ==================== PRINT STATUS ====================
void printStatus() {
    bool slaveOk = slaveConnected && (millis() - lastDataReceived < 2000);
    Serial.println("\n--- STATUS ---");
    Serial.printf("WiFi  : %s | Ch: %d\n",
                  wifiConnected ? WiFi.localIP().toString().c_str() : "DISCONNECTED",
                  currentChannel);
    Serial.printf("TCP   : %s | Target: %s:%d\n",
                  tcpConnected ? "STREAMING" : "NOT CONNECTED", ANDROID_IP, TCP_PORT);
    Serial.printf("Slave : %s | Last recv: %lums ago\n",
                  slaveOk ? "OK" : "WAITING", millis() - lastDataReceived);
    Serial.printf("Flex R: %4d %4d %4d %4d %4d (raw ADC)\n",
                  (int)localData.flex[0], (int)localData.flex[1], (int)localData.flex[2],
                  (int)localData.flex[3], (int)localData.flex[4]);
    Serial.printf("Flex L: %4d %4d %4d %4d %4d (raw ADC)\n",
                  (int)rxData.flex[0], (int)rxData.flex[1], (int)rxData.flex[2],
                  (int)rxData.flex[3], (int)rxData.flex[4]);
    Serial.println("--------------\n");
}
