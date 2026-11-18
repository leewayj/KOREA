import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path as PathParam, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .auth import router as auth_router
from .admin import router as admin_router, require_admin
from .me import router as me_router, StudentSession
from .maintenance import router as maintenance_router
from .clock import ReservationClock
from .tags import SERVER, LOCATION, RESERVATION_READ, RESERVATION_WRITE, OPENAPI_TAGS

from .db import default_path, validate, connection
from .errors import APIError
from .models import (EffectiveStatus, ErrorResponse, Floor, Identifier,
                     Reservation, ReservationCreate, ReservationEdit,
                     ReservationExtend, ReservationMove, Room, Seat)
from .service import Service

ID = Annotated[Identifier, PathParam()]
FilterID = Annotated[Identifier | None, Query()]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]
router = APIRouter(responses={code: {'model': ErrorResponse} for code in (404, 409, 422, 503)})


def service(request: Request) -> Service:
    return request.app.state.service


async def no_body(request: Request):
    if await request.body():
        raise APIError(422, 'VALIDATION_ERROR', '이 요청은 본문을 받지 않습니다.')


def require_owner(request: Request, reservation_id: ID, session: StudentSession):
    with connection(request.app.state.service.path) as db:
        owner = db.execute('SELECT s_id FROM reservation_owners WHERE reservation_id=?',
                           (reservation_id,)).fetchone()
    if owner is None or owner['s_id'] != session['user']['s_id']:
        raise APIError(403, 'RESERVATION_FORBIDDEN', '본인 예약만 조회하거나 변경할 수 있습니다.')


@router.get('/health', tags=[SERVER])
def health(request: Request):
    service(request).floors()
    return {'status': 'ok'}


@router.get('/floors', response_model=list[Floor], tags=[LOCATION])
def floors(request: Request):
    return service(request).floors()


@router.get('/rooms', response_model=list[Room], tags=[LOCATION])
def rooms(request: Request, floor_id: FilterID = None):
    return service(request).rooms(floor_id)


@router.get('/seats', response_model=list[Seat], tags=[LOCATION])
def seats(request: Request, response: Response, floor_id: FilterID = None, room_id: FilterID = None,
          limit: Limit = 100, offset: Offset = 0):
    response.headers['Cache-Control']='no-store'
    return service(request).seats(floor_id, room_id, limit, offset)


@router.get('/seats/{seat_id}', response_model=Seat, tags=[LOCATION])
def seat(request: Request, response: Response, seat_id: ID):
    response.headers['Cache-Control']='no-store'
    return service(request).seat(seat_id)


@router.post('/reservations', response_model=Reservation, status_code=201, tags=[RESERVATION_WRITE],
             summary='현재 시각부터 예약 등록',
             description='학번 로그인이 필요합니다. 본인 활성 예약이 있으면 추가 예약을 거부합니다.',
             responses={401: {'model': ErrorResponse}})
def create_reservation(request: Request, response: Response, body: ReservationCreate, session: StudentSession):
    result = service(request).create(body.seat_id, body.def_time, owner_s_id=session['user']['s_id'])
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/reservations', dependencies=[Depends(require_admin)], response_model=list[Reservation], tags=[RESERVATION_READ],
            summary='예약 목록 및 좌석별 이력 조회',
            description='현재 상태 필터를 적용하며 최신 예약부터 반환합니다. 검색 결과가 없으면 빈 배열입니다.')
def reservations(request: Request, seat_id: FilterID = None,
                 effective_status: EffectiveStatus | None = None,
                 limit: Limit = 100, offset: Offset = 0):
    return service(request).reservations(seat_id, effective_status, limit, offset)


@router.get('/reservations/{reservation_id}', dependencies=[Depends(require_owner)], response_model=Reservation, tags=[RESERVATION_READ],
            summary='예약 상세와 현재 이용 상태 조회')
def get_reservation(request: Request, reservation_id: ID):
    return service(request).get_reservation(reservation_id)


@router.patch('/reservations/{reservation_id}', dependencies=[Depends(require_owner)], response_model=Reservation, tags=[RESERVATION_WRITE],
              summary='시작 시각부터의 총 이용시간 변경',
              description='def_time을 총 이용시간(초)으로 교체합니다. 시작·확정 시각은 변경하지 않습니다.')
