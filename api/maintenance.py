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


@router.post('/cleanup', response_model=CleanupResult, summary='만료 데이터 미리보기 또는 삭제',
             description='기본 dry_run=true. 예약 보관기간 기본 30일, 만료 세션은 즉시 대상. 사용자·유효 예약·유효 세션은 유지합니다.')
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
