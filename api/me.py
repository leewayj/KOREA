"""Owned reservations and seat history scoped to the signed-in student."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth import require_session
from .tags import MY_DATA, RESERVATION_WRITE
from .models import ErrorResponse, Reservation, ReservationCreate, SeatHistory

router = APIRouter(prefix='/me', responses={
    code: {'model': ErrorResponse} for code in (401, 404, 409, 422, 503)})
StudentSession = Annotated[dict, Depends(require_session)]


@router.post('/reservations', response_model=Reservation, status_code=201, tags=[RESERVATION_WRITE],
             summary='로그인 사용자 명의로 현재 시각부터 예약',
             description='학번은 본문이 아닌 로그인 토큰에서 가져옵니다.')
def create(request: Request, response: Response, body: ReservationCreate, session: StudentSession):
    result = request.app.state.service.create(body.seat_id, body.def_time,
                                              owner_s_id=session['user']['s_id'])
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/seat-history', response_model=list[SeatHistory], tags=[MY_DATA],
            summary='내 이용 좌석 이력 조회',
            description='로그인 사용자의 독립 저장된 좌석 이력을 이용 시각·ID 내림차순으로 반환합니다. '
                        '각 행은 id, s_id, seat_id, used_at입니다. 원본 예약 삭제·정리 후에도 남습니다. '
                        '예약 시작·좌석 이동 기반이며 실제 착석 증명은 아닙니다. '
                        '기존 예약별 seats 배열 응답을 대체합니다.')
def seat_history(request: Request, response: Response, session: StudentSession,
                 limit: Annotated[int, Query(ge=1, le=500)] = 100,
                 offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
    result = request.app.state.service.my_seat_history(session['user']['s_id'], limit, offset)
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/reservations', response_model=list[Reservation], tags=[MY_DATA], summary='내 이용 중(IN_USE) 예약 조회',
            description='로그인 사용자에게 연결된 IN_USE 예약만 반환합니다. 없으면 빈 배열입니다.')
def in_use(request: Request, response: Response, session: StudentSession,
           limit: Annotated[int, Query(ge=1, le=500)] = 100,
           offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
    result = request.app.state.service.my_in_use(session['user']['s_id'], limit, offset)
    response.headers['Cache-Control'] = 'no-store'
    return result
