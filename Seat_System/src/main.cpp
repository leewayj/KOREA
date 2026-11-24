#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "HX711.h"
#include "secrets.h"

// ==================== [1. 설정 영역] ====================
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

const char* serverGetUrl = SERVER_GET_URL;
const char* serverPostUrl = SERVER_POST_URL;

// 핀 설정
const int LOADCELL_DOUT_PIN = 21;
const int LOADCELL_SCK_PIN = 22;
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;

HX711 scale;

// 착석·비착석 임계값 (히스테리시스)
const long OCCUPIED_THRESHOLD = 200000; // 2kg 이상 -> 착석 판정
const long EMPTY_THRESHOLD = 150000;    // 1.5kg 이하 -> 비착석 후보

// 앉은 채 의자를 들었다 놓는 동작 방어 (이석 유예 시간)
const unsigned long LEAVE_DEBOUNCE_MS = 3000; // 3초 이상 무게가 빠져야 실제 이석 인정

// 의자 넘어짐(전도) 및 비정상 하중 감지 기준
const long TILT_NEGATIVE_LIMIT = -120000;     // 이보다 큰 음수가 지속되면 의자 넘어짐/뒤틀림 판정
const long OVERLOAD_LIMIT = 2000000;          // 비정상 과하중 한계
const unsigned long ABNORMAL_HOLD_MS = 3000;  // 3초 이상 비정상 값 지속 시 전도/이상 판정

// 자동 영점(Auto-Tare) 설정 (실측 노이즈 -7,300 ~ +33,000 반영)
const long AUTO_TARE_MAX_OFFSET = 130000;     // 빈 의자 위치 변화 오차 허용 상한
const long AUTO_TARE_MIN_DRIFT = 45000;       // ±45,000 이상 영점이 틀어졌을 때만 재보정 (평소 노이즈 무시)
const long STABILITY_TOLERANCE = 15000;       // 센서 기본 노이즈 출렁임을 감안한 안정 허용 오차
const unsigned long AUTO_TARE_WAIT_MS = 4000; // 안정 상태 4초 유지 시 자동 영점

// 통신/센서 오류 판단 기준
const unsigned long SERVER_TIMEOUT_MS = 15000;
const unsigned long SENSOR_TIMEOUT_MS = 3000;

// LED 출력 모드 정의
enum LedMode {
    LED_OFF,
    LED_BLUE_ON,
    LED_ORANGE_ON,
    LED_RED_BLINK
};

LedMode currentLedMode = LED_OFF;

// 서버 및 센서 상태 변수
String serverSeatStatus = "UNKNOWN";
String serverTargetLed = "OFF";
bool isOccupied = false;

// 오류 및 초기화 추적 변수
bool hasServerSynced = false;
bool hasValidSensor = false;
bool isServerError = false;
bool isSensorError = false;
bool isChairFallen = false; // 의자 넘어짐 상태 플래그
unsigned long lastServerOkMillis = 0;
unsigned long lastSensorOkMillis = 0;

// 필터 및 추적 타이머 변수
unsigned long leaveCandidateStartMillis = 0;
bool isLeavePending = false;

unsigned long abnormalStartMillis = 0;
bool isAbnormalPending = false;

long prevReading = 0;
unsigned long stableStartMillis = 0;
bool isTrackingStability = false;

// 주기 타이머 변수
unsigned long previousBlinkMillis = 0;
unsigned long previousServerMillis = 0;
unsigned long previousSensorMillis = 0;
unsigned long previousWifiCheckMillis = 0;
bool blinkState = false;
// ========================================================

void setColor(int r, int g, int b) {
    analogWrite(RED_PIN, r);
    analogWrite(GREEN_PIN, g);
    analogWrite(BLUE_PIN, b);
}

void updateLED() {
    switch (currentLedMode) {
        case LED_OFF:
            setColor(0, 0, 0);
            break;
        case LED_BLUE_ON:
            setColor(0, 0, 255);
            break;
        case LED_ORANGE_ON:
            setColor(255, 80, 0);
            break;
        case LED_RED_BLINK:
            if (millis() - previousBlinkMillis >= 500) {
                previousBlinkMillis = millis();
                blinkState = !blinkState;
                if (blinkState) setColor(255, 0, 0);
                else setColor(0, 0, 0);
            }
            break;
    }
}

String ledModeToString(LedMode mode) {
    switch (mode) {
        case LED_BLUE_ON:   return "BLUE_ON";
        case LED_ORANGE_ON: return "ORANGE_ON";
        case LED_RED_BLINK: return "RED_BLINK";
        default:            return "OFF";
    }
}

