"""Shared reservation-time projection. No sensor or LED assumptions."""
EFFECTIVE_SQL = """CASE WHEN status='CANCELLED' THEN 'CANCELLED'
    WHEN status='ENDED' OR ends_at<=:now THEN 'ENDED'
    WHEN starts_at>:now THEN 'SCHEDULED' ELSE 'IN_USE' END"""
MESSAGES = {
    'RESERVATION_ENDING_SOON': '예약 종료까지 10분 이내로 남았습니다. 이용 종료를 준비해 주세요.',
    'RESERVATION_ENDED': '예약 이용 시간이 종료되었습니다.',
    'RESERVATION_CANCELLED': '예약이 취소되었습니다.',
}


def project(row, now):
    result = dict(row)
    status = result['status']
    if status == 'CANCELLED':
        effective = 'CANCELLED'
    elif status == 'ENDED' or result['ends_at'] <= now:
        effective = 'ENDED'
    elif result['starts_at'] > now:
        effective = 'SCHEDULED'
    else:
        effective = 'IN_USE'
    remaining = max(result['ends_at'] - now, 0) if effective == 'IN_USE' else (0 if effective in ('ENDED', 'CANCELLED') else None)
    code = ('RESERVATION_CANCELLED' if effective == 'CANCELLED' else
            'RESERVATION_ENDED' if effective == 'ENDED' else
            'RESERVATION_ENDING_SOON' if effective == 'IN_USE' and remaining <= 600 else None)
    result.update(effective_status=effective, server_now=now, remaining_seconds=remaining,
                  notice_code=code, notice_message=MESSAGES.get(code))
    return result


def reconcile(db, now=None):
    now = db.execute('SELECT unixepoch()').fetchone()[0] if now is None else now
    from .seat_history import record
    record(db, now)
    rows = db.execute('SELECT * FROM reservations').fetchall()
    for row in rows:
        value = project(row, now)
        db.execute('''INSERT INTO reservation_time_states VALUES(?,?,?,?)
            ON CONFLICT(reservation_id) DO UPDATE SET effective_status=excluded.effective_status,
                notice_code=excluded.notice_code,evaluated_at=excluded.evaluated_at''',
            (value['id'], value['effective_status'], value['notice_code'], now))
    return len(rows)
