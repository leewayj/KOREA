"""Owned reservations and seat history scoped to the signed-in student."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth import require_session
from .tags import MY_DATA, RESERVATION_WRITE
from .models import ErrorResponse, Reservation, ReservationCreate, SeatHistory, SeatUsageSummary

router = APIRouter(prefix='/me', responses={
    code: {'model': ErrorResponse} for code in (401, 404, 409, 422, 503)})
StudentSession = Annotated[dict, Depends(require_session)]


@router.get('/seat-history', response_model=list[SeatHistory], tags=[MY_DATA],
            summary='내 이용 좌석 이력 조회',
            description='DemoSession의 학번으로 독립 저장한 이용 이력을 조회합니다. 각 행은 `id`, `s_id`, `seat_id`, `used_at`이며 이용 시각·ID 내림차순입니다. 원본 예약 삭제·만료 데이터 정리 후에도 유지합니다.\n\n예약 1건당 마지막 이용 좌석 1개를 기록합니다. 이동하면 같은 이력의 좌석과 used_at을 갱신합니다. 센서가 확인한 실제 착석 증명은 아닙니다. 연결을 확정할 수 없는 기존 과거 이력은 보존됩니다. 조회 시 기록할 시점이 된 예약·이동 이력을 반영할 수 있습니다.')
def seat_history(request: Request, response: Response, session: StudentSession,
                 limit: Annotated[int, Query(ge=1, le=500)] = 100,
                 offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
    result = request.app.state.service.my_seat_history(session['user']['s_id'], limit, offset)
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/seat-history/summary', response_model=list[SeatUsageSummary], tags=[MY_DATA],
            summary='내 좌석별 이용 횟수·방·좌석번호 조회',
            description='DemoSession에 연결된 본인의 이력을 좌석별로 집계합니다. seat_id·room_id·room_name·seat_number·usage_count를 반환합니다. 횟수 내림차순, 같은 횟수는 seat_id 오름차순이며 limit·offset을 지원합니다. 이력이 없으면 빈 배열입니다. 학번은 본문·쿼리로 받지 않고 로그인 토큰에서 가져옵니다.\n\n새 방식의 예약은 마지막 이용 좌석 한 건만 집계하고 이동 이전 좌석은 제외합니다. 예약 삭제 후 보존된 이력도 포함합니다. 예약과 연결을 확정하지 못해 보존된 과거 이력은 그대로 집계하므로 과거 이동을 완전히 소급 제외하지는 못합니다. 실제 센서 착석 횟수는 아닙니다.')
def seat_usage_summary(request: Request, response: Response, session: StudentSession,
                       limit: Annotated[int, Query(ge=1, le=500)] = 100,
                       offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
    result = request.app.state.service.my_seat_usage_summary(session['user']['s_id'], limit, offset)
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/reservations' , response_model=list[Reservation], tags=[MY_DATA], summary='내 이용 중 예약 조회',
            description='DemoSession에 연결된 본인의 **IN_USE 예약만** 반환합니다. 예정 SCHEDULED·종료 ENDED·취소 CANCELLED 예약은 포함하지 않으며 없으면 빈 배열입니다. 예약 ID 내림차순이며 `limit`·`offset`을 지원합니다.')
def in_use(request: Request, response: Response, session: StudentSession,
           limit: Annotated[int, Query(ge=1, le=500)] = 100,
           offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
    result = request.app.state.service.my_in_use(session['user']['s_id'], limit, offset)
    response.headers['Cache-Control'] = 'no-store'
    return result
