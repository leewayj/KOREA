"""Password-based administrators and privileged reservation edits."""
import argparse
import getpass
import hashlib
import hmac
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import token_hash, no_logout_body
from .db import connection, default_path, validate
from .errors import APIError
from .tags import ADMIN_AUTH, ADMIN_RESERVATION
from .models import (AdminIdentity, AdminLoginRequest, AdminLoginResponse,
                     AdminReservationEdit, AdminReservationCreate, ReservationDeleted,
                     ErrorResponse, LogoutResponse, Reservation, Identifier, AdminSeat)
from .service import reservation, require

ITERATIONS = 600_000
SESSION_SECONDS = 3600
security = HTTPBearer(auto_error=False, scheme_name='AdminSession',
    description='POST /admin/auth/login의 access_token 값만 입력하세요.')
router = APIRouter(prefix='/admin', responses={
    code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or int(iterations) != ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Unknown usernames perform the same password derivation as known usernames.
DUMMY_HASH = f'pbkdf2_sha256${ITERATIONS}$' + '0' * 32 + '$' + '0' * 64


def create_admin(path: Path, username: str, password: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,32}', username):
        raise ValueError('Admin ID must contain 3-32 ASCII letters, digits, _ or -.')
    if not 8 <= len(password) <= 128:
        raise ValueError('Password must contain 8-128 characters.')
    validate(path)
    encoded = hash_password(password)
    with connection(path, write=True) as db:
        if db.execute('SELECT 1 FROM admins WHERE username=?', (username,)).fetchone():
            raise ValueError('Administrator already exists; existing credentials were not changed.')
        db.execute('INSERT INTO admins(username,password_hash) VALUES (?,?)', (username, encoded))


def require_admin(request: Request,
                  credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]):
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise APIError(401, 'AUTH_REQUIRED', '관리자 로그인 토큰이 필요합니다.')
    hashed = token_hash(credentials.credentials)
    with connection(request.app.state.service.path) as db:
        row = db.execute('''SELECT a.username,a.created_at,s.expires_at AS session_expires_at
            FROM admin_sessions s JOIN admins a ON a.username=s.username
            WHERE s.token_hash=? AND s.expires_at>unixepoch()''', (hashed,)).fetchone()
        if row is None:
            if db.execute('SELECT 1 FROM auth_sessions WHERE token_hash=? AND expires_at>unixepoch()', (hashed,)).fetchone():
                raise APIError(403, 'ADMIN_REQUIRED', '관리자 권한이 필요합니다.')
            raise APIError(401, 'INVALID_SESSION', '유효하지 않거나 만료된 관리자 로그인입니다.')
    return {'admin': dict(row), 'token_hash': hashed}


AdminSession = Annotated[dict, Depends(require_admin)]


@router.post('/auth/login', response_model=AdminLoginResponse, tags=[ADMIN_AUTH], summary='관리자 ID·비밀번호 로그인', description='`username`과 `password`를 입력해 관리자 전용 access_token을 받습니다. 토큰은 1시간 유효합니다. 사용자 학번 로그인과 계정·세션이 분리되어 있으며 일반 사용자 토큰으로 관리자 권한을 얻을 수 없습니다.\n\nAuthorize의 AdminSession에 토큰 값만 입력하세요. 계정 생성은 이 API가 아닌 서버의 로컬 관리자 등록 명령으로 수행합니다.')
def login(request: Request, response: Response, body: AdminLoginRequest):
    with connection(request.app.state.service.path) as db:
        account = db.execute('SELECT * FROM admins WHERE username=?', (body.username,)).fetchone()
    valid = verify_password(body.password, account['password_hash'] if account else DUMMY_HASH)
    if not valid or account is None:
        raise APIError(401, 'INVALID_CREDENTIALS', '관리자 ID 또는 비밀번호가 올바르지 않습니다.')
    token = secrets.token_urlsafe(32)
    with connection(request.app.state.service.path, write=True) as db:
        now = db.execute('SELECT unixepoch()').fetchone()[0]
        expires_at = now + SESSION_SECONDS
        db.execute('DELETE FROM admin_sessions WHERE expires_at<=?', (now,))
        db.execute('INSERT INTO admin_sessions VALUES(?,?,?,?)', (token_hash(token), body.username, now, expires_at))
    response.headers['Cache-Control'] = 'no-store'
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': SESSION_SECONDS,
            'expires_at': expires_at, 'admin': {'username': body.username,
            'created_at': account['created_at'], 'session_expires_at': expires_at}}


