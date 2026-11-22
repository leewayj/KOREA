"""Public management endpoints; user authentication remains separate."""
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request, Response

from .db import connection
from .errors import APIError
from .tags import ADMIN_RESERVATION
from .models import (AdminReservationEdit, AdminReservationCreate, ReservationDeleted,
                     ErrorResponse, Reservation, Identifier, AdminSeat)
from .service import reservation, require

router = APIRouter(prefix='/admin', responses={
    code: {'model': ErrorResponse} for code in (404, 409, 422, 503)})


def context_actor(db):
    # Preserve the existing NOT NULL FK schema without requiring a login account.
    # This non-password marker is never a usable credential; no login route exists.
    actor = '__api_context__'
    db.execute('INSERT INTO admins(username,password_hash) VALUES(?,?) ON CONFLICT(username) DO NOTHING',
               (actor, '!disabled!'))
    return actor


@router.patch('/reservations/{reservation_id}', response_model=Reservation, tags=[ADMIN_RESERVATION],
              summary='관리자 예약 시간·상태 수정',
              description='로그인이나 토큰 없이 호출합니다. `starts_at`, `ends_at`, `def_time`, `status` 중 변경할 값을 입력합니다. 생략한 값은 유지하며 `{}`와 명시적 null은 422입니다.\n\n- `def_time`: 시작 시각부터의 총 이용시간(초). 시작 10시·7200초면 종료 12시입니다.\n- `def_time`과 `ends_at`은 동시 입력할 수 없습니다.\n- 시작과 종료의 순서·정수 범위·같은 좌석의 CONFIRMED 시간 중복을 검사합니다.\n- 상태 입력은 CONFIRMED·ENDED·CANCELLED입니다. 예정·사용 중·만료·취소·종료 상태와 관계없이 수정할 수 있습니다.\n- 종료·취소·만료된 예약도 관리자 수정이 가능합니다. 복구 시에도 충돌·다중 활성 예약 검증을 적용합니다.\n- 생성 당시 정책·연장 사용 횟수·확정 시각은 유지하며 관리자 시간 증가는 연장 횟수를 소비하지 않습니다.\n\n좌석·소유자 변경은 이 모델에 없습니다.')
def edit(request: Request, reservation_id: Identifier, body: AdminReservationEdit):
    fields = body.model_fields_set
    if not fields or any(getattr(body, name) is None for name in fields):
        raise APIError(422, 'VALIDATION_ERROR', '변경할 필드를 하나 이상 입력하고 null은 보내지 마세요.')
    if 'def_time' in fields and 'ends_at' in fields:
        raise APIError(422, 'VALIDATION_ERROR', 'def_time과 ends_at은 함께 입력할 수 없습니다.')
    with connection(request.app.state.service.path, write=True) as db:
        old = reservation(db, reservation_id)
        start = body.starts_at if 'starts_at' in fields else old['starts_at']
        if 'def_time' in fields:
            if body.def_time > 9223372036854775807-start:
                raise APIError(422, 'INVALID_DURATION', '이용시간이 저장 가능한 범위를 초과합니다.')
            end = start + body.def_time
        else:
            end = body.ends_at if 'ends_at' in fields else old['ends_at']
        status = body.status if 'status' in fields else old['status']
        if start >= end:
            raise APIError(422, 'INVALID_DURATION', '시작 시각은 종료 시각보다 빨라야 합니다.')
        if (start, end, status) == (old['starts_at'], old['ends_at'], old['status']):
            return old
        db.execute('INSERT INTO reservation_admin_context VALUES(?,?)',
                   (reservation_id, context_actor(db)))
        db.execute('UPDATE reservations SET starts_at=?,def_time=?,status=? WHERE id=?',
                   (start, end-start, status, reservation_id))
        db.execute('DELETE FROM reservation_admin_context WHERE reservation_id=?', (reservation_id,))
        return reservation(db, reservation_id)


@router.post('/reservations', response_model=Reservation, status_code=201, tags=[ADMIN_RESERVATION],
             summary='관리자 가상 예약 생성', description='로그인이나 토큰 없이 호출합니다. `seat_id`, 등록된 사용자 `s_id`, `starts_at`, `ends_at`을 입력합니다. 시각은 UTC Unix 초 정수이며 과거·현재·미래 시각을 지정할 수 있습니다.\n\n시작 < 종료, 동일 좌석 CONFIRMED 예약의 시간 중복 및 사용자의 다중 활성 예약을 검사합니다. 앞 예약 종료와 다음 시작이 같으면 허용합니다. CONFIRMED로 생성하고 현재 설정의 기본 시간·연장 한도를 함께 저장합니다. 실제 이용시간은 입력한 종료−시작입니다. 성공은 201입니다.')
