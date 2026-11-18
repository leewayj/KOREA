import sqlite3


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def database_error(error: sqlite3.Error) -> APIError:
    text = str(error)
    conflicts = {
        'user already has active reservation': ('ACTIVE_RESERVATION_EXISTS', '이미 활성 예약이 있습니다. 기존 예약을 종료하거나 취소한 뒤 다시 예약하세요.'),
        'reservation overlaps': ('RESERVATION_CONFLICT', '이미 예약된 좌석입니다.'),
        'terminal reservation cannot be changed': ('RESERVATION_CLOSED', '종료·취소된 예약은 수정할 수 없습니다.'),
        'reservation already expired': ('RESERVATION_EXPIRED', '만료된 예약은 수정할 수 없습니다.'),
    }
    for key, (code, message) in conflicts.items():
        if key in text:
            return APIError(409, code, message)
    if isinstance(error, sqlite3.IntegrityError):
        return APIError(422, 'CONSTRAINT_VIOLATION', '데이터베이스 제약조건에 맞지 않는 요청입니다.')
    if 'locked' in text or 'busy' in text:
        return APIError(503, 'DATABASE_BUSY', '다른 작업을 처리 중입니다. 잠시 후 다시 요청하세요.')
    return APIError(500, 'DATABASE_ERROR', '데이터베이스 작업을 완료하지 못했습니다.')
