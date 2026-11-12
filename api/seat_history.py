"""Append independent usage events once, inside the caller's write transaction."""


def record(db, now=None):
    now = db.execute('SELECT unixepoch()').fetchone()[0] if now is None else now
    rows = db.execute('''
        SELECT r.id,owner.s_id,r.seat_id,r.starts_at,r.ends_at,r.status,r.status_changed_at,
               progress.last_move_id
        FROM reservations r JOIN reservation_owners owner ON owner.reservation_id=r.id
        LEFT JOIN reservation_history_progress progress ON progress.reservation_id=r.id
        WHERE r.starts_at<=:now AND
            (r.status='CONFIRMED' OR MIN(r.ends_at,r.status_changed_at)>r.starts_at)
        ORDER BY r.id
    ''', {'now': now}).fetchall()
    inserted = 0
    for rid, student, seat, start, end, status, changed, last_move in rows:
        if last_move is None:
            first = db.execute('''SELECT from_seat_id FROM reservation_moves
                WHERE reservation_id=? ORDER BY id LIMIT 1''', (rid,)).fetchone()
            db.execute('INSERT INTO user_seat_history(s_id,seat_id,used_at) VALUES(?,?,?)',
                       (student, first[0] if first else seat, start))
            db.execute('INSERT INTO reservation_history_progress(reservation_id) VALUES(?)', (rid,))
            last_move = 0
            inserted += 1
        cutoff = min(now, end)
        if status in ('ENDED', 'CANCELLED'):
            cutoff = min(cutoff, changed)
        moves = db.execute('''SELECT id,to_seat_id,moved_at FROM reservation_moves
            WHERE reservation_id=? AND id>? AND moved_at<=? ORDER BY id''',
            (rid, last_move, cutoff)).fetchall()
        for move_id, destination, moved_at in moves:
            db.execute('INSERT INTO user_seat_history(s_id,seat_id,used_at) VALUES(?,?,?)',
                       (student, destination, moved_at))
            last_move = move_id
            inserted += 1
        db.execute('UPDATE reservation_history_progress SET last_move_id=? WHERE reservation_id=?',
                   (last_move, rid))
    return inserted
