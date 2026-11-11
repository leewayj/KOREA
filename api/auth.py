"""ID-only demo sign-in. No password or real student identity verification."""
import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connection
from .errors import APIError
from .tags import USER_AUTH, MY_DATA
from .models import (ErrorResponse, LoginRequest, LoginResponse, LogoutResponse, UserIdentity,
                     UserRegisterRequest, UserRegistration)

SESSION_SECONDS = 3600
bearer = HTTPBearer(auto_error=False, scheme_name='DemoSession',
                    description='POST /auth/login 응답의 access_token. 학번만 사용하는 시연용 식별입니다.')
router = APIRouter(prefix='/auth', responses={
    code: {'model': ErrorResponse} for code in (401, 404, 409, 422, 503)})


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def require_session(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise APIError(401, 'AUTH_REQUIRED', '로그인 토큰이 필요합니다.')
    hashed = token_hash(credentials.credentials)
    with connection(request.app.state.service.path) as db:
        row = db.execute('''SELECT u.s_id, p.name, p.college, p.department,
            u.created_at, s.expires_at AS session_expires_at
            FROM auth_sessions s JOIN users u ON u.s_id = s.s_id
            LEFT JOIN user_profiles p ON p.s_id=u.s_id
            WHERE s.token_hash = ? AND s.expires_at > unixepoch()''', (hashed,)).fetchone()
    if row is None:
        raise APIError(401, 'INVALID_SESSION', '유효하지 않거나 만료된 로그인입니다.')
    return {'user': dict(row), 'token_hash': hashed}


@router.post('/register', response_model=UserRegistration, status_code=201, tags=[USER_AUTH],
             summary='학번·이름·단과대학·학과 별도 등록',
             description='로그인 세션을 만들지 않습니다. 기존 사용자 중 프로필이 없는 학번도 한 번 등록할 수 있습니다.')
def register(request: Request, response: Response, body: UserRegisterRequest):
    with connection(request.app.state.service.path, write=True) as db:
        if db.execute('SELECT 1 FROM user_profiles WHERE s_id=?', (body.s_id,)).fetchone():
            raise APIError(409, 'USER_ALREADY_REGISTERED', '이미 등록된 사용자입니다.')
        db.execute('INSERT INTO users(s_id) VALUES(?) ON CONFLICT(s_id) DO NOTHING', (body.s_id,))
        db.execute('INSERT INTO user_profiles(s_id,name,college,department) VALUES(?,?,?,?)',
                   (body.s_id, body.name, body.college, body.department))
        created_at = db.execute('SELECT created_at FROM users WHERE s_id=?', (body.s_id,)).fetchone()[0]
    response.headers['Cache-Control'] = 'no-store'
    return {'s_id': body.s_id, 'name': body.name, 'college': body.college,
            'department': body.department, 'created_at': created_at}


@router.post('/login', response_model=LoginResponse, tags=[USER_AUTH], summary='학번형 ID만으로 시연용 로그인',
             description='등록된 학번으로만 로그인합니다. 미등록 학번은 먼저 /auth/register로 등록하세요. 실제 학생 여부는 확인하지 않습니다.')
def login(request: Request, response: Response, body: LoginRequest):
    token = secrets.token_urlsafe(32)
    with connection(request.app.state.service.path, write=True) as db:
        now = db.execute('SELECT unixepoch()').fetchone()[0]
        expires_at = now + SESSION_SECONDS
        user = db.execute('''SELECT u.s_id,p.name,p.college,p.department,u.created_at
            FROM users u LEFT JOIN user_profiles p ON p.s_id=u.s_id WHERE u.s_id=?''', (body.s_id,)).fetchone()
        if user is None:
            raise APIError(404, 'USER_NOT_REGISTERED', '사용자 정보를 먼저 등록하세요.')
        db.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (now,))
        db.execute('INSERT INTO auth_sessions(token_hash,s_id,created_at,expires_at) VALUES (?,?,?,?)',
                   (token_hash(token), body.s_id, now, expires_at))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': SESSION_SECONDS,
            'expires_at': expires_at,
            'user': {**dict(user), 'session_expires_at': expires_at}}


@router.get('/me', response_model=UserIdentity, tags=[MY_DATA], summary='현재 로그인 사용자의 학번·이름·단과대학·학과 조회')
def me(response: Response, session: Annotated[dict, Depends(require_session)]):
    response.headers['Cache-Control'] = 'no-store'
    return session['user']


async def no_logout_body(request: Request):
    if await request.body():
        raise APIError(422, 'VALIDATION_ERROR', '로그아웃 요청은 본문을 받지 않습니다.')


@router.post('/logout', response_model=LogoutResponse, tags=[USER_AUTH], summary='현재 로그인 세션 종료',
             dependencies=[Depends(no_logout_body)])
def logout(request: Request, response: Response, session: Annotated[dict, Depends(require_session)]):
    with connection(request.app.state.service.path, write=True) as db:
        db.execute('DELETE FROM auth_sessions WHERE token_hash = ?', (session['token_hash'],))
    response.headers['Cache-Control'] = 'no-store'
    return {'message': '로그아웃되었습니다.'}
