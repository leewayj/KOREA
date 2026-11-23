#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "HX711.h"

// ==================== [1. 설정 영역] ====================
const char* ssid = "GalaxyS26+5201";       // 와이파이 이름
const char* password = "11111111";         // 와이파이 비밀번호

// 백엔드 서버 주소 (백엔드 담당자 공유 IP·포트 및 seat_id로 변경)
const char* serverGetUrl = "http://10.44.160.72:8000/seats/1/reservation-info";
const char* serverPostUrl = "http://10.44.160.72:8000/seats/1/occupancy";

// 핀 설정
const int LOADCELL_DOUT_PIN = 21;
const int LOADCELL_SCK_PIN = 22;
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;

HX711 scale;

// 착석·비착석 임계값 (경계값 반복 전환 방지용 히스테리시스)
const long OCCUPIED_THRESHOLD = 200000; // 2kg 이상 -> 착석 판정
const long EMPTY_THRESHOLD = 150000;    // 이 값 이하 -> 비착석 판정

// 통신/센서 오류 판단 기준
const unsigned long SERVER_TIMEOUT_MS = 10000; // 10초 초과 시 통신 오류
const unsigned long SENSOR_TIMEOUT_MS = 3000;  // 3초 초과 시 센서 오류

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
unsigned long lastServerOkMillis = 0;
unsigned long lastSensorOkMillis = 0;

// 타이머 변수
unsigned long previousBlinkMillis = 0;
unsigned long previousServerMillis = 0;
unsigned long previousSensorMillis = 0;
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
            setColor(0, 0, 0);       // 소등
            break;
        case LED_BLUE_ON:
            setColor(0, 0, 255);     // 파란색 점등
            break;
        case LED_ORANGE_ON:
            setColor(255, 80, 0);    // 주황색 점등
            break;
        case LED_RED_BLINK:          // 빨간색 점멸 (0.5초 주기)
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

    // 로드셀 초기화
    scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
    scale.tare();

    // Wi-Fi 연결 시작
    Serial.println();
    Serial.print("WiFi 연결 중: ");
    Serial.println(ssid);

    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\nWiFi 연결 성공!");
    Serial.print("ESP32 IP 주소: ");
    Serial.println(WiFi.localIP());

    lastServerOkMillis = millis();
    lastSensorOkMillis = millis();
}

void loop() {
    // 1. 키보드 입력 처리 ('t' 누르면 영점 조절)
    if (Serial.available() > 0) {
        char cmd = Serial.read();
        if (cmd == 't') {
            scale.tare();
            Serial.println(">>> [영점 완료] 무게가 0으로 초기화되었습니다.");
        }
    }

    // 2. [서버에서 상태 및 목표 LED 받아오기] 2초마다 실행 (GET)
    if (millis() - previousServerMillis >= 2000) {
        previousServerMillis = millis();

        if (WiFi.status() == WL_CONNECTED) {
            HTTPClient http;
            http.setTimeout(1500);
            http.begin(serverGetUrl);
            int httpResponseCode = http.GET();

            if (httpResponseCode == 200) {
                String payload = http.getString();
                JsonDocument doc;
                DeserializationError error = deserializeJson(doc, payload);

                if (!error) {
                    serverSeatStatus = doc["seat_status"] | "UNKNOWN";
                    serverTargetLed = doc["target_led"] | "OFF";

                    hasServerSynced = true;
                    isServerError = false;
                    lastServerOkMillis = millis();
                } else {
                    Serial.println(">>> JSON 해석 오류");
                }
            } else {
                Serial.print(">>> 서버 GET 에러 코드: ");
                Serial.println(httpResponseCode);
            }
            http.end();
        }

        // 서버 응답이 10초 이상 없으면 통신 중단 오류 판정
        if (millis() - lastServerOkMillis > SERVER_TIMEOUT_MS) {
            isServerError = true;
        }
    }

    // 3. [무게 측정 + LED 적용 + 서버로 결과 회신] 1초마다 실행 (POST)
    if (millis() - previousSensorMillis >= 1000) {
        previousSensorMillis = millis();
        long reading = 0;

        if (scale.is_ready()) {
            reading = scale.get_units(5) * -1;
            hasValidSensor = true;
            isSensorError = false;
            lastSensorOkMillis = millis();

            if (reading >= OCCUPIED_THRESHOLD) {
                isOccupied = true;
            } else if (reading <= EMPTY_THRESHOLD) {
                isOccupied = false;
            }
        } else {
            if (millis() - lastSensorOkMillis > SENSOR_TIMEOUT_MS) {
                isSensorError = true;
            }
        }

        // ==================== [최종 LED 결정 (서버 target_led 기준)] ====================
        String displayStatus = serverSeatStatus;

        if (!hasServerSynced || isServerError || !hasValidSensor || isSensorError) {
            // 초기화 중, 센서 오류(3초 초과), 또는 서버 응답 단절(10초 초과) -> 소등
            currentLedMode = LED_OFF;
            displayStatus = "UNKNOWN";
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
            // "OFF" 또는 기타 예외 값 수신 시 소등
            currentLedMode = LED_OFF;
        }
        // ================================================================================

        updateLED();

        // 초기화 중 센서 상태를 아직 확인하지 못했다면 POST 전송 건너뛰기
        if (WiFi.status() == WL_CONNECTED && (hasValidSensor || isSensorError)) {
            HTTPClient http;
            http.setTimeout(1500);
            http.begin(serverPostUrl);
            http.addHeader("Content-Type", "application/json");

            String sensorStateStr = isSensorError ? "SENSOR_ERROR" : (isOccupied ? "OCCUPIED" : "EMPTY");

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
        Serial.print(isOccupied ? "OCCUPIED" : "EMPTY");
        Serial.print(" | 서버상태: ");
        Serial.print(displayStatus);
        Serial.print(" | 적용LED: ");
        Serial.println(ledModeToString(currentLedMode));
    }

    updateLED();
}