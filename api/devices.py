"""Receive occupancy reports using the demo ESP32 HTTP contract."""
from fastapi import APIRouter, Request, Response

from .models import DeviceReservationInfo, ErrorResponse, Identifier, OccupancyUpdate, Seat
from .tags import SENSOR


router = APIRouter(tags=[SENSOR], responses={
    code: {'model': ErrorResponse} for code in (404, 422, 503)})


@router.post('/api/seats/{seat_id}/occupancy', response_model=Seat,
             summary='ESP32 착석 상태 수신 — 첨부 코드 호환 주소',
             description='ai_studio_code.cpp의 serverPostUrl과 같은 경로입니다. '
                         '인증 없이 OCCUPIED/EMPTY JSON을 받고 기존 주소와 같은 처리·응답을 사용합니다.')
@router.post('/seats/{seat_id}/occupancy', response_model=Seat,
             summary='ESP32 착석 상태 수신',
             description='인증 헤더 없이 state JSON만 받습니다. OCCUPIED 또는 EMPTY를 저장하고 '
                         '현재 예약·남은 시간·착석 상태를 반환합니다. 시각은 서버 기준입니다.')
def update_occupancy(request: Request, response: Response, seat_id: Identifier, body: OccupancyUpdate):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.service.update_occupancy(seat_id, body.state)


@router.get('/seats/{seat_id}/reservation-info', response_model=DeviceReservationInfo,
            summary='ESP32에 좌석 예약정보 전달',
            description='인증 없이 현재 예약 여부·시작/종료 시각·남은 초·다음 예정 예약을 반환합니다. '
                        '서버 시각 기준이며 착석·센서·LED 판단은 포함하지 않습니다.')
def reservation_info(request: Request, response: Response, seat_id: Identifier):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.service.device_reservation_info(seat_id)
