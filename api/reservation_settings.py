"""Administrator-only reservation policy settings; existing policies are immutable."""
from fastapi import APIRouter, Request, Response

from .admin import AdminSession
from .db import connection
from .errors import APIError
from .models import ErrorResponse, ReservationSettings, ReservationSettingsEdit
from .tags import ADMIN_SETTINGS


router = APIRouter(prefix='/admin', tags=[ADMIN_SETTINGS], responses={
    code: {'model': ErrorResponse} for code in (401, 403, 422, 503)})


@router.get('/reservation-settings', response_model=ReservationSettings,
            summary='기본 예약 시간·최대 연장 횟수 조회')
def get_settings(request: Request, response: Response, session: AdminSession):
    response.headers['Cache-Control'] = 'no-store'
    with connection(request.app.state.service.path) as db:
        return dict(db.execute('SELECT * FROM reservation_settings WHERE id=1').fetchone())


@router.patch('/reservation-settings', response_model=ReservationSettings,
              summary='새 예약에 적용할 기본 예약 시간·최대 연장 횟수 수정',
              description='초 단위 양의 정수와 0 이상의 연장 횟수. 생략한 값은 유지하며 기존 예약에는 소급하지 않습니다.')
def edit_settings(request: Request, response: Response, body: ReservationSettingsEdit, session: AdminSession):
    fields = body.model_fields_set
    if not fields or any(getattr(body, field) is None for field in fields):
        raise APIError(422, 'VALIDATION_ERROR', '변경할 설정을 하나 이상 입력하고 null은 보내지 마세요.')
    with connection(request.app.state.service.path, write=True) as db:
        old = db.execute('SELECT * FROM reservation_settings WHERE id=1').fetchone()
        duration = body.default_duration_seconds if 'default_duration_seconds' in fields else old['default_duration_seconds']
        maximum = body.max_extensions if 'max_extensions' in fields else old['max_extensions']
        if duration > db.execute('SELECT 9223372036854775807-unixepoch()').fetchone()[0]:
            raise APIError(422, 'INVALID_DURATION', '기본 예약 시간이 저장 가능한 범위를 초과합니다.')
        if (duration, maximum) != (old['default_duration_seconds'], old['max_extensions']):
            db.execute('''UPDATE reservation_settings SET default_duration_seconds=?, max_extensions=?,
                          updated_at=unixepoch(), updated_by=? WHERE id=1''',
                       (duration, maximum, session['admin']['username']))
        result = dict(db.execute('SELECT * FROM reservation_settings WHERE id=1').fetchone())
    response.headers['Cache-Control'] = 'no-store'
    return result
