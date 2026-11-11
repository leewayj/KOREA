"""Create an owned reservation and list only the signed-in user's IN_USE rows."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth import require_session
from .models import ErrorResponse, Reservation, ReservationCreate

router = APIRouter(prefix='/me', tags=['내 예약'], responses={
    code: {'model': ErrorResponse} for code in (401, 404, 409, 422, 503)})
StudentSession = Annotated[dict, Depends(require_session)]


@router.post('/reservations', response_model=Reservation, status_code=201,
             summary='로그인 사용자 명의로 현재 시각부터 예약',
             description='학번은 본문이 아닌 로그인 토큰에서 가져옵니다.')
def create(request: Request, response: Response, body: ReservationCreate, session: StudentSession):
    result = request.app.state.service.create(body.seat_id, body.def_time,
                                              owner_s_id=session['user']['s_id'])
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/reservations', response_model=list[Reservation], summary='내 이용 중(IN_USE) 예약 조회',
            description='로그인 사용자에게 연결된 IN_USE 예약만 반환합니다. 없으면 빈 배열입니다.')
def in_use(request: Request, response: Response, session: StudentSession,
           limit: Annotated[int, Query(ge=1, le=500)] = 100,
           offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0):
    result = request.app.state.service.my_in_use(session['user']['s_id'], limit, offset)
    response.headers['Cache-Control'] = 'no-store'
    return result