def edit_reservation(request: Request, reservation_id: ID, body: ReservationEdit):
    return service(request).duration(reservation_id, body.def_time)


@router.post('/reservations/{reservation_id}/extend', dependencies=[Depends(require_owner)], response_model=Reservation, tags=[RESERVATION_WRITE],
             summary='기존 예약에 이용시간 추가',
             description='additional_seconds를 더합니다. 반복 호출하면 매번 시간이 추가됩니다.')
def extend_reservation(request: Request, reservation_id: ID, body: ReservationExtend):
    return service(request).duration(reservation_id, body.additional_seconds, additional=True)


@router.post('/reservations/{reservation_id}/move', dependencies=[Depends(require_owner)], response_model=Reservation, tags=[RESERVATION_WRITE],
             summary='좌석 이동',
             description='이용 중인 예약의 좌석만 바꿉니다. 남은 시간의 예약 충돌을 검사하며, 시간·착석 상태는 유지합니다.')
def move_reservation(request: Request, reservation_id: ID, body: ReservationMove):
    return service(request).move(reservation_id, body.target_seat_id)


@router.post('/reservations/{reservation_id}/cancel', response_model=Reservation, tags=[RESERVATION_WRITE],
             summary='예약 취소', description='같은 취소를 반복하면 기존 결과를 반환합니다. 자연 만료한 예약은 취소할 수 없습니다.',
             dependencies=[Depends(no_body), Depends(require_owner)])
def cancel_reservation(request: Request, reservation_id: ID):
    return service(request).transition(reservation_id, 'CANCELLED')


@router.post('/reservations/{reservation_id}/end', response_model=Reservation, tags=[RESERVATION_WRITE],
             summary='예약 조기 종료', description='같은 종료를 반복하면 기존 결과를 반환합니다. 착석 상태는 변경하지 않습니다.',
             dependencies=[Depends(no_body), Depends(require_owner)])
def end_reservation(request: Request, reservation_id: ID):
    return service(request).transition(reservation_id, 'ENDED')


def create_app(database_path: Path | None = None) -> FastAPI:
    path = Path(database_path).resolve() if database_path is not None else default_path()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        validate(path)
        worker=ReservationClock(path)
        app.state.reservation_clock=worker
        if os.getenv('KOREA_CLOCK_ENABLED','1') != '0':
            worker.start()
        try:
            yield
        finally:
            if worker.thread is not None:
                worker.stop()

    app = FastAPI(title='KOREA 예약정보 관리 API', version='1.11.0', lifespan=lifespan, openapi_tags=OPENAPI_TAGS,
                  description='관리자 테스트용 API. 시간은 UTC Unix 초이며, 실제 착석자 인증은 하지 않습니다.')
    app.state.service = Service(path)

    @app.exception_handler(APIError)
    async def api_error(request: Request, error: APIError):
        if error.status >= 500:
            logging.getLogger(__name__).error('API processing error: %s', error.code, exc_info=error.__cause__)
        headers = {'Retry-After': '1'} if error.status == 503 else None
        if error.status == 401:
            headers = {'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'}
        return JSONResponse(status_code=error.status, headers=headers,
                            content={'error': {'code': error.code, 'message': error.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={
            'error': {'code': 'VALIDATION_ERROR', 'message': '입력 항목과 자료형을 확인하세요.'}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return JSONResponse(status_code=error.status_code, headers=error.headers, content={
            'error': {'code': 'HTTP_ERROR', 'message': str(error.detail)}})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        logging.getLogger(__name__).error('Unhandled API error', exc_info=error)
        return JSONResponse(status_code=500, content={
            'error': {'code': 'INTERNAL_ERROR', 'message': '요청을 처리하지 못했습니다.'}})

    origins = [value.strip() for value in os.getenv('KOREA_CORS_ORIGINS', '').split(',') if value.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins,
                           allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'Authorization'])
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(me_router)
    app.include_router(maintenance_router)
    return app


app = create_app()
