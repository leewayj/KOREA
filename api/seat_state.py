"""Server seat/LED projection and conservative sensor continuity evidence."""

LEDS = {'RESERVED_EMPTY': 'BLUE_ON', 'EXPIRING_OCCUPIED': 'ORANGE_ON',
        'EXPIRED_OCCUPIED': 'RED_BLINK'}
TIMEOUT = 10


def connected(report, now):
    return bool(report and report['received_at'] is not None
                and 0 <= now-report['received_at'] <= TIMEOUT)


def reliable(report, now):
    return bool(report and report['received_at'] is not None and
                (report['device_kind'] == 'VIRTUAL' or connected(report, now)))


def clear_tracking(db, seat_id):
    db.execute('''UPDATE seat_device_reports SET tracked_reservation_id=NULL,
                  tracked_starts_at=NULL,tracked_ends_at=NULL WHERE seat_id=?''', (seat_id,))


def reconcile_devices(db, now):
    reports = db.execute('''SELECT d.*,o.state FROM seat_device_reports d
                           JOIN seat_occupancy o ON o.seat_id=d.seat_id''').fetchall()
    for report in reports:
        sid = report['seat_id']
        if not reliable(report, now) or report['state'] != 'OCCUPIED':
            clear_tracking(db, sid)
            continue
        active = db.execute('''SELECT id,starts_at,ends_at FROM reservations
            WHERE seat_id=? AND status='CONFIRMED' AND starts_at<=? AND ?<ends_at''',
            (sid, now, now)).fetchone()
        if active:
            # Require an occupied report during this booking, not before its start.
            if report['received_at'] >= active['starts_at']:
                db.execute('''UPDATE seat_device_reports SET tracked_reservation_id=?,
                    tracked_starts_at=?,tracked_ends_at=? WHERE seat_id=?''',
                    (active['id'], active['starts_at'], active['ends_at'], sid))
            else:
                clear_tracking(db, sid)
        elif report['tracked_reservation_id'] is not None:
            old = db.execute('''SELECT 1 FROM reservations WHERE id=? AND seat_id=?
                AND status='CONFIRMED' AND starts_at=? AND ends_at=? AND ends_at<=?''',
                (report['tracked_reservation_id'], sid, report['tracked_starts_at'],
                 report['tracked_ends_at'], now)).fetchone()
            # Deletion, cancellation, early ending, moving or retiming is not expiry.
            if not old:
                clear_tracking(db, sid)


def record_report(db, seat_id, state, led_state, now):
    previous = db.execute('SELECT * FROM seat_device_reports WHERE seat_id=?', (seat_id,)).fetchone()
    continuing = reliable(previous, now)
    if not continuing or state != 'OCCUPIED':
        clear_tracking(db, seat_id)
    db.execute('''INSERT INTO seat_occupancy(seat_id,state,occupied_since,updated_at)
        VALUES(?,?,?,?) ON CONFLICT(seat_id) DO UPDATE SET state=excluded.state,
        occupied_since=CASE WHEN excluded.state='OCCUPIED' THEN
            CASE WHEN seat_occupancy.state='OCCUPIED' AND ? THEN seat_occupancy.occupied_since
                 ELSE excluded.occupied_since END ELSE NULL END,updated_at=excluded.updated_at''',
        (seat_id, state, now if state == 'OCCUPIED' else None, now, continuing))
    db.execute('''INSERT INTO seat_device_reports(seat_id,received_at,led_state,led_state_updated_at)
        VALUES(?,?,?,?) ON CONFLICT(seat_id) DO UPDATE SET received_at=excluded.received_at,
        led_state=COALESCE(excluded.led_state,seat_device_reports.led_state),
        led_state_updated_at=COALESCE(excluded.led_state_updated_at,seat_device_reports.led_state_updated_at)''',
        (seat_id, now, led_state, now if led_state is not None else None))
    reconcile_devices(db, now)


def projection(db, seat, now):
    report = db.execute('SELECT * FROM seat_device_reports WHERE seat_id=?', (seat['seat_id'],)).fetchone()
    active = seat['active_reservation_id'] is not None
    occupancy = seat['occupancy_state']
    if not reliable(report, now) or occupancy not in ('EMPTY', 'OCCUPIED'):
        status = 'UNKNOWN'
    elif occupancy == 'EMPTY':
        status = 'RESERVED_EMPTY' if active else 'AVAILABLE'
    elif active:
        status = 'EXPIRING_OCCUPIED' if 0 < seat['remaining_seconds'] <= 600 else 'RESERVED_OCCUPIED'
    else:
        expired = False
        if report['tracked_reservation_id'] is not None:
            expired = bool(db.execute('''SELECT 1 FROM reservations WHERE id=? AND seat_id=?
                AND status='CONFIRMED' AND starts_at=? AND ends_at=? AND ends_at<=?''',
                (report['tracked_reservation_id'], seat['seat_id'], report['tracked_starts_at'],
                 report['tracked_ends_at'], now)).fetchone())
        status = 'EXPIRED_OCCUPIED' if expired else 'UNRESERVED_OCCUPIED'
    return {'seat_status': status, 'target_led': LEDS.get(status, 'OFF'),
            'led_state': report['led_state'] if report else None,
            'led_state_updated_at': report['led_state_updated_at'] if report else None,
            'device_connected': connected(report, now) if not report or report['device_kind']=='REAL' else False}


def reset_after_restart(db):
    # Preserve the last hardware ACK for audit; require a new real sensor report.
    db.execute('''UPDATE seat_device_reports SET received_at=CASE WHEN device_kind='REAL'
        THEN NULL ELSE received_at END,tracked_reservation_id=NULL,
        tracked_starts_at=NULL,tracked_ends_at=NULL''')