@router.get('/auth/me', response_model=AdminIdentity, tags=[ADMIN_AUTH], summary='현재 관리자 세션 확인', description='AdminSession 토큰을 검사하고 관리자 ID·계정 생성 시각·세션 만료 시각을 반환합니다. 토큰 누락·불일치·만료는 401, 일반 사용자 토큰은 403입니다.')
def me(response: Response, session: AdminSession):
    response.headers['Cache-Control'] = 'no-store'
    return session['admin']


@router.post('/auth/logout', response_model=LogoutResponse, tags=[ADMIN_AUTH], summary='현재 관리자 세션 로그아웃',
             dependencies=[Depends(no_logout_body)], description='AdminSession이 필요하며 본문을 보내지 않습니다. 현재 관리자 토큰의 세션 하나만 삭제합니다. 관리자 계정과 다른 세션·예약·설정은 유지합니다.')
def logout(request: Request, response: Response, session: AdminSession):
    with connection(request.app.state.service.path, write=True) as db:
        db.execute('DELETE FROM admin_sessions WHERE token_hash=?', (session['token_hash'],))
    response.headers['Cache-Control'] = 'no-store'
    return {'message': '로그아웃되었습니다.'}


@router.patch('/reservations/{reservation_id}', response_model=Reservation, tags=[ADMIN_RESERVATION],
              summary='관리자 예약 시간·상태 수정',
              description='AdminSession이 필요합니다. `starts_at`, `ends_at`, `def_time`, `status` 중 변경할 값을 입력합니다. 생략한 값은 유지하며 `{}`와 명시적 null은 422입니다.\n\n- `def_time`: 시작 시각부터의 총 이용시간(초). 시작 10시·7200초면 종료 12시입니다.\n- `def_time`과 `ends_at`은 동시 입력할 수 없습니다.\n- 시작과 종료의 순서·정수 범위·같은 좌석의 CONFIRMED 시간 중복을 검사합니다.\n- 상태 입력은 CONFIRMED·ENDED·CANCELLED입니다. 예정·사용 중·만료·취소·종료 상태와 관계없이 수정할 수 있습니다.\n- 종료·취소·만료된 예약도 관리자 수정이 가능합니다. 복구 시에도 충돌·다중 활성 예약 검증을 적용합니다.\n- 생성 당시 정책·연장 사용 횟수·확정 시각은 유지하며 관리자 시간 증가는 연장 횟수를 소비하지 않습니다.\n\n좌석·소유자 변경은 이 모델에 없습니다.')
def edit(request: Request, reservation_id: Identifier, body: AdminReservationEdit, session: AdminSession):
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
                   (reservation_id, session['admin']['username']))
        db.execute('UPDATE reservations SET starts_at=?,def_time=?,status=? WHERE id=?',
                   (start, end-start, status, reservation_id))
        db.execute('DELETE FROM reservation_admin_context WHERE reservation_id=?', (reservation_id,))
        return reservation(db, reservation_id)


@router.post('/reservations', response_model=Reservation, status_code=201, tags=[ADMIN_RESERVATION],
             summary='관리자 가상 예약 생성', description='AdminSession이 필요합니다. `seat_id`, 등록된 사용자 `s_id`, `starts_at`, `ends_at`을 입력합니다. 시각은 UTC Unix 초 정수이며 과거·현재·미래 시각을 지정할 수 있습니다.\n\n시작 < 종료, 동일 좌석 CONFIRMED 예약의 시간 중복 및 사용자의 다중 활성 예약을 검사합니다. 앞 예약 종료와 다음 시작이 같으면 허용합니다. CONFIRMED로 생성하고 현재 설정의 기본 시간·연장 한도를 함께 저장합니다. 실제 이용시간은 입력한 종료−시작입니다. 성공은 201입니다.')