void setup() {
    Serial.begin(115200);

    pinMode(RED_PIN, OUTPUT);
    pinMode(GREEN_PIN, OUTPUT);
    pinMode(BLUE_PIN, OUTPUT);
    setColor(0, 0, 0);

    scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
    scale.tare();

    Serial.println();
    Serial.print("WiFi 연결 중: ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    unsigned long wifiStartAttempt = millis();

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (millis() - wifiStartAttempt >= 5000) {
            wifiStartAttempt = millis();
            Serial.println("\n>>> 첫 Wi-Fi 연결 재시도 중...");
            WiFi.disconnect();
            WiFi.begin(ssid, password);
        }
    }

    Serial.println("\nWiFi 연결 성공!");
    Serial.print("ESP32 IP 주소: ");
    Serial.println(WiFi.localIP());

    lastServerOkMillis = millis();
    lastSensorOkMillis = millis();
}

void loop() {
    // 0. Wi-Fi 재연결 감시
    if (WiFi.status() != WL_CONNECTED) {
        if (millis() - previousWifiCheckMillis >= 5000) {
            previousWifiCheckMillis = millis();
            Serial.println(">>> Wi-Fi 끊김 감지! 재연결 시도 중...");
            WiFi.disconnect();
            WiFi.begin(ssid, password);
        }
    }

    // 1. 수동 영점 조절 ('t')
    if (Serial.available() > 0) {
        char cmd = Serial.read();
        if (cmd == 't') {
            scale.tare();
            isTrackingStability = false;
            isChairFallen = false;
            Serial.println(">>> [수동 영점 완료] 무게가 0으로 초기화되었습니다.");
        }
    }

    // 2. [서버 상태 조회] 2초마다 실행 (GET)
    if (millis() - previousServerMillis >= 2000) {
        previousServerMillis = millis();

        if (WiFi.status() == WL_CONNECTED) {
            WiFiClientSecure client;
            client.setInsecure();

            HTTPClient http;
            http.setTimeout(10000);
            http.begin(client, serverGetUrl);
            int httpResponseCode = http.GET();

            if (httpResponseCode == 200) {
                String payload = http.getString();
                JsonDocument doc;
                DeserializationError error = deserializeJson(doc, payload);

                if (!error) {
                    serverSeatStatus = doc["seat_status"] | "UNKNOWN";

                    if (doc["target_led"].isNull() || !doc["target_led"].is<const char*>()) {
                        serverTargetLed = "OFF";
                    } else {
                        String rawLed = doc["target_led"].as<String>();
                        if (rawLed == "OFF" || rawLed == "BLUE_ON" || rawLed == "ORANGE_ON" || rawLed == "RED_BLINK") {
                            serverTargetLed = rawLed;
                        } else {
                            serverTargetLed = "OFF";
                        }
                    }

                    hasServerSynced = true;
                    isServerError = false;
                    lastServerOkMillis = millis();
                }
            } else {
                Serial.printf(">>> 서버 GET 에러 코드: HTTP %d\n", httpResponseCode);
            }
            http.end();
        }

        if (millis() - lastServerOkMillis > SERVER_TIMEOUT_MS) {
            isServerError = true;
        }
    }

    // 3. [무게 측정 + 들썩임 필터 + 의자 넘어짐 감지 + 자동 영점] 1초마다 실행 (POST)
    if (millis() - previousSensorMillis >= 1000) {
        previousSensorMillis = millis();
        long reading = 0;

        if (scale.is_ready()) {
            reading = scale.get_units(5) * -1;
            hasValidSensor = true;
            isSensorError = false;
            lastSensorOkMillis = millis();

            // [A] 의자 넘어짐(전도) 및 비정상 극단값 감시
            if (reading < TILT_NEGATIVE_LIMIT || reading > OVERLOAD_LIMIT) {
                if (!isAbnormalPending) {
                    isAbnormalPending = true;
                    abnormalStartMillis = millis();
                } else if (millis() - abnormalStartMillis >= ABNORMAL_HOLD_MS) {
                    if (!isChairFallen) {
                        Serial.println(">>> [경고] 의자 넘어짐 또는 비정상 하중 감지! (자동 영점 중단)");
                    }
                    isChairFallen = true;
                    isOccupied = false;
                    isLeavePending = false;
                }
            } else {
                isAbnormalPending = false;
                if (isChairFallen) {
                    Serial.println(">>> [복구] 의자가 정상 위치로 복구되었습니다.");
                }
                isChairFallen = false;
            }

            // [B] 정상 상태일 때 착석 판정 (앉은 채 의자 들썩임 방어 포함)
            if (!isChairFallen) {
                if (reading >= OCCUPIED_THRESHOLD) {
                    isOccupied = true;
                    isLeavePending = false; // 다시 하중이 실리면 이석 유예 취소
                } else if (reading <= EMPTY_THRESHOLD) {
                    if (isOccupied) {
                        // 이미 착석 중이었다면 3초간 하중 감소가 유지되는지 대기
                        if (!isLeavePending) {
                            isLeavePending = true;
                            leaveCandidateStartMillis = millis();
                        } else if (millis() - leaveCandidateStartMillis >= LEAVE_DEBOUNCE_MS) {
                            isOccupied = false;
                            isLeavePending = false;
                        }
                    } else {
                        isOccupied = false;
                        isLeavePending = false;
                    }
                }
            }

            // [C] 자동 영점(Auto-Tare): 넘어지지 않았고, 비착석이며, 미세 오차 범위 내 안정화 시 실행
            if (!isChairFallen && !isOccupied && !isLeavePending &&
                abs(reading) < AUTO_TARE_MAX_OFFSET && abs(reading) > AUTO_TARE_MIN_DRIFT) {
                if (abs(reading - prevReading) < STABILITY_TOLERANCE) {
                    if (!isTrackingStability) {
                        isTrackingStability = true;
                        stableStartMillis = millis();
                    } else if (millis() - stableStartMillis >= AUTO_TARE_WAIT_MS) {
                        scale.tare();
                        reading = 0;
                        isTrackingStability = false;
                        Serial.println(">>> [자동 영점 완료] 빈 의자 위치 변화 안정화 -> 0점 재보정!");
                    }
                } else {
                    isTrackingStability = false;
                }
            } else {
                isTrackingStability = false;
            }
            prevReading = reading;

        } else {
            if (millis() - lastSensorOkMillis > SENSOR_TIMEOUT_MS) {
                isSensorError = true;
            }
        }

        // [D] 최종 LED 결정 (센서 오류 또는 의자 넘어짐 시 안전 소등)
        String displayStatus = serverSeatStatus;

        if (!hasServerSynced || isServerError || !hasValidSensor || isSensorError || isChairFallen) {
            currentLedMode = LED_OFF;
            displayStatus = isChairFallen ? "CHAIR_FALLEN" : "UNKNOWN";
        }
        else if (serverTargetLed == "BLUE_ON") {
            currentLedMode = LED_BLUE_ON;
        }
        else if (serverTargetLed == "ORANGE_ON") {
            currentLedMode = LED_ORANGE_ON;
        }
        else if (serverTargetLed == "RED_BLINK") {
            currentLedMode = LED_RED_BLINK;
        }
        else {
            currentLedMode = LED_OFF;
        }

        updateLED();

        // [E] 서버로 센서/LED 상태 회신 (의자 넘어짐 시 SENSOR_ERROR로 보고)
        if (WiFi.status() == WL_CONNECTED && (hasValidSensor || isSensorError)) {
            WiFiClientSecure client;
            client.setInsecure();

            HTTPClient http;
            http.setTimeout(10000);
            http.begin(client, serverPostUrl);
            http.addHeader("Content-Type", "application/json");

            String sensorStateStr = (isSensorError || isChairFallen)
                ? "SENSOR_ERROR"
                : (isOccupied ? "OCCUPIED" : "EMPTY");

            JsonDocument postDoc;
            postDoc["state"] = sensorStateStr;
            postDoc["led_state"] = ledModeToString(currentLedMode);

            String httpRequestData;
            serializeJson(postDoc, httpRequestData);

            int postCode = http.POST(httpRequestData);
            if (postCode != 200) {
                Serial.printf(">>> 센서/LED 회신 POST 에러: HTTP %d\n", postCode);
            }
            http.end();
        }

        // 시리얼 모니터 출력
        Serial.print("무게: ");
        Serial.print(reading);
        Serial.print(" | 착석: ");
        Serial.print(isChairFallen ? "FALLEN(전도)" : (isOccupied ? "OCCUPIED" : "EMPTY"));
        Serial.print(" | 서버상태: ");
        Serial.print(displayStatus);
        Serial.print(" | 적용LED: ");
        Serial.println(ledModeToString(currentLedMode));
    }

    updateLED();
}