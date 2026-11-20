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
            summary='관리자 기본 예약 시간·연장 한도 조회', description='AdminSession이 필요합니다. `default_duration_seconds`, `max_extensions`, `updated_at`, `updated_by`를 반환합니다. 초기값은 21600초(6시간)·2회이며 관리자가 변경한 실제 저장값을 조회합니다.')
def get_settings(request: Request, response: Response, session: AdminSession):
    response.headers['Cache-Control'] = 'no-store'
    with connection(request.app.state.service.path) as db:
        return dict(db.execute('SELECT * FROM reservation_settings WHERE id=1').fetchone())


@router.patch('/reservation-settings', response_model=ReservationSettings,
              summary='관리자 기본 예약 시간·연장 한도 수정',
              description='AdminSession이 필요합니다. `default_duration_seconds`는 양의 정수 초, `max_extensions`는 0 이상의 정수입니다. 0회면 일반 연장을 허용하지 않습니다. 생략한 필드는 유지하고 `{}`·명시적 null·잘못된 자료형은 422입니다.\n\n변경은 **이후 새로 만드는 예약부터** 적용합니다. 기존 활성·예정 예약은 생성 당시 기본 시간·한도를 유지합니다. 예약 생성에서 명시적 def_time을 보내면 그 시간을 사용하므로 이 설정은 기본값이며 총 이용시간 상한이 아닙니다. 실제 값이 바뀔 때만 수정 시각·관리자 ID를 갱신합니다.')
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
