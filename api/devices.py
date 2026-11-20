"""Receive occupancy reports using the demo ESP32 HTTP contract."""
from fastapi import APIRouter, Request, Response

from .models import DeviceReservationInfo, ErrorResponse, Identifier, OccupancyUpdate, Seat
from .tags import SENSOR


router = APIRouter(tags=[SENSOR], responses={
    code: {'model': ErrorResponse} for code in (404, 422, 503)})


@router.post('/seats/{seat_id}/occupancy', response_model=Seat,
             summary='ESP32 착석 상태 수신·저장',
             description='인증 없이 `{"state":"OCCUPIED"}` 또는 `{"state":"EMPTY"}`를 받습니다. 전역 seat_id가 있어야 하며 다른 값·빈 본문·추가 필드는 422입니다.\n\n새 착석은 서버 시각을 occupied_since에 기록하고 반복 OCCUPIED는 최초 시각을 유지합니다. EMPTY는 occupied_since를 null로 만들며 매 정상 수신마다 updated_at을 갱신합니다. 성공은 200과 기존 Seat 형식의 좌석 정보입니다. 예약 생성·변경이나 센서 오류·수신 중단 판정은 하지 않습니다.\n\n현재 등록 주소는 `/seats/{seat_id}/occupancy`입니다. `/api/seats/...` 접두 경로는 현재 등록되어 있지 않습니다.')
def update_occupancy(request: Request, response: Response, seat_id: Identifier, body: OccupancyUpdate):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.service.update_occupancy(seat_id, body.state)


@router.get('/seats/{seat_id}/reservation-info', response_model=DeviceReservationInfo,
            summary='ESP32에 현재·다음 예약정보 전달',
            description='ESP32가 이 경로를 1~2초마다 GET하면 인증 없이 예약정보를 응답합니다. 서버가 ESP32에 먼저 접속하는 push 방식은 아닙니다.\n\n현재 예약 여부, 예약 ID, 시작·종료 시각, 남은 초, 다음 예정 예약과 서버 현재 시각을 반환합니다. 현재 예약이 없으면 AVAILABLE과 현재 예약 필드 null이며 예정 예약은 next_reservation으로 구분합니다. 착석 판단·10초 수신 지연·LED 명령·혼잡도는 포함하지 않습니다.')
def reservation_info(request: Request, response: Response, seat_id: Identifier):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.service.device_reservation_info(seat_id)
