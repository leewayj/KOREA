"""One independent final-seat history row per reservation."""
from collections import Counter


def record(db, now=None):
    now = db.execute('SELECT unixepoch()').fetchone()[0] if now is None else now
    rows = db.execute('''SELECT r.id,o.s_id,r.seat_id,r.starts_at,r.ends_at,r.status,
        r.status_changed_at,p.last_move_id,p.history_id
        FROM reservations r JOIN reservation_owners o ON o.reservation_id=r.id
        LEFT JOIN reservation_history_progress p ON p.reservation_id=r.id
        WHERE r.starts_at<=? AND
        (r.status='CONFIRMED' OR MIN(r.ends_at,r.status_changed_at)>r.starts_at)
        ORDER BY r.id''', (now,)).fetchall()
    inserted = 0
    for rid, student, seat, start, end, status, changed, last_move, history_id in rows:
        if last_move is None:
            first = db.execute('SELECT from_seat_id FROM reservation_moves WHERE reservation_id=? ORDER BY id LIMIT 1', (rid,)).fetchone()
            cursor = db.execute('INSERT INTO user_seat_history(s_id,seat_id,used_at) VALUES(?,?,?)',
                                (student, first[0] if first else seat, start))
            history_id = cursor.lastrowid
            db.execute('INSERT INTO reservation_history_progress(reservation_id,history_id) VALUES(?,?)', (rid, history_id))
            last_move = 0
            inserted += 1
        cutoff = min(now, end, changed) if status in ('ENDED','CANCELLED') else min(now,end)
        move = db.execute('''SELECT id,to_seat_id,moved_at FROM reservation_moves
            WHERE reservation_id=? AND id>? AND moved_at<=? ORDER BY id DESC LIMIT 1''',
            (rid,last_move,cutoff)).fetchone()
        if move:
            move_id,destination,moved_at = move
            if history_id is None:
                # Preserve ambiguous legacy records; link future movement independently.
                history_id = db.execute('INSERT INTO user_seat_history(s_id,seat_id,used_at) VALUES(?,?,?)',
                                        (student,destination,moved_at)).lastrowid
                inserted += 1
            else:
                db.execute('UPDATE user_seat_history SET seat_id=?,used_at=? WHERE id=? AND s_id=?',
                           (destination,moved_at,history_id,student))
            last_move = move_id
        db.execute('UPDATE reservation_history_progress SET last_move_id=?,history_id=? WHERE reservation_id=?',
                   (last_move,history_id,rid))
    return inserted


def migrate_links(db):
    """Collapse fully unique legacy matches, preserving unidentifiable records."""
    sources = db.execute('''SELECT p.reservation_id,p.last_move_id,o.s_id,r.seat_id,r.starts_at
        FROM reservation_history_progress p JOIN reservations r ON r.id=p.reservation_id
        JOIN reservation_owners o ON o.reservation_id=r.id WHERE p.history_id IS NULL
        ORDER BY p.reservation_id''').fetchall()
    events_by_reservation = []
    references = Counter()
    for rid,last_move,student,seat,start in sources:
        first = db.execute('SELECT from_seat_id FROM reservation_moves WHERE reservation_id=? ORDER BY id LIMIT 1', (rid,)).fetchone()
        events = [(student,first[0] if first else seat,start)]
        events.extend((student,dest,at) for dest,at in db.execute(
            'SELECT to_seat_id,moved_at FROM reservation_moves WHERE reservation_id=? AND id<=? ORDER BY id', (rid,last_move)))
        references.update(events)
        events_by_reservation.append((rid,events))
    linked = removed = 0
    for rid,events in events_by_reservation:
        ids = []
        for event in events:
            candidates = db.execute('SELECT id FROM user_seat_history WHERE s_id=? AND seat_id=? AND used_at=?', event).fetchall()
            if references[event] != 1 or len(candidates) != 1:
                break
            ids.append(candidates[0][0])
        else:
            db.execute('UPDATE reservation_history_progress SET history_id=? WHERE reservation_id=?', (ids[-1],rid))
            for history_id in ids[:-1]:
                db.execute('DELETE FROM user_seat_history WHERE id=?', (history_id,))
                removed += 1
            linked += 1
    unresolved = db.execute('SELECT COUNT(*) FROM reservation_history_progress WHERE history_id IS NULL').fetchone()[0]
    return {'linked_reservations':linked,'removed_previous_seat_events':removed,'unresolved_preserved':unresolved}
