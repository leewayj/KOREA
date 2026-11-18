#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "HX711.h"

// ==================== [1. 설정 영역] ====================
// 시연 때 사용할 스마트폰 핫스팟(또는 공유기) 정보 입력!
const char* ssid = "GalaxyS26+5201";       // 와이파이 이름
const char* password = "11111111";         // 와이파이 비밀번호

// 백엔드 서버 주소 (팀원이 알려준 서버 IP와 포트 번호 입력)
// 예: "http://192.168.0.15:8000/seats/1" (1번 좌석 기준)
const char* serverGetUrl = "http://10.44.160.72:8000/seats/1";

// 센서값(착석 여부)을 보낼 서버 API 주소
const char* serverPostUrl = "http://10.44.160.72:8000/api/seats/1/occupancy";

// 핀 설정
const int LOADCELL_DOUT_PIN = 21;
const int LOADCELL_SCK_PIN = 22;
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;

HX711 scale;
const long OCCUPANCY_THRESHOLD = 200000; // 2kg 기준값

// 상태 정의
enum SeatStatus {
    AVAILABLE,
    RESERVED_EMPTY,
    RESERVED_OCCUPIED,
    EXPIRING_OCCUPIED,
    EXPIRED_OCCUPIED
};

SeatStatus currentStatus = AVAILABLE;

// 서버에서 받아올 변수들 (초기값)
bool isReserved = false;
long remainingTimeSec = 600;
const long WARNING_THRESHOLD_SEC = 30; // 30초 전 주황색 임박

// 타이머 변수
unsigned long previousBlinkMillis = 0;
unsigned long previousServerMillis = 0;
bool blinkState = false;
// ========================================================

void setColor(int r, int g, int b) {
    analogWrite(RED_PIN, r);
    analogWrite(GREEN_PIN, g);
    analogWrite(BLUE_PIN, b);
}

void updateLED() {
    switch (currentStatus) {
        case AVAILABLE:
            setColor(0, 0, 0);       // 소등
            break;
        case RESERVED_EMPTY:
            setColor(0, 0, 255);     // 파랑 (예약석 빈자리)
            break;
        case RESERVED_OCCUPIED:
            setColor(0, 0, 0);       // 소등 (정상 이용 중)
            break;
        case EXPIRING_OCCUPIED:
            setColor(255, 80, 0);    // 주황 (종료 임박)
            break;
        case EXPIRED_OCCUPIED:       // 빨강 점멸 (만료 후 미반납)
            if (millis() - previousBlinkMillis >= 500) {
                previousBlinkMillis = millis();
                blinkState = !blinkState;

                if (blinkState) {
                    setColor(255, 0, 0);
                } else {
                    setColor(0, 0, 0);
                }
            }
            break;
    }
}

void setup() {
    Serial.begin(115200);

    // 핀 모드 설정
    pinMode(RED_PIN, OUTPUT);
    pinMode(GREEN_PIN, OUTPUT);
    pinMode(BLUE_PIN, OUTPUT);

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
    if (WiFi.status() == WL_CONNECTED && millis() - previousServerMillis >= 2000) {
        previousServerMillis = millis();

        HTTPClient http;
        http.setTimeout(1500);
        http.begin(serverGetUrl);
        int httpResponseCode = http.GET();

        if (httpResponseCode > 0) {
            String payload = http.getString();
            JsonDocument doc;
            DeserializationError error = deserializeJson(doc, payload);

            if (!error) {
                const char* resState = doc["reservation_state"];
                if (resState != nullptr && String(resState) == "RESERVED") {
                    isReserved = true;
                } else {
                    isReserved = false;
                }

                if (!doc["remaining_seconds"].isNull()) {
                    remainingTimeSec = doc["remaining_seconds"];
                } else {
                    remainingTimeSec = 0;
                }

                Serial.println(">>> 서버 데이터 동기화 완료 (GET 성공)");
            }
        } else {
            Serial.print(">>> 서버 GET 연결 에러 코드: ");
            Serial.println(httpResponseCode);
        }

        http.end();
    }

    // 3. [무게 측정 + 서버로 전송 + 화면 출력] 1초마다 실행
    static unsigned long previousSensorMillis = 0;
    if (millis() - previousSensorMillis >= 1000) {
        previousSensorMillis = millis();

        if (scale.is_ready()) {
            long reading = scale.get_units(5) * -1;
            bool isOccupied = (reading > OCCUPANCY_THRESHOLD);

            // 서버로 내 착석 상태 보내기 (POST)
            if (WiFi.status() == WL_CONNECTED) {
                HTTPClient http;
                http.setTimeout(1500);
                http.begin(serverPostUrl);
                http.addHeader("Content-Type", "application/json");

                String httpRequestData = isOccupied
                    ? "{\"state\":\"OCCUPIED\"}"
                    : "{\"state\":\"EMPTY\"}";

                int postCode = http.POST(httpRequestData);

                if (postCode <= 0) {
                    Serial.print(">>> 센서 POST 에러 코드: ");
                    Serial.println(postCode);
                } else {
                    // 서버에서 받은 HTTP 응답 코드와 이번에 보낸 착석 상태 출력
                    Serial.printf(">>> 착석 POST 응답: HTTP %d | 전송 상태: %s\n",
                                  postCode, isOccupied ? "OCCUPIED" : "EMPTY");
                }

                http.end();
            }

            // 최종 상태 판정
            if (!isReserved) {
                currentStatus = isOccupied ? EXPIRED_OCCUPIED : AVAILABLE;
            } else {
                if (!isOccupied) {
                    currentStatus = RESERVED_EMPTY;
                } else {
                    if (remainingTimeSec > WARNING_THRESHOLD_SEC) {
                        currentStatus = RESERVED_OCCUPIED;
                    } else if (remainingTimeSec > 0) {
                        currentStatus = EXPIRING_OCCUPIED;
                    } else {
                        currentStatus = EXPIRED_OCCUPIED;
                    }
                }
            }

            // 시리얼 모니터에 남은 시간 & 무게 & 상태 출력!
            Serial.print("예약여부: ");
            Serial.print(isReserved ? "O" : "X");
            Serial.print(" | 남은시간: ");
            Serial.print(remainingTimeSec);
            Serial.print("초 | 무게: ");
            Serial.print(reading);
            Serial.print(" | 상태: ");

            if (currentStatus == AVAILABLE) {
                Serial.println("빈자리 (소등)");
            } else if (currentStatus == RESERVED_EMPTY) {
                Serial.println("예약석 빈자리 (파랑)");
            } else if (currentStatus == RESERVED_OCCUPIED) {
                Serial.println("이용 중 (소등)");
            } else if (currentStatus == EXPIRING_OCCUPIED) {
                Serial.println("종료 임박 (주황)");
            } else if (currentStatus == EXPIRED_OCCUPIED) {
                Serial.println("만료/미예약 착석 (빨강 점멸)");
            }
        }
    }

    updateLED();
}