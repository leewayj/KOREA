#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Ticker.h>
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
Ticker ledTicker; // HTTPS 통신 중에도 멈추지 않고 LED를 제어하는 독립 타이머

// HTTPS 연결 재사용을 위한 전역 클라이언트 (SSL 핸드셰이크 지연 최소화)
WiFiClientSecure secureClient;
HTTPClient httpGet;
HTTPClient httpPost;

// 착석·비착석 임계값 (2L 생수병 약 200,000 시연 최적화)
const long OCCUPIED_THRESHOLD = 180000; // 1.8kg 이상 -> 착석 판정
const long EMPTY_THRESHOLD = 130000;    // 1.3kg 이하 -> 비착석 후보

// 시연용 빠른 반응을 위한 이석 유예 시간 (1초)
const unsigned long LEAVE_DEBOUNCE_MS = 1000;

// 의자 넘어짐(전도) 및 비정상 하중 감지 기준
const long TILT_NEGATIVE_LIMIT = -120000;
const long OVERLOAD_LIMIT = 2000000;
const unsigned long ABNORMAL_HOLD_MS = 3000;

// 자동 영점(Auto-Tare) 설정
const long AUTO_TARE_MAX_OFFSET = 120000;
const long AUTO_TARE_MIN_DRIFT = 20000;
const long STABILITY_TOLERANCE = 10000;
const unsigned long AUTO_TARE_WAIT_MS = 4000;

// 통신/센서 오류 판단 기준
const unsigned long SERVER_TIMEOUT_MS = 15000;
const unsigned long SENSOR_TIMEOUT_MS = 3000;

// 통신 주기 설정 (빠른 동기화 최적화)
const unsigned long SERVER_GET_INTERVAL_MS = 700;   // 0.7초마다 서버 상태 조회
const unsigned long SENSOR_POST_INTERVAL_MS = 1000; // 1초마다 정기 보고 (상태 변화 시 즉시 보고)

// 빨간색 경고 점멸 주기 (0.2초 = 200ms)
const float RED_BLINK_INTERVAL_SEC = 0.2;

// LED 출력 모드 정의
enum LedMode {
    LED_OFF,
    LED_BLUE_ON,
    LED_ORANGE_ON,
    LED_RED_BLINK
};

volatile LedMode currentLedMode = LED_OFF;
volatile bool blinkState = false;

// 서버 및 센서 상태 변수
String serverSeatStatus = "UNKNOWN";
String serverTargetLed = "OFF";
bool isOccupied = false;
String lastReportedState = "";
LedMode lastReportedLed = LED_OFF;

// 오류 및 초기화 추적 변수
bool hasServerSynced = false;
bool hasValidSensor = false;
bool isServerError = false;
bool isSensorError = false;
bool isChairFallen = false;
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
unsigned long previousServerMillis = 0;
unsigned long previousSensorMillis = 0;
unsigned long previousWifiCheckMillis = 0;
// ========================================================

void setColor(int r, int g, int b) {
    analogWrite(RED_PIN, r);
    analogWrite(GREEN_PIN, g);
    analogWrite(BLUE_PIN, b);
}

void onLedTimerTick() {
    switch (currentLedMode) {
        case LED_OFF:
            setColor(0, 0, 0);
            break;
        case LED_BLUE_ON:
            setColor(0, 0, 255);
            break;
        case LED_ORANGE_ON:
            setColor(255, 25, 0);
            break;
        case LED_RED_BLINK:
            blinkState = !blinkState;
            if (blinkState) setColor(255, 0, 0);
            else setColor(0, 0, 0);
            break;
    }
}

