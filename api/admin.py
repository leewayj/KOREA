"""Password-based administrators and privileged reservation edits."""
import argparse
import getpass
import hashlib
import hmac
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import token_hash, no_logout_body
from .db import connection, default_path, validate
from .errors import APIError
from .tags import ADMIN_AUTH, ADMIN_RESERVATION
from .models import (AdminIdentity, AdminLoginRequest, AdminLoginResponse,
                     AdminReservationEdit, AdminReservationCreate, ReservationDeleted,
                     ErrorResponse, LogoutResponse, Reservation, Identifier)
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


@router.post('/auth/login', response_model=AdminLoginResponse, tags=[ADMIN_AUTH], summary='관리자 ID·비밀번호 로그인')
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


@router.get('/auth/me', response_model=AdminIdentity, tags=[ADMIN_AUTH], summary='현재 관리자 로그인 확인')
def me(response: Response, session: AdminSession):
    response.headers['Cache-Control'] = 'no-store'
    return session['admin']


@router.post('/auth/logout', response_model=LogoutResponse, tags=[ADMIN_AUTH], summary='현재 관리자 세션 종료',
             dependencies=[Depends(no_logout_body)])
def logout(request: Request, response: Response, session: AdminSession):
    with connection(request.app.state.service.path, write=True) as db:
        db.execute('DELETE FROM admin_sessions WHERE token_hash=?', (session['token_hash'],))
    response.headers['Cache-Control'] = 'no-store'
    return {'message': '로그아웃되었습니다.'}


@router.patch('/reservations/{reservation_id}', response_model=Reservation, tags=[ADMIN_RESERVATION],
              summary='관리자 예약 시작·종료 시각 및 상태 변경',
              description='UTC Unix 초. 생략한 필드는 유지합니다. 확정 예약끼리 시간 중복은 허용하지 않습니다.')
def edit(request: Request, reservation_id: Identifier, body: AdminReservationEdit, session: AdminSession):
    fields = body.model_fields_set
    if not fields or any(getattr(body, name) is None for name in fields):
        raise APIError(422, 'VALIDATION_ERROR', '변경할 필드를 하나 이상 입력하고 null은 보내지 마세요.')
    with connection(request.app.state.service.path, write=True) as db:
        old = reservation(db, reservation_id)
        start = body.starts_at if 'starts_at' in fields else old['starts_at']
        end = body.ends_at if 'ends_at' in fields else old['ends_at']
        status = body.status if 'status' in fields else old['status']
        if start >= end:
            raise APIError(422, 'INVALID_DURATION', '시작 시각은 종료 시각보다 빨라야 합니다.')
        if status == 'ENDED' and start > db.execute('SELECT unixepoch()').fetchone()[0]:
            raise APIError(422, 'INVALID_STATUS', '시작 전 예약은 종료 상태로 바꿀 수 없습니다.')
        if (start, end, status) == (old['starts_at'], old['ends_at'], old['status']):
            return old
        db.execute('INSERT INTO reservation_admin_context VALUES(?,?)',
                   (reservation_id, session['admin']['username']))
        db.execute('UPDATE reservations SET starts_at=?,def_time=?,status=? WHERE id=?',
                   (start, end-start, status, reservation_id))
        db.execute('DELETE FROM reservation_admin_context WHERE reservation_id=?', (reservation_id,))
        return reservation(db, reservation_id)


@router.post('/reservations', response_model=Reservation, status_code=201, tags=[ADMIN_RESERVATION],
             summary='관리자가 사용자·좌석·시작·종료 시각을 지정하여 예약 등록')
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
               summary='관리자가 특정 예약과 연결 이력을 영구 삭제',dependencies=[Depends(no_delete_body)])
def delete_reservation(request: Request, reservation_id: Identifier, session: AdminSession):
    with connection(request.app.state.service.path,write=True) as db:
        reservation(db,reservation_id)
        db.execute('DELETE FROM reservations WHERE id=?',(reservation_id,))
    return {'deleted_reservation_id':reservation_id}


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
