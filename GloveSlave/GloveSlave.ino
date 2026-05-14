/*
 * SMART GLOVE - ESP32-S3 SLAVE (Tangan Kiri) FIKS
 * FIX: MPU6050 baca langsung via Wire (tanpa library MPU6050)
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>

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

struct_message dataSend;

// ==================== MAC MASTER ====================
uint8_t masterAddress[] = {0x9C, 0x13, 0x9E, 0xF4, 0x11, 0x04};

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
    mpuWrite(0x6B, 0x00); // bangunkan dari sleep
    delay(100);
    mpuWrite(0x1C, 0x00); // accel ±2g
    mpuWrite(0x1B, 0x00); // gyro ±250°/s
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
unsigned long lastSuccessSend = 0;
unsigned long lastBatteryWarning = 0;
unsigned long lastChannelSync = 0;
unsigned long lastChannelScan = 0;
bool lastSendSuccess = false;
int consecutiveFailures = 0;
uint8_t currentChannel = 1;
uint8_t masterChannel = 0;
bool channelSynced = false;

// ==================== FORWARD DECLARATIONS ====================
void scanForMaster();
void syncToChannel(uint8_t channel);
void readAllSensors();
void readBattery();
void controlLED();
void checkBatteryWarning();
void printSensorData();
void printBatteryBar(int percentage);

// ==================== CALLBACKS ====================
void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status)
{
    if (status == ESP_NOW_SEND_SUCCESS)
    {
        Serial.println("SEND: OK");
        lastSendSuccess = true;
        lastSuccessSend = millis();
        consecutiveFailures = 0;
        channelSynced = true;
    }
    else
    {
        Serial.println("SEND: FAILED");
        lastSendSuccess = false;
        consecutiveFailures++;
        if (consecutiveFailures >= 5)
        {
            Serial.println("WARNING: 5x gagal — re-scan channel...");
            channelSynced = false;
        }
    }
}

void OnDataRecv(const esp_now_recv_info *info,
                const uint8_t *incomingData, int len)
{
    if (len == sizeof(channel_info))
    {
        channel_info chInfo;
        memcpy(&chInfo, incomingData, sizeof(chInfo));
        if (strcmp(chInfo.identifier, "MASTER_CH") == 0)
        {
            masterChannel = chInfo.channel;
            if (chInfo.channel != currentChannel)
            {
                Serial.printf(">>> Master channel: %d — switching...\n", chInfo.channel);
                syncToChannel(chInfo.channel);
            }
            else
            {
                channelSynced = true;
            }
            lastChannelSync = millis();
        }
    }
}

// ==================== SETUP ====================
void setup()
{
    Serial.begin(115200);
    delay(3000);

    Serial.println("\n========================================");
    Serial.println("   SMART GLOVE SLAVE - LEFT HAND");
    Serial.println("========================================");

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);

    WiFi.mode(WIFI_STA);
    Serial.printf("MAC SLAVE: %s\n", WiFi.macAddress().c_str());

    if (esp_now_init() != ESP_OK)
    {
        Serial.println("ERROR: ESP-NOW init failed!");
        return;
    }
    esp_now_register_send_cb(OnDataSent);
    esp_now_register_recv_cb(OnDataRecv);

    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, masterAddress, 6);
    peerInfo.channel = 0;
    peerInfo.encrypt = false;
    if (esp_now_add_peer(&peerInfo) != ESP_OK)
    {
        Serial.println("ERROR: Failed to add peer!");
        return;
    }

    Serial.print("Target Master: ");
    for (int i = 0; i < 6; i++)
    {
        Serial.printf("%02X", masterAddress[i]);
        if (i < 5)
            Serial.print(":");
    }
    Serial.println();

    // I2C + MPU6050 (tanpa library)
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);
    delay(200);

    if (mpuInit())
    {
        Serial.println("MPU6050 OK");
    }
    else
    {
        Serial.println("WARNING: MPU6050 tidak terdeteksi — cek kabel!");
    }

    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    Serial.println("\n========================================");
    Serial.println("        SYSTEM READY");
    Serial.println("  Scanning for Master channel...");
    Serial.println("========================================\n");

    scanForMaster();
}

// ==================== LOOP ====================
void loop()
{
    // Re-scan jika belum sync atau lama tidak dapat broadcast
    if (!channelSynced || (millis() - lastChannelSync > 10000))
    {
        if (millis() - lastChannelScan >= 5000)
        {
            Serial.println(">>> Re-scanning for Master...");
            scanForMaster();
            lastChannelScan = millis();
        }
    }

    dataSend.timestamp = millis();
    readAllSensors();

    esp_err_t result = esp_now_send(masterAddress, (uint8_t *)&dataSend, sizeof(dataSend));
    if (result != ESP_OK)
        Serial.printf("ERROR: Send code %d\n", result);

    printSensorData();
    controlLED();
    checkBatteryWarning();

    delay(50);
}

// ==================== SCAN FOR MASTER ====================
void scanForMaster()
{
    Serial.println("Scanning channels 1-13...");
    for (uint8_t ch = 1; ch <= 13; ch++)
    {
        Serial.printf("  ch%d... ", ch);
        esp_wifi_set_promiscuous(true);
        esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
        esp_wifi_set_promiscuous(false);
        delay(50);
        currentChannel = ch;

        unsigned long t = millis();
        while (millis() - t < 300)
        {
            if (masterChannel == ch)
            {
                Serial.println("FOUND!");
                channelSynced = true;
                Serial.printf("Master on channel %d\n\n", ch);
                return;
            }
            delay(10);
        }
        Serial.println("not found");
    }
    Serial.println("Master not found — using ch1 default");
    syncToChannel(1);
}

// ==================== SYNC TO CHANNEL ====================
void syncToChannel(uint8_t channel)
{
    if (channel == currentChannel && channelSynced)
        return;
    currentChannel = channel;
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(false);
    delay(50);
    channelSynced = true;
    lastChannelSync = millis();
    Serial.printf(">>> Switched to channel %d\n", currentChannel);
}

// ==================== CONTROL LED ====================
void controlLED()
{
    bool conn = lastSendSuccess && (millis() - lastSuccessSend < 2000);
    if (conn)
    {
        digitalWrite(LED_PIN, ((dataSend.timestamp / 500) % 2) == 0 ? LOW : HIGH);
    }
    else
    {
        digitalWrite(LED_PIN, HIGH);
    }
}

// ==================== READ ALL SENSORS ====================
void readAllSensors()
{
    // Send raw ADC values (0-4095), will be normalized in Python during calibration
    dataSend.flex[0] = (float)analogRead(FLEX_PIN_1);
    dataSend.flex[1] = (float)analogRead(FLEX_PIN_2);
    dataSend.flex[2] = (float)analogRead(FLEX_PIN_3);
    dataSend.flex[3] = (float)analogRead(FLEX_PIN_4);
    dataSend.flex[4] = (float)analogRead(FLEX_PIN_5);

    int16_t ax, ay, az, gx, gy, gz;
    mpuGetMotion6(&ax, &ay, &az, &gx, &gy, &gz);

    dataSend.accel[0] = ax / 16384.0;
    dataSend.accel[1] = ay / 16384.0;
    dataSend.accel[2] = az / 16384.0;
    dataSend.gyro[0] = gx / 131.0;
    dataSend.gyro[1] = gy / 131.0;
    dataSend.gyro[2] = gz / 131.0;

    readBattery();
}

// ==================== READ BATTERY ====================
void readBattery()
{
    int raw = analogRead(VBAT_PIN);
    dataSend.batteryVoltage = (raw / ADC_RESOLUTION) * ADC_REFERENCE * VOLTAGE_DIVIDER_RATIO;
    float pct = ((dataSend.batteryVoltage - BATTERY_MIN) / (BATTERY_MAX - BATTERY_MIN)) * 100.0;
    dataSend.batteryPercentage = constrain((int)pct, 0, 100);
}

// ==================== CHECK BATTERY WARNING ====================
void checkBatteryWarning()
{
    if (dataSend.batteryVoltage < BATTERY_LOW &&
        millis() - lastBatteryWarning > 30000)
    {
        Serial.printf("\nWARNING: Battery LOW! %.2fV (%d%%)\n",
                      dataSend.batteryVoltage, dataSend.batteryPercentage);
        lastBatteryWarning = millis();
    }
}

// ==================== PRINT SENSOR DATA ====================
void printSensorData()
{
    Serial.printf("Ch:%d SEND -> Flex:[", currentChannel);
    for (int i = 0; i < 5; i++)
    {
        Serial.print(dataSend.flex[i], 2);
        if (i < 4)
            Serial.print(",");
    }
    Serial.printf("] Bat:%.2fV(%d%%) ", dataSend.batteryVoltage, dataSend.batteryPercentage);
    printBatteryBar(dataSend.batteryPercentage);
    Serial.println();
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