void setLedMode(LedMode newMode) {
    if (currentLedMode != newMode) {
        currentLedMode = newMode;
        if (newMode == LED_RED_BLINK) {
            blinkState = true;
            setColor(255, 0, 0);
        } else {
            onLedTimerTick();
        }
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

    ledTicker.attach(RED_BLINK_INTERVAL_SEC, onLedTimerTick);

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

    // SSL 클라이언트 및 HTTP 연결 재사용 설정
    secureClient.setInsecure();
    httpGet.setReuse(true);
    httpGet.setTimeout(5000);
    httpPost.setReuse(true);
    httpPost.setTimeout(5000);

    lastServerOkMillis = millis();
    lastSensorOkMillis = millis();
}

void sendSensorReport(String sensorStateStr) {
    if (WiFi.status() != WL_CONNECTED) return;

    httpPost.begin(secureClient, serverPostUrl);
    httpPost.addHeader("Content-Type", "application/json");

    JsonDocument postDoc;
    postDoc["state"] = sensorStateStr;
    postDoc["led_state"] = ledModeToString(currentLedMode);

    String httpRequestData;
    serializeJson(postDoc, httpRequestData);

    int postCode = httpPost.POST(httpRequestData);
    if (postCode != 200) {
        Serial.printf(">>> 센서/LED 회신 POST 에러: HTTP %d\n", postCode);
    }
    httpPost.end();

    lastReportedState = sensorStateStr;
    lastReportedLed = currentLedMode;
    previousSensorMillis = millis();
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

    // 2. [서버 상태 조회] 0.7초마다 실행 (GET)
    if (millis() - previousServerMillis >= SERVER_GET_INTERVAL_MS) {
        previousServerMillis = millis();

        if (WiFi.status() == WL_CONNECTED) {
            httpGet.begin(secureClient, serverGetUrl);
            int httpResponseCode = httpGet.GET();

            if (httpResponseCode == 200) {
                String payload = httpGet.getString();
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
            httpGet.end();
        }

        if (millis() - lastServerOkMillis > SERVER_TIMEOUT_MS) {
            isServerError = true;
        }
    }

    // 3. [무게 측정 + 상태 판정] 0.5초마다 빠르게 측정하되, 변경 시 즉시 POST 전송
    static unsigned long lastMeasureMillis = 0;
    if (millis() - lastMeasureMillis >= 500) {
        lastMeasureMillis = millis();
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

            // [B] 정상 상태일 때 착석 판정 (이석 유예 1초 적용)
            if (!isChairFallen) {
                if (reading >= OCCUPIED_THRESHOLD) {
                    isOccupied = true;
                    isLeavePending = false;
                } else if (reading <= EMPTY_THRESHOLD) {
                    if (isOccupied) {
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

            // [C] 자동 영점(Auto-Tare)
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

        // [D] 최종 LED 결정 (예약 없는 빈 좌석 또는 무단 점유 상태 착석 시 즉시 빨간색 점멸)
        String displayStatus = serverSeatStatus;

        if (!hasServerSynced || isServerError || !hasValidSensor || isSensorError || isChairFallen) {
            setLedMode(LED_OFF);
            displayStatus = isChairFallen ? "CHAIR_FALLEN" : "UNKNOWN";
        }
        else if ((serverSeatStatus == "AVAILABLE" || serverSeatStatus == "UNRESERVED_OCCUPIED") && isOccupied) {
            // 예약 없는 좌석(AVAILABLE) 및 서버 무단 점유 상태(UNRESERVED_OCCUPIED)에서 착석 유지 시 빨간색 점멸
            setLedMode(LED_RED_BLINK);
        }
        else if (serverTargetLed == "BLUE_ON") {
            setLedMode(LED_BLUE_ON);
        }
        else if (serverTargetLed == "ORANGE_ON") {
            setLedMode(LED_ORANGE_ON);
        }
        else if (serverTargetLed == "RED_BLINK") {
            setLedMode(LED_RED_BLINK);
        }
        else {
            setLedMode(LED_OFF);
        }

        // [E] 상태가 바뀌었거나 1초 정기 보고 주기가 되었을 때 즉시 서버로 회신
        if (hasValidSensor || isSensorError) {
            String sensorStateStr = (isSensorError || isChairFallen)
                ? "SENSOR_ERROR"
                : (isOccupied ? "OCCUPIED" : "EMPTY");

            bool stateChanged = (sensorStateStr != lastReportedState) || (currentLedMode != lastReportedLed);

            if (stateChanged || (millis() - previousSensorMillis >= SENSOR_POST_INTERVAL_MS)) {
                sendSensorReport(sensorStateStr);

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
        }
    }
}