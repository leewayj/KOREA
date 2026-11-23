"""Receive occupancy reports using the demo ESP32 HTTP contract."""
from fastapi import APIRouter, Request, Response

from .models import DeviceReservationInfo, ErrorResponse, Identifier, OccupancyUpdate, Seat
from .tags import SENSOR


router = APIRouter(tags=[SENSOR], responses={
    code: {'model': ErrorResponse} for code in (404, 422, 503)})


@router.post('/seats/{seat_id}/occupancy', response_model=Seat,
             summary='ESP32 착석 상태 수신·저장',
             description='인증 없이 state(OCCUPIED·EMPTY·SENSOR_ERROR)를 받습니다. led_state는 선택이며 OFF·BLUE_ON·ORANGE_ON·RED_BLINK를 허용합니다. 생략 또는 null은 이전 회신을 유지합니다. 최초 미회신은 null입니다. 서버 수신시각과 LED 회신시각을 별도로 저장합니다. 기존 state만 보낸 요청도 허용합니다. 정상 보고는 해당 좌석을 REAL로 저장하며 VIRTUAL에서 전환할 때 이전 가상 착석의 연속성은 초기화합니다. 가상 입력은 DB 또는 별도 가상 입력 경로에서 관리해야 합니다. 오류·10초 초과 단절은 연속 착석 증거를 해제합니다. 응답은 기존 좌석 필드와 seat_status이며 장치 상세는 관리자 API에서 조회합니다.')
def update_occupancy(request: Request, response: Response, seat_id: Identifier, body: OccupancyUpdate):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.service.update_occupancy(seat_id, body.state, body.led_state)


@router.get('/seats/{seat_id}/reservation-info', response_model=DeviceReservationInfo,
            summary='ESP32에 현재·다음 예약정보 전달',
            description='기존 현재·다음 예약정보에 seat_status와 target_led를 추가합니다. ESP32는 주기적으로 GET해 LED 목표를 적용하고 다음 occupancy POST에서 led_state를 회신합니다. 예약 상태와 최종 좌석 상태는 별도입니다. 예약된 빈자리는 BLUE_ON, 착석 중 0초 초과·10분 이하는 ORANGE_ON, 자연 만료 후 입증된 연속 착석만 RED_BLINK이며 나머지는 OFF입니다. 센서 오류·실제 장치 수신 10초 초과·초기화는 UNKNOWN/OFF입니다. 조회 실패는 오류 응답입니다. 혼잡도는 포함하지 않습니다.')
def reservation_info(request: Request, response: Response, seat_id: Identifier):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.service.device_reservation_info(seat_id)

