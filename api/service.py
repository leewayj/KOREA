import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .db import connection
from .errors import APIError
from .models import Congestion, SeatCounts
from .timing import project, EFFECTIVE_SQL


RESERVATION_SELECT = '''SELECT r.*,p.default_duration_seconds AS policy_default_duration_seconds,
    p.max_extensions,p.extension_count,p.is_legacy AS legacy_extension_policy
    FROM reservations r JOIN reservation_policies p ON p.reservation_id=r.id'''


def require(db, table, row_id):
    # table is supplied exclusively by server code, never by a request.
    row = db.execute(f'SELECT * FROM {table} WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        raise APIError(404, 'NOT_FOUND', '요청한 데이터를 찾을 수 없습니다.')
    return row


def reservation(db, reservation_id, now=None):
    now = db.execute('SELECT unixepoch()').fetchone()[0] if now is None else now
    row = db.execute(RESERVATION_SELECT + ' WHERE r.id = ?', (reservation_id,)).fetchone()
    if row is None:
        raise APIError(404, 'RESERVATION_NOT_FOUND', '예약을 찾을 수 없습니다.')
    return project(row, now)



def owned_reservation(db, reservation_id, owner_s_id):
    if owner_s_id is None:
        raise APIError(401, 'AUTH_REQUIRED', '예약을 변경하려면 로그인해야 합니다.')
    row = reservation(db, reservation_id)
    owner = db.execute('SELECT s_id FROM reservation_owners WHERE reservation_id=?',
                       (reservation_id,)).fetchone()
    if owner is None or owner['s_id'] != owner_s_id:
        raise APIError(403, 'RESERVATION_FORBIDDEN', '본인의 예약만 변경할 수 있습니다.')
    return row


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
        from .seat_state import projection
        item.update(projection(db, item, now))
        result.append(item)
    return result


def room_reservation_time(seconds):
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise APIError(503, 'STATUS_UNAVAILABLE', '예약 시각을 표시할 수 없습니다.') from error


def room_summary(seats, calculated_at):
    statuses = Counter(seat['seat_status'] for seat in seats)
    total = len(seats)
    unknown = statuses['UNKNOWN']
    valid = total - unknown
    available = statuses['AVAILABLE']
    reserved_empty = statuses['RESERVED_EMPTY']
    occupied = valid - available - reserved_empty
    counts = SeatCounts(total=total, valid=valid, occupied=occupied, available=available,
                        reservedEmpty=reserved_empty, unknown=unknown)

    if total == 0:
        reason = 'NO_SEATS'
    elif valid == 0:
        reason = 'NO_VALID_SEATS'
    elif valid * 100 < total * 80:
        reason = 'LOW_COVERAGE'
    else:
        # Apply thresholds to the exact fraction, then round for display.
        scaled = occupied * 100
        if scaled < valid * 30:
            level = 'LOW'
        elif scaled < valid * 70:
            level = 'MODERATE'
        else:
            level = 'HIGH'
        percent = (2 * scaled + valid) // (2 * valid)
        return counts, Congestion(status='OK', reason=None, level=level, percent=percent,
                                  calculatedAt=calculated_at)

    return counts, Congestion(status='INSUFFICIENT_DATA', reason=reason, level=None,
                              percent=None, calculatedAt=calculated_at)


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

    def room_status(self, room_id):
        try:
            with connection(self.path) as db:
                room = db.execute('SELECT id, name FROM rooms WHERE id=?', (room_id,)).fetchone()
                if room is None:
                    raise APIError(404, 'ROOM_NOT_FOUND', '열람실을 찾을 수 없습니다.')
                now = db.execute('SELECT unixepoch()').fetchone()[0]
                # SQLite LIMIT -1 reads every seat rather than one page.
                seats = seat_rows(db, now, room_id=room_id, limit=-1)
                simulated = db.execute("""SELECT EXISTS(
                    SELECT 1 FROM seats s JOIN seat_device_reports d ON d.seat_id=s.id
                    WHERE s.room_id=? AND d.device_kind='VIRTUAL')""", (room_id,)).fetchone()[0]
        except APIError as error:
            if isinstance(error.__cause__, sqlite3.Error):
                raise APIError(503, 'STATUS_UNAVAILABLE', '열람실 현황을 조회할 수 없습니다.') from error
            raise

        calculated_at = datetime.fromtimestamp(now, UTC)
        counts, congestion = room_summary(seats, calculated_at)
        # Convert database seconds before the response model can infer milliseconds.
        for seat in seats:
            seat['starts_at'] = room_reservation_time(seat['starts_at'])
            seat['ends_at'] = room_reservation_time(seat['ends_at'])
            upcoming = seat['next_reservation']
            if upcoming is not None:
                upcoming['starts_at'] = room_reservation_time(upcoming['starts_at'])
                upcoming['ends_at'] = room_reservation_time(upcoming['ends_at'])
        return {'room': dict(room), 'serverTime': calculated_at, 'seatCounts': counts,
                'congestion': congestion, 'hasSimulatedData': bool(simulated), 'seats': seats}

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
                {RESERVATION_SELECT}
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
                def_time = db.execute('SELECT default_duration_seconds FROM reservation_settings WHERE id=1').fetchone()[0]
            # Read settings, insert the reservation/policy and ownership in one write transaction.
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
            return [project(row,now) for row in db.execute(f'''
                {RESERVATION_SELECT}
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

    def extend(self, reservation_id, *, owner_s_id):
        with connection(self.path, write=True) as db:
            row = owned_reservation(db, reservation_id, owner_s_id)
            now = db.execute('SELECT unixepoch()').fetchone()[0]
            if row['status'] != 'CONFIRMED' or row['effective_status'] != 'IN_USE':
                raise APIError(409, 'RESERVATION_CLOSED', '종료·취소·만료된 예약은 수정할 수 없습니다.')
            duration = row['def_time'] + row['policy_default_duration_seconds']
            if duration > 9223372036854775807 - row['starts_at']:
                raise APIError(422, 'INVALID_DURATION', '이용시간이 저장 가능한 범위를 초과합니다.')
            if row['starts_at'] + duration <= now:
                raise APIError(422, 'INVALID_DURATION', '변경할 종료 시각은 현재 시각 이후여야 합니다.')
            db.execute('UPDATE reservations SET def_time = ? WHERE id = ?', (duration, reservation_id))
            return reservation(db, reservation_id)

    def transition(self, reservation_id, status, *, owner_s_id):
        with connection(self.path, write=True) as db:
            row = owned_reservation(db, reservation_id, owner_s_id)
            if row['status'] == status:
                return row  # Safe repeat: preserve the original transition timestamp.
            allowed = {'CANCELLED': 'SCHEDULED', 'ENDED': 'IN_USE'}
            if row['status'] != 'CONFIRMED' or row['effective_status'] != allowed.get(status):
                raise APIError(409, 'RESERVATION_CLOSED', '예정 예약은 취소만, 사용 중 예약은 종료만 가능합니다.')
            db.execute('UPDATE reservations SET status = ? WHERE id = ?', (status, reservation_id))
            return reservation(db, reservation_id)

    def move(self, reservation_id, target_seat_id, *, owner_s_id):
        with connection(self.path, write=True) as db:
            row = owned_reservation(db, reservation_id, owner_s_id)
            if row['status'] != 'CONFIRMED' or row['effective_status'] not in ('SCHEDULED', 'IN_USE'):
                raise APIError(409, 'RESERVATION_CLOSED', '예정 또는 사용 중 예약만 이동할 수 있습니다.')
            require(db, 'seats', target_seat_id)
            if row['seat_id'] == target_seat_id:
                return row
            # The DB checks the remaining interval and atomically records move history.
            db.execute('UPDATE reservations SET seat_id = ? WHERE id = ?', (target_seat_id, reservation_id))
            return reservation(db, reservation_id)


    def update_occupancy(self, seat_id, state, led_state=None):
        if state not in ('OCCUPIED', 'EMPTY', 'SENSOR_ERROR'):
            raise APIError(422, 'VALIDATION_ERROR', '착석 상태 값이 올바르지 않습니다.')
        if led_state not in (None, 'OFF', 'BLUE_ON', 'ORANGE_ON', 'RED_BLINK'):
            raise APIError(422, 'VALIDATION_ERROR', 'LED 적용 상태 값이 올바르지 않습니다.')
        from .seat_state import record_report
        with connection(self.path, write=True) as db:
            require(db, 'seats', seat_id)
            now = db.execute('SELECT unixepoch()').fetchone()[0]
            record_report(db, seat_id, state, led_state, now)
            return seat_rows(db, now, seat_id=seat_id)[0]

    def reset_device_continuity(self):
        from .seat_state import reset_after_restart
        with connection(self.path, write=True) as db:
            reset_after_restart(db)

    def device_reservation_info(self, seat_id):
        row = self.seat(seat_id)
        return {key: row[key] for key in (
            'seat_status', 'target_led', 'seat_id', 'reservation_state', 'active_reservation_id',
            'starts_at', 'ends_at', 'remaining_seconds', 'next_reservation', 'server_now')}