def create_reservation(request: Request, response: Response, body: AdminReservationCreate):
    if body.starts_at >= body.ends_at:
        raise APIError(422,'INVALID_DURATION','시작 시각은 종료 시각보다 빨라야 합니다.')
    with connection(request.app.state.service.path,write=True) as db:
        require(db,'seats',body.seat_id)
        if db.execute('SELECT 1 FROM users WHERE s_id=?',(body.s_id,)).fetchone() is None:
            raise APIError(404,'USER_NOT_REGISTERED','등록된 사용자를 지정하세요.')
        db.execute('INSERT INTO reservation_admin_insert_context VALUES(1,?)',(context_actor(db),))
        cursor=db.execute('INSERT INTO reservations(seat_id,starts_at,def_time) VALUES(?,?,?)',
                          (body.seat_id,body.starts_at,body.ends_at-body.starts_at))
        rid=cursor.lastrowid
        db.execute('INSERT INTO reservation_owners VALUES(?,?)',(rid,body.s_id))
        db.execute('DELETE FROM reservation_admin_insert_context')
        result=reservation(db,rid)
    response.headers['Cache-Control']='no-store'
    return result


async def no_delete_body(request: Request):
    if await request.body():
        raise APIError(422,'VALIDATION_ERROR','예약 삭제 요청은 본문을 받지 않습니다.')


@router.delete('/reservations/{reservation_id}',response_model=ReservationDeleted, tags=[ADMIN_RESERVATION],
               summary='관리자 예약 영구 삭제',dependencies=[Depends(no_delete_body)], description='로그인이나 토큰 없이 **본문 없이 호출**합니다. 상태와 무관하게 예약과 연결된 소유자·이동 기록·예약별 정책·시간 캐시·이력 진행 정보를 연쇄 삭제합니다. 사용자 계정·현재 기본 설정·독립 `user_seat_history`와 좌석·착석 상태는 유지합니다.\n\n성공 시 `{"deleted_reservation_id":1}`을 반환합니다. 없는 예약 또는 반복 삭제는 404입니다. 삭제를 자연 만료로 판정하지 않습니다.')
def delete_reservation(request: Request, reservation_id: Identifier):
    with connection(request.app.state.service.path,write=True) as db:
        reservation(db,reservation_id)
        db.execute('DELETE FROM reservations WHERE id=?',(reservation_id,))
    return {'deleted_reservation_id':reservation_id}


@router.get('/seats', response_model=list[AdminSeat], tags=[ADMIN_RESERVATION],
            summary='관리자 좌석·LED·통신 상태 목록',
            description='로그인이나 토큰 없이 호출합니다. 공개 좌석 필드에 target_led·led_state·led_state_updated_at·device_connected를 추가합니다. 수신 이력이 있고 마지막 수신 후 10초 이하는 연결, 초과는 단절입니다. 센서 오류도 정상 수신이면 연결은 true입니다. 미회신 LED는 null이며 회신 생략은 이전 값을 유지합니다. floor_id·room_id·limit·offset으로 조회하며 배열 형식을 유지합니다. 가상 좌석은 통신 단절 판정을 적용하지 않고 device_connected=false로 반환합니다.')
def admin_seats(request: Request,
                floor_id: Identifier | None = None, room_id: Identifier | None = None,
                limit: Annotated[int, Query(ge=1, le=500)] = 100,
                offset: Annotated[int, Query(ge=0)] = 0):
    return request.app.state.service.seats(floor_id, room_id, limit, offset)


@router.get('/seats/{seat_id}', response_model=AdminSeat, tags=[ADMIN_RESERVATION],
            summary='관리자 개별 좌석·LED·통신 상태',
            description='로그인이나 토큰 없이 호출합니다. 목표 LED와 마지막 실제 적용 회신을 구분합니다. 기존 occupancy_updated_at은 마지막 센서 저장시각입니다. 연결 여부는 실제 수신 기록으로 판정하며 초기 DB 생성시각을 수신으로 간주하지 않습니다. 재시작 후 실제 좌석은 새 보고 전 UNKNOWN입니다.')
def admin_seat(request: Request, seat_id: Identifier):
    return request.app.state.service.seat(seat_id)


