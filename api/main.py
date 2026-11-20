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
from .admin import router as admin_router
from .me import router as me_router, StudentSession
from .maintenance import router as maintenance_router
from .clock import ReservationClock
from .devices import router as device_router
from .reservation_settings import router as reservation_settings_router
from .tags import SERVER, LOCATION, RESERVATION_READ, RESERVATION_WRITE, OPENAPI_TAGS

from .db import default_path, validate
from .errors import APIError
from .models import (EffectiveStatus, ErrorResponse, Floor, Identifier,
                     Reservation, ReservationCreate,
                     ReservationMove, Room, Seat)
from .service import Service

ID = Annotated[Identifier, PathParam()]
FilterID = Annotated[Identifier | None, Query()]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]
OWNER_RESPONSES = {code: {'model': ErrorResponse} for code in (401, 403)}
router = APIRouter(responses={code: {'model': ErrorResponse} for code in (404, 409, 422, 503)})


def service(request: Request) -> Service:
    return request.app.state.service


async def no_body(request: Request):
    if await request.body():
        raise APIError(422, 'VALIDATION_ERROR', '이 요청은 본문을 받지 않습니다.')


@router.get('/health', tags=[SERVER], description='층 목록을 읽어 API와 DB에 접근할 수 있는지 확인합니다. 정상 응답은 `{"status":"ok"}`입니다. 센서·ESP32 연결 상태나 실제 착석 여부를 확인하는 API는 아닙니다.', summary='서버·DB 연결 확인')
def health(request: Request):
    service(request).floors()
    return {'status': 'ok'}


@router.get('/floors', response_model=list[Floor], tags=[LOCATION], description='등록된 층을 정렬 순서·ID 순으로 반환합니다. 로그인 없이 조회합니다. 응답의 `id`를 방·좌석 조회의 `floor_id`에 사용합니다.', summary='층 목록 조회')
def floors(request: Request):
    return service(request).floors()


@router.get('/rooms', response_model=list[Room], tags=[LOCATION], description='`floor_id`를 생략하면 전체 방, 지정하면 해당 층의 방을 반환합니다. 없는 층은 404입니다. 로그인 없이 조회합니다.', summary='전체 또는 특정 층의 방 목록 조회')
def rooms(request: Request, floor_id: FilterID = None):
    return service(request).rooms(floor_id)


@router.get('/seats', response_model=list[Seat], tags=[LOCATION], description='`floor_id`, `room_id`로 범위를 좁히고 `limit`·`offset`으로 나누어 조회합니다.\n\n좌석별 위치, 현재 예약, 다음 예정 예약, 남은 초, 마지막 저장 착석 상태를 반환합니다. `reservation_state=AVAILABLE`은 현재 예약이 없다는 뜻이며 비착석을 보장하지 않습니다. 현재 예약이 없으면 `remaining_seconds=null`입니다. 로그인 없이 조회합니다.', summary='좌석 목록·현재 및 다음 예약 조회')
def seats(request: Request, response: Response, floor_id: FilterID = None, room_id: FilterID = None,
          limit: Limit = 100, offset: Offset = 0):
    response.headers['Cache-Control']='no-store'
    return service(request).seats(floor_id, room_id, limit, offset)


@router.get('/seats/{seat_id}', response_model=Seat, tags=[LOCATION], description='전역 `seat_id`로 좌석을 조회합니다. 방 안의 표시 번호와 다릅니다. ESP32는 이 경로를 1~2초마다 요청해 `reservation_state`와 `remaining_seconds`를 읽을 수 있습니다.\n\n현재 유효 예약은 RESERVED, 없으면 AVAILABLE입니다. 예정 예약은 `next_reservation`으로 구분합니다. 착석 상태는 DB의 마지막 저장값이며 수신 중단 자동 판정이나 LED 명령을 포함하지 않습니다. 없는 좌석은 404입니다.', summary='개별 좌석의 예약·착석 정보 조회')
def seat(request: Request, response: Response, seat_id: ID):
    response.headers['Cache-Control']='no-store'
    return service(request).seat(seat_id)


@router.post('/reservations', response_model=Reservation, status_code=201, tags=[RESERVATION_WRITE],
             summary='로그인 사용자 명의로 새 예약 생성',
             description='`seat_id`를 입력합니다. 선택 항목 `def_time`은 총 이용시간(초)이며 생략·null이면 현재 관리자 설정의 기본 시간을 사용합니다.\n\n학번은 본문이 아닌 DemoSession에서 가져옵니다. 시작 시각은 서버 현재 시각으로 고정하고 status는 CONFIRMED로 생성합니다. 좌석 중복과 사용자 다중 활성 예약을 차단하며 예정 예약도 활성 예약에 포함합니다. 생성 당시 기본 시간·연장 한도를 별도 저장합니다.\n\n201과 생성한 예약을 반환합니다.',
             responses={401: {'model': ErrorResponse}})
def create_reservation(request: Request, response: Response, body: ReservationCreate, session: StudentSession):
    result = service(request).create(body.seat_id, body.def_time, owner_s_id=session['user']['s_id'])
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/reservations', response_model=list[Reservation], tags=[RESERVATION_READ],
            summary='전체 예약·좌석별 이력 조회',
            description='공개 예약 목록입니다. `seat_id`, `effective_status`와 페이지 범위를 지정할 수 있으며 예약 ID 내림차순으로 반환합니다. 계산 상태는 SCHEDULED·IN_USE·ENDED·CANCELLED입니다. 검색 결과가 없으면 빈 배열입니다.\n\n본인 예약만 조회하는 경로는 `GET /me/reservations`이며 현재 IN_USE 예약만 제공합니다. 이 API는 학생 ID를 반환하지 않습니다.')
