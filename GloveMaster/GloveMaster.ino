/*
 * SMART GLOVE - ESP32-S3 MASTER (Tangan Kanan) FIKS
 * FIX: MPU6050 baca langsung via Wire (tanpa library MPU6050)
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>

// ==================== WIFI CONFIG ====================
const char *ssid = "RANGGA12";
const char *password = "1rangga19%1";

IPAddress targetIP(192, 168, 18, 183);
const int udpPort = 5000;
WiFiUDP udp;

// ==================== DATA STRUCTURE ====================
typedef struct struct_message
{
    float flex[5];
    float accel[3];
    float gyro[3];
    float batteryVoltage;
    int batteryPercentage;
    unsigned long timestamp;
} struct_message;

typedef struct channel_info
{
    uint8_t channel;
    char identifier[10];
} channel_info;

struct_message rxData;
struct_message localData;

// ==================== PIN CONFIGURATION ====================
const int FLEX_PIN_1 = 1;
const int FLEX_PIN_2 = 2;
const int FLEX_PIN_3 = 3;
const int FLEX_PIN_4 = 4;
const int FLEX_PIN_5 = 5;
const int SDA_PIN = 9;
const int SCL_PIN = 8;
const int VBAT_PIN = 7;
const int LED_PIN = 6;

// ==================== MPU6050 RAW (tanpa library) ====================
const uint8_t MPU_ADDR = 0x68;

void mpuWrite(uint8_t reg, uint8_t val)
{
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

void mpuRead(uint8_t reg, uint8_t *buf, uint8_t len)
{
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU_ADDR, len);
    for (uint8_t i = 0; i < len; i++)
        buf[i] = Wire.read();
}

bool mpuInit()
{
    // Bangunkan dari sleep mode
    mpuWrite(0x6B, 0x00);
    delay(100);
    // Accel ±2g, Gyro ±250°/s
    mpuWrite(0x1C, 0x00);
    mpuWrite(0x1B, 0x00);
    // Verifikasi WHO_AM_I
    uint8_t who = 0;
    mpuRead(0x75, &who, 1);
    return (who == 0x68);
}

void mpuGetMotion6(int16_t *ax, int16_t *ay, int16_t *az,
                   int16_t *gx, int16_t *gy, int16_t *gz)
{
    uint8_t buf[14];
    mpuRead(0x3B, buf, 14);
    *ax = (buf[0] << 8) | buf[1];
    *ay = (buf[2] << 8) | buf[3];
    *az = (buf[4] << 8) | buf[5];
    *gx = (buf[8] << 8) | buf[9];
    *gy = (buf[10] << 8) | buf[11];
    *gz = (buf[12] << 8) | buf[13];
}

// ==================== BATTERY CALIBRATION ====================
const float VOLTAGE_DIVIDER_RATIO = 2.0;
const float ADC_REFERENCE = 3.3;
const float ADC_RESOLUTION = 4095.0;
const float BATTERY_MAX = 4.2;
const float BATTERY_MIN = 3.0;
const float BATTERY_LOW = 3.3;

// ==================== STATE ====================
unsigned long lastDataReceived = 0;
unsigned long lastPrint = 0;
unsigned long lastBatteryCheck = 0;
unsigned long lastUDPSend = 0;
unsigned long lastWiFiAttempt = 0;
unsigned long lastChannelBroadcast = 0;
unsigned long wifiRetryDelay = 5000;
unsigned long bootTime = 0;
bool slaveConnected = false;
bool wifiConnected = false;
uint8_t currentChannel = 1;

uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// ==================== FORWARD DECLARATIONS ====================
void checkAndRetryWiFi();
void readLocalSensors();
void controlLED();
void sendUDPData();
void readBattery();
void checkBatteryStatus();
void printCombinedData();
void printBatteryBar(int percentage);
void broadcastChannelInfo();
void syncESPNowChannel();

// ==================== ESP-NOW CALLBACK ====================
void OnDataRecv(const esp_now_recv_info *info,
                const uint8_t *incomingData, int len)
{
    memcpy(&rxData, incomingData, sizeof(rxData));
    lastDataReceived = millis();
    slaveConnected = true;

    Serial.printf("RECV FROM SLAVE [%02X:%02X:%02X:%02X:%02X:%02X] -> ",
                  info->src_addr[0], info->src_addr[1], info->src_addr[2],
                  info->src_addr[3], info->src_addr[4], info->src_addr[5]);

    Serial.print("Flex: ");
    for (int i = 0; i < 5; i++)
    {
        Serial.print(rxData.flex[i], 2);
        if (i < 4)
            Serial.print(",");
    }
    Serial.printf(" | Bat: %.2fV (%d%%)\n",
                  rxData.batteryVoltage, rxData.batteryPercentage);
}

// ==================== SETUP ====================
void setup()
{
    Serial.begin(115200);
    delay(5000);

    Serial.println("\n=====================================");
    Serial.println("   SMART GLOVE MASTER - BOOTING");
    Serial.println("=====================================");

    // LED
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);
    Serial.println("[1/9] LED OK");

    // WiFi
    Serial.println("[2/9] Connecting WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20)
    {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED)
    {
        wifiConnected = true;
        currentChannel = WiFi.channel();
        udp.begin(udpPort);
        Serial.printf("[2/9] WiFi OK — IP: %s  Ch: %d\n",
                      WiFi.localIP().toString().c_str(), currentChannel);
    }
    else
    {
        Serial.println("[2/9] WiFi FAILED — will retry in loop");
    }

    Serial.printf("[3/9] MAC: %s\n", WiFi.macAddress().c_str());

    // ESP-NOW
    Serial.println("[4/9] ESP-NOW init...");
    if (esp_now_init() != ESP_OK)
    {
        Serial.println("ERROR: ESP-NOW init failed!");
        return;
    }
    esp_now_register_recv_cb(OnDataRecv);

    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, broadcastAddress, 6);
    peerInfo.channel = 0;
    peerInfo.encrypt = false;
    esp_now_add_peer(&peerInfo);
    Serial.println("[4/9] ESP-NOW OK");

    syncESPNowChannel();
    Serial.printf("[5/9] ESP-NOW channel synced to %d\n", currentChannel);

    // I2C + MPU6050 (tanpa library)
    Serial.println("[6/9] I2C + MPU6050 init...");
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);
    delay(200);

    if (mpuInit())
    {
        Serial.println("[6/9] MPU6050 OK");
    }
    else
    {
        Serial.println("[6/9] WARNING: MPU6050 tidak terdeteksi — cek kabel!");
    }

    // ADC
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);
    Serial.println("[7/9] ADC OK");

    Serial.println("\n========================================");
    Serial.println("        SYSTEM READY");
    Serial.printf("        Channel: %d\n", currentChannel);
    Serial.println("========================================\n");

    bootTime = millis();
    delay(2000);
}

// ==================== LOOP ====================
void loop()
{
    checkAndRetryWiFi();

    if (millis() - lastChannelBroadcast >= 2000)
    {
        broadcastChannelInfo();
        lastChannelBroadcast = millis();
    }

    readLocalSensors();
    controlLED();

    if (wifiConnected && slaveConnected && (millis() - lastDataReceived < 2000))
    {
        if (millis() - lastUDPSend >= 20)
        {
            sendUDPData();
            lastUDPSend = millis();
        }
    }
    else
    {
        static unsigned long lastDebug = 0;
        if (millis() - lastDebug > 5000 && bootTime > 0)
        {
            if (!wifiConnected)
                Serial.println("DEBUG: WiFi not connected");
            if (!slaveConnected)
                Serial.println("DEBUG: Slave not connected");
            if (millis() - lastDataReceived > 2000)
                Serial.println("DEBUG: No slave data");
            lastDebug = millis();
        }
    }

    if (millis() - bootTime > 15000 && millis() - lastPrint >= 1000)
    {
        printCombinedData();
        lastPrint = millis();
    }

    if (millis() - lastBatteryCheck >= 10000)
    {
        checkBatteryStatus();
        lastBatteryCheck = millis();
    }

    delay(20);
}

// ==================== SYNC ESP-NOW CHANNEL ====================
void syncESPNowChannel()
{
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(false);
    delay(50);
}

// ==================== BROADCAST CHANNEL INFO ====================
void broadcastChannelInfo()
{
    channel_info chInfo;
    chInfo.channel = currentChannel;
    strcpy(chInfo.identifier, "MASTER_CH");
    esp_now_send(broadcastAddress, (uint8_t *)&chInfo, sizeof(chInfo));
}

// ==================== CHECK AND RETRY WIFI ====================
void checkAndRetryWiFi()
{
    if (WiFi.status() == WL_CONNECTED)
    {
        if (!wifiConnected)
        {
            wifiConnected = true;
            wifiRetryDelay = 5000;
            uint8_t newCh = WiFi.channel();
            if (newCh != currentChannel)
            {
                currentChannel = newCh;
                syncESPNowChannel();
            }
            udp.stop();
            udp.begin(udpPort);
            Serial.printf("WiFi RECONNECTED — IP: %s  Ch: %d\n",
                          WiFi.localIP().toString().c_str(), currentChannel);
        }
        else
        {
            static unsigned long lastChCheck = 0;
            if (millis() - lastChCheck >= 10000)
            {
                uint8_t newCh = WiFi.channel();
                if (newCh != currentChannel)
                {
                    currentChannel = newCh;
                    syncESPNowChannel();
                    Serial.printf("Channel changed -> %d\n", currentChannel);
                }
                lastChCheck = millis();
            }
        }
    }
    else
    {
        if (wifiConnected)
        {
            wifiConnected = false;
            Serial.println("WiFi DISCONNECTED");
        }
        if (millis() - lastWiFiAttempt >= wifiRetryDelay)
        {
            lastWiFiAttempt = millis();
            WiFi.begin(ssid, password);
            int att = 0;
            while (WiFi.status() != WL_CONNECTED && att < 10)
            {
                delay(500);
                att++;
            }
            if (WiFi.status() == WL_CONNECTED)
            {
                wifiConnected = true;
                wifiRetryDelay = 5000;
                currentChannel = WiFi.channel();
                syncESPNowChannel();
                udp.begin(udpPort);
                Serial.println("WiFi reconnected!");
            }
            else
            {
                if (wifiRetryDelay < 30000)
                    wifiRetryDelay *= 2;
            }
        }
    }
}

// ==================== SEND UDP DATA ====================
void sendUDPData()
{
    String d = "DATA";
    d += "|F:";
    for (int i = 0; i < 5; i++)
    {
        d += String(rxData.flex[i], 3);
        if (i < 4)
            d += ",";
    }
    d += "|A:" + String(rxData.accel[0], 3) + "," + String(rxData.accel[1], 3) + "," + String(rxData.accel[2], 3);
    d += "|G:" + String(rxData.gyro[0], 3) + "," + String(rxData.gyro[1], 3) + "," + String(rxData.gyro[2], 3);
    d += "|F:";
    for (int i = 0; i < 5; i++)
    {
        d += String(localData.flex[i], 3);
        if (i < 4)
            d += ",";
    }
    d += "|A:" + String(localData.accel[0], 3) + "," + String(localData.accel[1], 3) + "," + String(localData.accel[2], 3);
    d += "|G:" + String(localData.gyro[0], 3) + "," + String(localData.gyro[1], 3) + "," + String(localData.gyro[2], 3);
    d += "|BAT:" + String(rxData.batteryVoltage, 2) + "," + String(localData.batteryVoltage, 2);

    if (udp.beginPacket(targetIP, udpPort))
    {
        udp.print(d);
        udp.endPacket();
    }
}

// ==================== CONTROL LED ====================
void controlLED()
{
    bool conn = (lastDataReceived > 0) && (millis() - lastDataReceived < 2000);
    if (conn)
    {
        digitalWrite(LED_PIN, ((rxData.timestamp / 500) % 2) == 0 ? LOW : HIGH);
    }
    else
    {
        digitalWrite(LED_PIN, HIGH);
    }
}

// ==================== READ LOCAL SENSORS ====================
void readLocalSensors()
{
    localData.timestamp = millis();

    // Send raw ADC values (0-4095), will be normalized in Python during calibration
    localData.flex[0] = (float)analogRead(FLEX_PIN_1);
    localData.flex[1] = (float)analogRead(FLEX_PIN_2);
    localData.flex[2] = (float)analogRead(FLEX_PIN_3);
    localData.flex[3] = (float)analogRead(FLEX_PIN_4);
    localData.flex[4] = (float)analogRead(FLEX_PIN_5);

    int16_t ax, ay, az, gx, gy, gz;
    mpuGetMotion6(&ax, &ay, &az, &gx, &gy, &gz);

    localData.accel[0] = ax / 16384.0;
    localData.accel[1] = ay / 16384.0;
    localData.accel[2] = az / 16384.0;
    localData.gyro[0] = gx / 131.0;
    localData.gyro[1] = gy / 131.0;
    localData.gyro[2] = gz / 131.0;

    readBattery();
}

// ==================== READ BATTERY ====================
void readBattery()
{
    int raw = analogRead(VBAT_PIN);
    localData.batteryVoltage = (raw / ADC_RESOLUTION) * ADC_REFERENCE * VOLTAGE_DIVIDER_RATIO;
    float pct = ((localData.batteryVoltage - BATTERY_MIN) / (BATTERY_MAX - BATTERY_MIN)) * 100.0;
    localData.batteryPercentage = constrain((int)pct, 0, 100);
}

// ==================== CHECK BATTERY ====================
void checkBatteryStatus()
{
    if (localData.batteryVoltage < BATTERY_LOW)
        Serial.printf("WARNING: RIGHT Battery LOW! %.2fV\n", localData.batteryVoltage);
    if (millis() - lastDataReceived < 2000 && rxData.batteryVoltage < BATTERY_LOW)
        Serial.printf("WARNING: LEFT Battery LOW! %.2fV\n", rxData.batteryVoltage);
}

// ==================== PRINT COMBINED DATA ====================
void printCombinedData()
{
    Serial.println("\n========================================");
    Serial.println("       COMBINED SENSOR DATA");
    Serial.println("========================================");
    Serial.printf("WiFi: %s  Ch:%d\n",
                  wifiConnected ? WiFi.localIP().toString().c_str() : "DISCONNECTED",
                  currentChannel);

    Serial.println("\n--- LEFT HAND (Slave) ---");
    if (lastDataReceived == 0)
    {
        Serial.println("Status: WAITING...");
    }
    else if (millis() - lastDataReceived > 2000)
    {
        Serial.println("Status: LOST");
    }
    else
    {
        Serial.print("Flex: ");
        for (int i = 0; i < 5; i++)
        {
            Serial.print(rxData.flex[i], 3);
            if (i < 4)
                Serial.print(",");
        }
        Serial.printf("\nBat: %.2fV (%d%%) ", rxData.batteryVoltage, rxData.batteryPercentage);
        printBatteryBar(rxData.batteryPercentage);
        Serial.println();
    }

    Serial.println("\n--- RIGHT HAND (Master) ---");
    Serial.print("Flex: ");
    for (int i = 0; i < 5; i++)
    {
        Serial.print(localData.flex[i], 3);
        if (i < 4)
            Serial.print(",");
    }
    Serial.printf("\nBat: %.2fV (%d%%) ", localData.batteryVoltage, localData.batteryPercentage);
    printBatteryBar(localData.batteryPercentage);
    Serial.println("\n========================================\n");
}

// ==================== BATTERY BAR ====================
void printBatteryBar(int p)
{
    Serial.print("[");
    Serial.print(p > 80 ? "#####" : p > 60 ? "#### "
                                : p > 40   ? "###  "
                                : p > 20   ? "##   "
                                           : "#    ");
    Serial.print("]");
}
