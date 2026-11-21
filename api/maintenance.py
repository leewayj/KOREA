"""Explicit administrator-only cleanup; preview is the default."""
from fastapi import APIRouter, Request, Response

from .admin import AdminSession
from .tags import ADMIN_MAINTENANCE
from .db import connection
from .models import CleanupRequest, CleanupResult, ErrorResponse

router = APIRouter(prefix='/admin/maintenance', tags=[ADMIN_MAINTENANCE], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 422, 503)})

# Retention starts at natural expiry, or at explicit cancellation/early ending.
RESERVATION_TARGET = '''SELECT id FROM reservations
    WHERE (status='CONFIRMED' AND ends_at<=?)
       OR (status IN ('ENDED','CANCELLED') AND status_changed_at<=?)'''


@router.post('/cleanup', response_model=CleanupResult, summary='관리자 만료 데이터 미리보기·삭제',
             description='AdminSession이 필요합니다. 기본 본문은 `{"dry_run":true,"reservation_retention_days":30}`입니다. `{}`도 같은 기본값으로 처리합니다.\n\n- dry_run=true: 삭제 대상 건수를 반환합니다.\n- dry_run=false: 만료 사용자·관리자 세션과 보관기간이 지난 종료·취소·자연 만료 예약을 삭제합니다.\n- 예약 보관기간은 자연 만료의 종료 시각 또는 명시적 종료·취소 상태 변경 시각부터 계산합니다.\n- 연결된 예약 정책·소유자·이동 이력·시간 캐시·이력 진행 정보는 연쇄 삭제됩니다. 사용자·프로필·관리자 계정·현재 설정·독립 이용 이력은 유지합니다.\n\n응답 건수는 예약·이동·소유자·세션을 별도 집계하며 모든 연쇄 삭제 테이블을 나열하지는 않습니다. 미리보기라도 지연된 이용 이력 기록과 시간 캐시 갱신은 수행할 수 있습니다.')
def cleanup(request: Request, response: Response, body: CleanupRequest, session: AdminSession):
    with connection(request.app.state.service.path, write=True) as db:
        now = db.execute('SELECT unixepoch()').fetchone()[0]
        cutoff = now - body.reservation_retention_days * 86400
        matched = {'reservations': db.execute(
            f'SELECT COUNT(*) FROM reservations WHERE id IN ({RESERVATION_TARGET})', (cutoff, cutoff)).fetchone()[0]}
        for table in ('reservation_moves', 'reservation_owners'):
            matched[table] = db.execute(
                f'SELECT COUNT(*) FROM {table} WHERE reservation_id IN ({RESERVATION_TARGET})',
                (cutoff, cutoff)).fetchone()[0]
        for label, table in (('user_sessions', 'auth_sessions'), ('admin_sessions', 'admin_sessions')):
            matched[label] = db.execute(f'SELECT COUNT(*) FROM {table} WHERE expires_at<=?', (now,)).fetchone()[0]
        deleted = dict.fromkeys(matched, 0)
        if not body.dry_run:
            # FK cascades remove move history and owner mappings, not user accounts.
            db.execute(f'DELETE FROM reservations WHERE id IN ({RESERVATION_TARGET})', (cutoff, cutoff))
            db.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (now,))
            db.execute('DELETE FROM admin_sessions WHERE expires_at<=?', (now,))
            deleted = matched.copy()
    response.headers['Cache-Control'] = 'no-store'
    return {'dry_run': body.dry_run, 'checked_at': now,
            'reservation_retention_days': body.reservation_retention_days,
            'reservation_cutoff_at': cutoff, 'matched': matched, 'deleted': deleted}
