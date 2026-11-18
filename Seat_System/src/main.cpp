#include <Arduino.h>
#include "HX711.h"

// 핀 설정
const int LOADCELL_DOUT_PIN = 21;
const int LOADCELL_SCK_PIN = 22;
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;

HX711 scale;

// [시연용 설정]
const long OCCUPANCY_THRESHOLD = 200000;    // 2kg 기준값
bool isReserved = true;                     // 예약 여부
long remainingTimeSec = 20;                 // ★ 시작 시간 20초
const long WARNING_THRESHOLD_SEC = 10;      // ★ 종료 10초 전부터 주황색 알림

// 상태 정의
enum SeatStatus { AVAILABLE, RESERVED_EMPTY, RESERVED_OCCUPIED, EXPIRING_OCCUPIED, EXPIRED_OCCUPIED };
SeatStatus currentStatus = AVAILABLE;

// 타이머 변수
unsigned long previousBlinkMillis = 0;
unsigned long previousTimerMillis = 0;
bool blinkState = false;

void setColor(int r, int g, int b) {
    analogWrite(RED_PIN, r);
    analogWrite(GREEN_PIN, g);
    analogWrite(BLUE_PIN, b);
}

void updateLED() {
    switch (currentStatus) {
        case AVAILABLE: setColor(0, 0, 0); break;          // 소등
        case RESERVED_EMPTY: setColor(0, 0, 255); break;   // 파랑 (예약석 빈자리)
        case RESERVED_OCCUPIED: setColor(0, 0, 0); break;  // 소등 (정상 이용 중)
        case EXPIRING_OCCUPIED: setColor(255, 80, 0); break; // 주황 (종료 10초 임박)
        case EXPIRED_OCCUPIED:                             // 빨강 점멸 (시간 만료 후 착석 지속)
            if (millis() - previousBlinkMillis >= 500) {
                previousBlinkMillis = millis();
                blinkState = !blinkState;
                if (blinkState) setColor(255, 0, 0); 
                else setColor(0, 0, 0);
            }
            break;
    }
}

void setup() {
    Serial.begin(115200);
    scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
    scale.tare(); 
    
    pinMode(RED_PIN, OUTPUT);
    pinMode(GREEN_PIN, OUTPUT);
    pinMode(BLUE_PIN, OUTPUT);
    
    Serial.println("======================================");
    Serial.println("도서관 스마트 좌석 시연 시스템 시작!");
    Serial.println("키보드 'r' 누르면 20초로 타이머 리셋");
    Serial.println("키보드 't' 누르면 무게 영점(Tare) 잡기");
    Serial.println("======================================");
}

void loop() {
    // 1. 키보드 입력 처리
    if (Serial.available() > 0) {
        char cmd = Serial.read();
        if (cmd == 't') {
            scale.tare();
            Serial.println(">>> [영점 완료] 무게가 0으로 초기화되었습니다.");
        }
        if (cmd == 'r') {
            remainingTimeSec = 20;
            Serial.println(">>> [타이머 리셋] 다시 20초부터 카운트다운 시작!");
        }
    }

    // 2. 1초마다 남은 시간 1초씩 감소 (카운트다운)
    if (millis() - previousTimerMillis >= 1000) {
        previousTimerMillis = millis();
        if (remainingTimeSec > 0) {
            remainingTimeSec--;
        }
    }

    // 3. 무게 측정 및 상태 판정
    if (scale.is_ready()) {
        long reading = scale.get_units(5) * -1;
        bool isOccupied = (reading > OCCUPANCY_THRESHOLD);

        // 시리얼 모니터 출력
        Serial.print("남은시간: ");
        Serial.print(remainingTimeSec);
        Serial.print("초 | 무게: ");
        Serial.print(reading);
        Serial.print(" | 상태: ");

        if (!isReserved) {
            currentStatus = isOccupied ? EXPIRED_OCCUPIED : AVAILABLE;
            Serial.println("예약없음");
        } else {
            if (!isOccupied) {
                currentStatus = RESERVED_EMPTY; 
                Serial.println("예약됨(빈자리) -> [파란색 LED]");
            } else {
                if (remainingTimeSec > WARNING_THRESHOLD_SEC) {
                    currentStatus = RESERVED_OCCUPIED;
                    Serial.println("이용 중 (정상) -> [LED 소등]");
                } else if (remainingTimeSec > 0) {
                    currentStatus = EXPIRING_OCCUPIED;
                    Serial.println("종료 임박 (10초 이하) -> [주황색 LED]");
                } else {
                    currentStatus = EXPIRED_OCCUPIED;
                    Serial.println("예약 만료 (미반납) -> [빨간색 점멸!]");
                }
            }
        }
    }

    updateLED();
    delay(100);
}