def reservations(request: Request, seat_id: FilterID = None,
                 effective_status: EffectiveStatus | None = None,
                 limit: Limit = 100, offset: Offset = 0):
    return service(request).reservations(seat_id, effective_status, limit, offset)


@router.get('/reservations/{reservation_id}', response_model=Reservation, tags=[RESERVATION_READ],
            summary='예약 ID로 상세·현재 상태 조회', description='`reservation_id`는 좌석 번호가 아닌 예약 고유 ID입니다. 저장 상태와 서버 시각 기준 계산 상태, 남은 시간, 안내 문구, 생성 당시 설정과 연장 사용 횟수를 반환합니다. 삭제되었거나 없는 예약은 404입니다. 로그인 없이 조회합니다.')
def get_reservation(request: Request, reservation_id: ID):
    return service(request).get_reservation(reservation_id)


@router.post('/reservations/{reservation_id}/extend', response_model=Reservation, tags=[RESERVATION_WRITE], responses=OWNER_RESPONSES,
             summary='생성 당시 기본 시간만큼 예약 연장',
             description='**본문을 보내지 않습니다.** `{}`, `null`, `additional_seconds` JSON도 422입니다.\n\n예약에 저장된 `policy_default_duration_seconds`를 기존 종료 시각에 더하고 연장 횟수 1회를 소비합니다. 이후 관리자 설정이 변경되어도 기존 예약의 연장량·한도는 유지합니다. 횟수 초과는 409 EXTENSION_LIMIT_REACHED, 시간 충돌은 409 RESERVATION_CONFLICT이며 실패 시 시간·횟수를 모두 유지합니다. 종료·취소·만료 예약은 거부합니다.\n\nDemoSession 로그인이 필요합니다. 로그인 학번과 예약 소유자를 비교해 본인 예약만 처리합니다. 타인·소유자 없는 예약은 403이며 반복 요청도 소유자를 먼저 확인합니다.',
             dependencies=[Depends(no_body)])
def extend_reservation(request: Request, reservation_id: ID, session: StudentSession):
    return service(request).extend(reservation_id, owner_s_id=session['user']['s_id'])


@router.post('/reservations/{reservation_id}/move', response_model=Reservation, tags=[RESERVATION_WRITE], responses=OWNER_RESPONSES,
             summary='이용 중 예약의 좌석 이동',
             description='`{"target_seat_id":5}`처럼 목적 좌석의 전역 ID를 입력합니다. 현재 IN_USE인 CONFIRMED 예약만 이동할 수 있습니다. 목적 좌석의 남은 예약 구간 충돌을 검사하고, 예약 ID·시작/종료 시각·생성 정책·연장 횟수와 각 좌석의 착석 상태를 유지합니다. 이동 이력은 기록합니다. 같은 좌석이면 기존 결과를 반환합니다.\n\n현재 예정 예약은 이동할 수 없습니다. DemoSession 로그인이 필요하며 본인 예약만 처리합니다. 타인·소유자 없는 예약은 403입니다. 동일 좌석 요청도 소유자를 먼저 확인합니다.')
def move_reservation(request: Request, reservation_id: ID, body: ReservationMove, session: StudentSession):
    return service(request).move(reservation_id, body.target_seat_id, owner_s_id=session['user']['s_id'])


@router.post('/reservations/{reservation_id}/cancel', response_model=Reservation, tags=[RESERVATION_WRITE], responses=OWNER_RESPONSES,
             summary='이용 중 예약 취소', description='**본문 없이 호출**하여 저장 상태를 CANCELLED로 바꿉니다. 현재 IN_USE 예약만 취소할 수 있고 같은 취소를 반복하면 기존 결과를 반환합니다. 예정·자연 만료·종료 예약은 취소하지 못합니다. 예약을 물리 삭제하거나 착석 상태를 바꾸지는 않습니다.\n\nDemoSession 로그인이 필요합니다. 로그인 학번과 예약 소유자를 비교해 본인 예약만 처리합니다. 타인·소유자 없는 예약은 403이며 반복 요청도 소유자를 먼저 확인합니다.',
             dependencies=[Depends(no_body)])
def cancel_reservation(request: Request, reservation_id: ID, session: StudentSession):
    return service(request).transition(reservation_id, 'CANCELLED', owner_s_id=session['user']['s_id'])


@router.post('/reservations/{reservation_id}/end', response_model=Reservation, tags=[RESERVATION_WRITE], responses=OWNER_RESPONSES,
             summary='이용 중 예약 조기 종료', description='**본문 없이 호출**하여 저장 상태를 ENDED로 바꿉니다. 현재 IN_USE 예약만 종료할 수 있고 같은 종료를 반복하면 기존 결과를 반환합니다. 예정·자연 만료·취소 예약은 변경하지 못합니다. 기존 종료일시나 센서 착석 상태를 수정하지 않습니다.\n\nDemoSession 로그인이 필요합니다. 로그인 학번과 예약 소유자를 비교해 본인 예약만 처리합니다. 타인·소유자 없는 예약은 403이며 반복 요청도 소유자를 먼저 확인합니다.',
             dependencies=[Depends(no_body)])
def end_reservation(request: Request, reservation_id: ID, session: StudentSession):
    return service(request).transition(reservation_id, 'ENDED', owner_s_id=session['user']['s_id'])


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

    app = FastAPI(title='KOREA 예약정보 관리 API', version='1.13.0', lifespan=lifespan, openapi_tags=OPENAPI_TAGS,
                  description='여기자리 서비스 위한 API.')
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
    app.include_router(device_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(reservation_settings_router)
    app.include_router(me_router)
    app.include_router(maintenance_router)
    return app


app = create_app()
