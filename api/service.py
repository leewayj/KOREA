from pathlib import Path

from .db import connection
from .errors import APIError
from .timing import project, EFFECTIVE_SQL


def require(db, table, row_id):
    # table is supplied exclusively by server code, never by a request.
    row = db.execute(f'SELECT * FROM {table} WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        raise APIError(404, 'NOT_FOUND', '요청한 데이터를 찾을 수 없습니다.')
    return row


def reservation(db, reservation_id, now=None):
    now = db.execute('SELECT unixepoch()').fetchone()[0] if now is None else now
    row = db.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,)).fetchone()
    if row is None:
        raise APIError(404, 'RESERVATION_NOT_FOUND', '예약을 찾을 수 없습니다.')
    return project(row, now)


def seat_rows(db, now, floor_id=None, room_id=None, seat_id=None, limit=100, offset=0):
    rows = db.execute('''SELECT s.id AS seat_id,f.code AS floor_code,f.name AS floor_name,
        rm.code AS room_code,rm.name AS room_name,s.number AS seat_number,
        r.id AS active_reservation_id,r.starts_at,r.ends_at,
        CASE WHEN r.id IS NULL THEN 'AVAILABLE' ELSE 'RESERVED' END AS reservation_state,
        o.state AS occupancy_state,o.occupied_since,o.updated_at AS occupancy_updated_at,
        n.id AS next_id,n.starts_at AS next_starts,n.ends_at AS next_ends
        FROM seats s JOIN rooms rm ON rm.id=s.room_id JOIN floors f ON f.id=rm.floor_id
        LEFT JOIN seat_occupancy o ON o.seat_id=s.id
        LEFT JOIN reservations r ON r.seat_id=s.id AND r.status='CONFIRMED'
            AND r.starts_at<=:now AND :now<r.ends_at
        LEFT JOIN reservations n ON n.id=(SELECT nr.id FROM reservations nr
            WHERE nr.seat_id=s.id AND nr.status='CONFIRMED' AND nr.starts_at>:now
            ORDER BY nr.starts_at,nr.id LIMIT 1)
        WHERE (:floor IS NULL OR rm.floor_id=:floor) AND (:room IS NULL OR s.room_id=:room)
          AND (:seat IS NULL OR s.id=:seat)
        ORDER BY s.id LIMIT :limit OFFSET :offset''',
        {'now':now,'floor':floor_id,'room':room_id,'seat':seat_id,'limit':limit,'offset':offset}).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        nid,start,end=item.pop('next_id'),item.pop('next_starts'),item.pop('next_ends')
        item['next_reservation']={'id':nid,'starts_at':start,'ends_at':end} if nid is not None else None
        if item['active_reservation_id'] is not None:
            timing=project({'status':'CONFIRMED','starts_at':item['starts_at'],'ends_at':item['ends_at']},now)
            item.update({key:timing[key] for key in ('remaining_seconds','notice_code','notice_message')})
        else:
            item.update(remaining_seconds=None,notice_code=None,notice_message=None)
        item['server_now']=now
        result.append(item)
    return result


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
            now=db.execute('SELECT unixepoch()').fetchone()[0]
            if floor_id is not None:
                require(db, 'floors', floor_id)
            if room_id is not None:
                require(db, 'rooms', room_id)
            return seat_rows(db,now,floor_id,room_id,limit=limit,offset=offset)

    def seat(self, seat_id):
        with connection(self.path) as db:
            require(db, 'seats', seat_id)
            now=db.execute('SELECT unixepoch()').fetchone()[0]
            return seat_rows(db,now,seat_id=seat_id)[0]

    def reservations(self, seat_id=None, effective_status=None, limit=100, offset=0):
        with connection(self.path) as db:
            now=db.execute('SELECT unixepoch()').fetchone()[0]
            if seat_id is not None:
                require(db, 'seats', seat_id)
            return [project(r,now) for r in db.execute(f'''
                SELECT * FROM reservations
                WHERE (:seat IS NULL OR seat_id=:seat) AND (:status IS NULL OR ({EFFECTIVE_SQL})=:status)
                ORDER BY id DESC LIMIT :limit OFFSET :offset
            ''', {'now':now,'seat':seat_id,'status':effective_status,'limit':limit,'offset':offset})]

    def get_reservation(self, reservation_id):
        with connection(self.path) as db:
            return reservation(db, reservation_id)

    def create(self, seat_id, def_time=None, *, owner_s_id):
        if owner_s_id is None:
            raise APIError(401, 'AUTH_REQUIRED', '예약하려면 로그인해야 합니다.')
        with connection(self.path, write=True) as db:
            require(db, 'seats', seat_id)
            if def_time is None:
                cursor = db.execute('INSERT INTO reservations(seat_id) VALUES (?)', (seat_id,))
            else:
                # The guard and starts_at's default use the same SQLite statement
                # clock, so a second changing between queries cannot overflow.
                cursor = db.execute('''INSERT INTO reservations(seat_id, def_time)
                    SELECT ?, ? WHERE ? <= 9223372036854775807 - unixepoch()''',
                    (seat_id, def_time, def_time))
                if cursor.rowcount == 0:
                    raise APIError(422, 'INVALID_DURATION', '이용시간이 저장 가능한 범위를 초과합니다.')
            db.execute('INSERT INTO reservation_owners(reservation_id,s_id) VALUES(?,?)',
                       (cursor.lastrowid, owner_s_id))
            return reservation(db, cursor.lastrowid)

    def my_in_use(self, s_id, limit=100, offset=0):
        with connection(self.path) as db:
            now=db.execute('SELECT unixepoch()').fetchone()[0]
            return [project(row,now) for row in db.execute('''
                SELECT r.* FROM reservations r
                JOIN reservation_owners owner ON owner.reservation_id=r.id
                WHERE owner.s_id=? AND r.status='CONFIRMED' AND r.starts_at<=? AND ?<r.ends_at
                ORDER BY r.id DESC LIMIT ? OFFSET ?
            ''', (s_id, now, now, limit, offset))]

    def my_seat_history(self, s_id, limit=100, offset=0):
        # Materialize due starts even if the periodic worker is disabled or delayed.
        with connection(self.path, write=True) as db:
            return [dict(row) for row in db.execute('''
                SELECT id,s_id,seat_id,used_at FROM user_seat_history
                WHERE s_id=? ORDER BY used_at DESC,id DESC LIMIT ? OFFSET ?
            ''', (s_id, limit, offset))]

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


    def update_occupancy(self, seat_id, state):
        if state not in ('OCCUPIED', 'EMPTY'):
            raise APIError(422, 'VALIDATION_ERROR', 'OCCUPIED 또는 EMPTY를 입력하세요.')
        with connection(self.path, write=True) as db:
            require(db, 'seats', seat_id)
            now = db.execute('SELECT unixepoch()').fetchone()[0]
            db.execute("""INSERT INTO seat_occupancy(seat_id,state,occupied_since,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(seat_id) DO UPDATE SET
                state=excluded.state,
                occupied_since=CASE WHEN excluded.state='OCCUPIED' THEN
                    CASE WHEN seat_occupancy.state='OCCUPIED' THEN seat_occupancy.occupied_since
                         ELSE excluded.occupied_since END ELSE NULL END,
                updated_at=excluded.updated_at""",
                (seat_id, state, now if state == 'OCCUPIED' else None, now))
            return seat_rows(db, now, seat_id=seat_id)[0]

    def device_reservation_info(self, seat_id):
        row = self.seat(seat_id)
        return {key: row[key] for key in (
            'seat_id', 'reservation_state', 'active_reservation_id',
            'starts_at', 'ends_at', 'remaining_seconds', 'next_reservation', 'server_now')}