def create_reservation(request: Request, response: Response, body: AdminReservationCreate, session: AdminSession):
    if body.starts_at >= body.ends_at:
        raise APIError(422,'INVALID_DURATION','시작 시각은 종료 시각보다 빨라야 합니다.')
    with connection(request.app.state.service.path,write=True) as db:
        require(db,'seats',body.seat_id)
        if db.execute('SELECT 1 FROM users WHERE s_id=?',(body.s_id,)).fetchone() is None:
            raise APIError(404,'USER_NOT_REGISTERED','등록된 사용자를 지정하세요.')
        db.execute('INSERT INTO reservation_admin_insert_context VALUES(1,?)',(session['admin']['username'],))
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
               summary='관리자 예약 영구 삭제',dependencies=[Depends(no_delete_body)], description='AdminSession이 필요하며 **본문 없이 호출**합니다. 상태와 무관하게 예약과 연결된 소유자·이동 기록·예약별 정책·시간 캐시·이력 진행 정보를 연쇄 삭제합니다. 사용자 계정·현재 기본 설정·독립 `user_seat_history`와 좌석·착석 상태는 유지합니다.\n\n성공 시 `{"deleted_reservation_id":1}`을 반환합니다. 없는 예약 또는 반복 삭제는 404입니다. 삭제를 자연 만료로 판정하지 않습니다.')
def delete_reservation(request: Request, reservation_id: Identifier, session: AdminSession):
    with connection(request.app.state.service.path,write=True) as db:
        reservation(db,reservation_id)
        db.execute('DELETE FROM reservations WHERE id=?',(reservation_id,))
    return {'deleted_reservation_id':reservation_id}


@router.get('/seats', response_model=list[AdminSeat], tags=[ADMIN_RESERVATION],
            summary='관리자 좌석·LED·통신 상태 목록',
            description='AdminSession이 필요합니다. 공개 좌석 필드에 target_led·led_state·led_state_updated_at·device_connected를 추가합니다. 수신 이력이 있고 마지막 수신 후 10초 이하는 연결, 초과는 단절입니다. 센서 오류도 정상 수신이면 연결은 true입니다. 미회신 LED는 null이며 회신 생략은 이전 값을 유지합니다. floor_id·room_id·limit·offset으로 조회하며 배열 형식을 유지합니다. 가상 좌석은 통신 단절 판정을 적용하지 않고 device_connected=false로 반환합니다.')
def admin_seats(request: Request, session: AdminSession,
                floor_id: Identifier | None = None, room_id: Identifier | None = None,
                limit: Annotated[int, Query(ge=1, le=500)] = 100,
                offset: Annotated[int, Query(ge=0)] = 0):
    return request.app.state.service.seats(floor_id, room_id, limit, offset)


@router.get('/seats/{seat_id}', response_model=AdminSeat, tags=[ADMIN_RESERVATION],
            summary='관리자 개별 좌석·LED·통신 상태',
            description='AdminSession이 필요합니다. 목표 LED와 마지막 실제 적용 회신을 구분합니다. 기존 occupancy_updated_at은 마지막 센서 저장시각입니다. 연결 여부는 실제 수신 기록으로 판정하며 초기 DB 생성시각을 수신으로 간주하지 않습니다. 재시작 후 실제 좌석은 새 보고 전 UNKNOWN입니다.')
def admin_seat(request: Request, seat_id: Identifier, session: AdminSession):
    return request.app.state.service.seat(seat_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Locally create an administrator; no default password is provided.')
    parser.add_argument('command', choices=['create'])
    parser.add_argument('--username', required=True)
    parser.add_argument('--database', type=Path, default=default_path())
    args = parser.parse_args()
    password = getpass.getpass('Password (8-128 characters): ')
    if password != getpass.getpass('Confirm password: '):
        parser.error('Passwords do not match.')
    try:
        create_admin(args.database, args.username, password)
    except (ValueError, APIError, RuntimeError) as error:
        parser.error(str(error))
    print(f'Administrator created: {args.username}')
