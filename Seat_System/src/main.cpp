#include <Arduino.h>

// RGB LED 핀 설정
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;

// 상태 정의
enum SeatStatus { 
    AVAILABLE, RESERVED_EMPTY, RESERVED_OCCUPIED, EXPIRING_OCCUPIED, EXPIRED_OCCUPIED 
};

SeatStatus currentStatus = RESERVED_EMPTY; 

unsigned long previousMillis = 0;
const long interval = 500; 
bool blinkState = false;

void setColor(int red, int green, int blue) {
    analogWrite(RED_PIN, red);
    analogWrite(GREEN_PIN, green);
    analogWrite(BLUE_PIN, blue);
}

void updateLED() {
    switch (currentStatus) {
        case AVAILABLE: setColor(0, 0, 0); break;
        // [FR-05] 예약된 빈자리 (파란색)
        case RESERVED_EMPTY: setColor(0, 0, 255); break; 
        case RESERVED_OCCUPIED: setColor(0, 0, 0); break;
        // [FR-06] 예약 종료 임박 (주황색)
        case EXPIRING_OCCUPIED: setColor(255, 127, 0); break;
        case EXPIRED_OCCUPIED:
            if (millis() - previousMillis >= interval) {
                previousMillis = millis();
                blinkState = !blinkState;
                if (blinkState) setColor(255, 0, 0);
                else setColor(0, 0, 0);
            }
            break;
    }
}

void setup() {
    pinMode(RED_PIN, OUTPUT);
    pinMode(GREEN_PIN, OUTPUT);
    pinMode(BLUE_PIN, OUTPUT);
    Serial.begin(115200);
}

void loop() {
    // 시리얼 모니터에서 글자를 입력받는 로직
    if (Serial.available() > 0) {
        char command = Serial.read();
        if (command == 'e') currentStatus = RESERVED_EMPTY;      // 'e'를 치면 예약석(파랑)
        if (command == 'o') currentStatus = RESERVED_OCCUPIED;   // 'o'를 치면 이용중(소등)
        if (command == 'w') currentStatus = EXPIRING_OCCUPIED;   // 'w'를 치면 종료임박(주황)
        if (command == 'x') currentStatus = EXPIRED_OCCUPIED;    // 'x'를 치면 만료(빨강 점멸)
    }
    updateLED();
}