#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "HX711.h"

// ==================== [1. 설정 영역] ====================
const char* ssid = "GalaxyS26+5201";       // 와이파이 이름
const char* password = "11111111";         // 와이파이 비밀번호

// 백엔드 서버 주소 (1번 좌석 기준)
const char* serverGetUrl = "http://10.44.160.72:8000/seats/1";
const char* serverPostUrl = "http://10.44.160.72:8000/seats/1/occupancy";

// 핀 설정
const int LOADCELL_DOUT_PIN = 21;
const int LOADCELL_SCK_PIN = 22;
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;

HX711 scale;

// 착석·비착석 임계값 (경계값 반복 전환 방지용)
const long OCCUPIED_THRESHOLD = 200000; // 2kg 이상 -> 착석 판정
const long EMPTY_THRESHOLD = 150000;    // 이 값 이하 -> 비착석 판정

// 종료 임박 기준 (실제 명세서 10분=600초, 시연용 30초)
const long WARNING_THRESHOLD_SEC = 30;

// 통신/센서 오류 판단 기준 (명세서 기준 10초)
const unsigned long SERVER_TIMEOUT_MS = 10000;
const unsigned long SENSOR_TIMEOUT_MS = 3000;

// 최종 좌석 상태 정의 (만료·미예약 착석은 UNRESERVED_OCCUPIED로 통일)
enum SeatStatus {
    UNKNOWN,              // 1. 오류·수신 지연·초기화 중 (소등)
    RESERVED_EMPTY,       // 2. 유효 예약 있음 + 비착석 (파란색 점등)
    RESERVED_OCCUPIED,    // 3. 유효 예약 있음 + 착석 + 기준 초과 (소등)
    EXPIRING_OCCUPIED,    // 3. 유효 예약 있음 + 착석 + 0 초과~기준 이하 (주황색 점등)
    UNRESERVED_OCCUPIED,  // 4. 유효 예약 없음/만료 + 착석 (빨간색 점멸)
    AVAILABLE             // 5. 유효 예약 없음 + 비착석 (소등)
};

SeatStatus currentStatus = UNKNOWN;

// 상태 추적 변수들
bool isReserved = false;
long remainingTimeSec = 0;
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
    switch (currentStatus) {
        case UNKNOWN:
        case AVAILABLE:
        case RESERVED_OCCUPIED:
            setColor(0, 0, 0);       // 소등
            break;
        case RESERVED_EMPTY:
            setColor(0, 0, 255);     // 파란색 점등
            break;
        case EXPIRING_OCCUPIED:
            setColor(255, 80, 0);    // 주황색 점등
            break;
        case UNRESERVED_OCCUPIED:    // 빨간색 점멸 (0.5초 주기)
            if (millis() - previousBlinkMillis >= 500) {
                previousBlinkMillis = millis();
                blinkState = !blinkState;
                if (blinkState) setColor(255, 0, 0);
                else setColor(0, 0, 0);
            }
            break;
    }
}

void printStatusName(SeatStatus status) {
    switch (status) {
        case UNKNOWN:             Serial.println("UNKNOWN [소등] - 초기화 중/통신·센서 오류"); break;
        case RESERVED_EMPTY:      Serial.println("RESERVED_EMPTY [파랑 점등] - 예약 중·비어 있음"); break;
        case RESERVED_OCCUPIED:   Serial.println("RESERVED_OCCUPIED [소등] - 예약 중·이용 중"); break;
        case EXPIRING_OCCUPIED:   Serial.println("EXPIRING_OCCUPIED [주황 점등] - 예약 종료 임박"); break;
        case UNRESERVED_OCCUPIED: Serial.println("UNRESERVED_OCCUPIED [빨강 점멸] - 예약 없음/만료·이용 중"); break;
        case AVAILABLE:           Serial.println("AVAILABLE [소등] - 빈자리"); break;
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

    // 2. [서버에서 상태 받아오기] 2초마다 실행 (GET)
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
                    const char* resState = doc["reservation_state"];
                    isReserved = (resState != nullptr && String(resState) == "RESERVED");

                    if (!doc["remaining_seconds"].isNull()) {
                        remainingTimeSec = doc["remaining_seconds"];
                    } else {
                        remainingTimeSec = 0;
                    }

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

    // 3. [무게 측정 + 서버 전송 + 우선순위 판정] 1초마다 실행
    if (millis() - previousSensorMillis >= 1000) {
        previousSensorMillis = millis();
        long reading = 0;

        if (scale.is_ready()) {
            reading = scale.get_units(5) * -1;
            hasValidSensor = true;
            isSensorError = false;
            lastSensorOkMillis = millis();

            // 경계값 반복 전환 방지
            if (reading >= OCCUPIED_THRESHOLD) {
                isOccupied = true;
            } else if (reading <= EMPTY_THRESHOLD) {
                isOccupied = false;
            }
        } else {
            // 3초 이상 센서 응답이 없으면 SENSOR_ERROR 처리
            if (millis() - lastSensorOkMillis > SENSOR_TIMEOUT_MS) {
                isSensorError = true;
            }
        }

        // 서버로 센서 판정 결과 전송 (POST)
        if (WiFi.status() == WL_CONNECTED) {
            HTTPClient http;
            http.setTimeout(1500);
            http.begin(serverPostUrl);
            http.addHeader("Content-Type", "application/json");

            String sensorStateStr = "UNKNOWN";
            if (isSensorError) sensorStateStr = "SENSOR_ERROR";
            else if (hasValidSensor) sensorStateStr = isOccupied ? "OCCUPIED" : "EMPTY";

            String httpRequestData = "{\"state\":\"" + sensorStateStr + "\"}";
            int postCode = http.POST(httpRequestData);
            if (postCode <= 0 || postCode >= 400) {
                Serial.printf(">>> 센서 POST 응답/에러: HTTP %d (전송값: %s)\n",
                              postCode, sensorStateStr.c_str());
            }
            http.end();
        }

        // ==================== [판정 우선순위 1~5번] ====================
        if (!hasServerSynced || isServerError || !hasValidSensor || isSensorError) {
            // [우선순위 1] 오류·수신 지연·초기화 중 -> UNKNOWN
            currentStatus = UNKNOWN;
        } 
        else if (isReserved && !isOccupied) {
            // [우선순위 2] 유효 예약 있음 + 비착석 -> RESERVED_EMPTY
            currentStatus = RESERVED_EMPTY;
        } 
        else if (isReserved && isOccupied) {
            // [우선순위 3] 유효 예약 있음 + 착석
            if (remainingTimeSec > WARNING_THRESHOLD_SEC) {
                currentStatus = RESERVED_OCCUPIED;
            } else if (remainingTimeSec > 0) {
                currentStatus = EXPIRING_OCCUPIED;
            } else {
                currentStatus = UNRESERVED_OCCUPIED;
            }
        } 
        else if (!isReserved && isOccupied) {
            // [우선순위 4] 유효 예약 없음/만료 + 착석 중 -> UNRESERVED_OCCUPIED (빨강 점멸)
            currentStatus = UNRESERVED_OCCUPIED;
        } 
        else {
            // [우선순위 5] 유효 예약 없음 + 비착석 -> AVAILABLE
            currentStatus = AVAILABLE;
        }
        // ===============================================================

        // 시리얼 모니터 출력
        Serial.print("예약: ");
        Serial.print(isReserved ? "O" : "X");
        Serial.print(" | 남은시간: ");
        Serial.print(remainingTimeSec);
        Serial.print("초 | 무게: ");
        Serial.print(reading);
        Serial.print(" | 판정: ");
        printStatusName(currentStatus);
    }

    updateLED();
}
