from pathlib import Path

from .db import connection
from .errors import APIError


def require(db, table, row_id):
    # table is supplied exclusively by server code, never by a request.
    row = db.execute(f'SELECT * FROM {table} WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        raise APIError(404, 'NOT_FOUND', '요청한 데이터를 찾을 수 없습니다.')
    return row


def reservation(db, reservation_id):
    row = db.execute('SELECT * FROM reservation_status WHERE id = ?', (reservation_id,)).fetchone()
    if row is None:
        raise APIError(404, 'RESERVATION_NOT_FOUND', '예약을 찾을 수 없습니다.')
    return dict(row)


class Service:
    def __init__(self, path: Path):
        self.path = path

    def floors(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute('SELECT * FROM floors ORDER BY sort_order, id')]

    def rooms(self, floor_id=None):
        with connection(self.path) as db:
            if floor_id is not None:
                require(db, 'floors', floor_id)
            return [dict(r) for r in db.execute(
                'SELECT * FROM rooms WHERE (? IS NULL OR floor_id = ?) ORDER BY floor_id, id', (floor_id, floor_id))]

    def seats(self, floor_id=None, room_id=None, limit=100, offset=0):
        with connection(self.path) as db:
            if floor_id is not None:
                require(db, 'floors', floor_id)
            if room_id is not None:
                require(db, 'rooms', room_id)
            return [dict(r) for r in db.execute('''
                SELECT v.* FROM seat_status v JOIN seats s ON s.id = v.seat_id
                JOIN rooms rm ON rm.id = s.room_id
                WHERE (? IS NULL OR rm.floor_id = ?) AND (? IS NULL OR s.room_id = ?)
                ORDER BY v.seat_id LIMIT ? OFFSET ?
            ''', (floor_id, floor_id, room_id, room_id, limit, offset))]

    def seat(self, seat_id):
        with connection(self.path) as db:
            require(db, 'seats', seat_id)
            return dict(db.execute('SELECT * FROM seat_status WHERE seat_id = ?', (seat_id,)).fetchone())

    def reservations(self, seat_id=None, effective_status=None, limit=100, offset=0):
        with connection(self.path) as db:
            if seat_id is not None:
                require(db, 'seats', seat_id)
            return [dict(r) for r in db.execute('''
                SELECT * FROM reservation_status
                WHERE (? IS NULL OR seat_id = ?) AND (? IS NULL OR effective_status = ?)
                ORDER BY id DESC LIMIT ? OFFSET ?
            ''', (seat_id, seat_id, effective_status, effective_status, limit, offset))]

    def get_reservation(self, reservation_id):
        with connection(self.path) as db:
            return reservation(db, reservation_id)

    def create(self, seat_id, def_time=None):
        with connection(self.path, write=True) as db:
            require(db, 'seats', seat_id)
            if def_time is None:
                cursor = db.execute('INSERT INTO reservations(seat_id) VALUES (?)', (seat_id,))
            else:
                cursor = db.execute('INSERT INTO reservations(seat_id, def_time) VALUES (?, ?)', (seat_id, def_time))
            return reservation(db, cursor.lastrowid)

    def duration(self, reservation_id, seconds, additional=False):
        with connection(self.path, write=True) as db:
            row = reservation(db, reservation_id)
            now = db.execute('SELECT unixepoch()').fetchone()[0]
            if row['status'] != 'CONFIRMED' or row['ends_at'] <= now:
                raise APIError(409, 'RESERVATION_CLOSED', '종료·취소·만료된 예약은 수정할 수 없습니다.')
            duration = row['def_time'] + seconds if additional else seconds
            if duration > 9223372036854775807 - row['starts_at']:
                raise APIError(422, 'INVALID_DURATION', '이용시간이 저장 가능한 범위를 초과합니다.')
            if row['starts_at'] + duration <= now:
                raise APIError(422, 'INVALID_DURATION', '변경할 종료 시각은 현재 시각 이후여야 합니다.')
            db.execute('UPDATE reservations SET def_time = ? WHERE id = ?', (duration, reservation_id))
            return reservation(db, reservation_id)

    def transition(self, reservation_id, status):
        with connection(self.path, write=True) as db:
            row = reservation(db, reservation_id)
            if row['status'] == status:
                return row  # Safe repeat: preserve the original transition timestamp.
            if row['status'] != 'CONFIRMED' or row['effective_status'] != 'IN_USE':
                raise APIError(409, 'RESERVATION_CLOSED', '종료·취소·만료된 예약은 변경할 수 없습니다.')
            db.execute('UPDATE reservations SET status = ? WHERE id = ?', (status, reservation_id))
            return reservation(db, reservation_id)

    def move(self, reservation_id, target_seat_id):
        with connection(self.path, write=True) as db:
            row = reservation(db, reservation_id)
            if row['status'] != 'CONFIRMED' or row['effective_status'] != 'IN_USE':
                raise APIError(409, 'RESERVATION_CLOSED', '종료·취소·만료된 예약은 이동할 수 없습니다.')
            require(db, 'seats', target_seat_id)
            if row['seat_id'] == target_seat_id:
                return row
            # The DB checks the remaining interval and atomically records move history.
            db.execute('UPDATE reservations SET seat_id = ? WHERE id = ?', (target_seat_id, reservation_id))
            return reservation(db, reservation_id)

