"""Backed-up schema migration; create dependency tables before other objects."""
import argparse
import json
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from .db import ROOT, default_path
from .schema_objects import load_schema, read_objects

# These tables contain the source reservation/location data; never reconstruct
# them as empty tables when upgrading a damaged database.
CORE_TABLES = ('floors', 'rooms', 'seats', 'reservations')

# Exact normalized SQL digests of the supported pre-seat-move trigger version.
# Keep legacy compatibility explicit; never replace arbitrary modified triggers.
PRE_MOVE_RULE_HASHES = {'reservations_validate_insert': 'c2181554b32ce61ee12b1fabd2bd417a3c483af10aed018ca583508e1ae155db',
 'reservations_validate_update': '9c6d30d344e5542fccef1110d25246584c9d6a51123524837a632b674d1aed66'}


def definitions(db):
    return {name: obj.sql for name, obj in read_objects(db).items()}


def normalize(sql):
    return ' '.join(sql.split()) if sql is not None else None


def upgrade(path: Path, backup: Path):
    path, backup = path.resolve(), backup.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path == backup:
        raise ValueError('Backup and database paths must be different.')
    latest = load_schema(ROOT/'schema.sql')
    expected = {name: obj.sql for name, obj in latest.items()}
    legacy = {name: obj.sql for name, obj in load_schema(ROOT/'api/schema_v1_3.sql').items()}
    db = sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, timeout=5)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        current = definitions(db)
        missing_core = [name for name in CORE_TABLES if name not in current]
        if missing_core:
            raise RuntimeError('Compatible KOREA database is required; missing source tables: '
                               + ', '.join(missing_core))
        for name, obj in latest.items():
            if name not in current or normalize(current[name]) == normalize(obj.sql):
                continue
            known_old = (obj.kind in ('trigger', 'view') and (
                (name in legacy and normalize(current[name]) == normalize(legacy[name]))
                or hashlib.sha256(normalize(current[name]).encode()).hexdigest()
                    == PRE_MOVE_RULE_HASHES.get(name)))
            if not known_old:
                raise RuntimeError('Partial or different schema found for object: '
                                   + name + '; inspect before migration.')
        if 'reservation_owners' in current and db.execute('''
            SELECT 1 FROM reservation_owners owner JOIN reservations r ON r.id=owner.reservation_id
            WHERE r.status='CONFIRMED' AND r.ends_at>unixepoch()
            GROUP BY owner.s_id HAVING COUNT(*)>1 LIMIT 1
        ''').fetchone():
            raise RuntimeError('Existing users have multiple active reservations. Resolve these reservations before migration; no data was changed.')
        if all(normalize(current.get(name)) == normalize(sql) for name, sql in expected.items()):
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Foreign key violations must be resolved before migration.')
            return {'status': 'already_current', 'backup': None}
        # Independent history cannot be unambiguously linked back to reservations.
        # Refuse to guess a lost cursor when retained history is nonempty.
        if ('reservation_history_progress' not in current and 'user_seat_history' in current
                and db.execute('SELECT 1 FROM user_seat_history LIMIT 1').fetchone()):
            raise RuntimeError('Cannot safely rebuild missing reservation_history_progress with existing independent history; inspect before migration.')
        with backup.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(backup)) as copy:
                db.backup(copy)
        except Exception:
            backup.unlink(missing_ok=True)
            raise
        try:
            db.execute('BEGIN IMMEDIATE')
            # No hard-coded feature table lists: every current schema table is
            # available before indexes, views, or triggers are installed.
            for kind in ('table', 'index', 'view', 'trigger'):
                for name, obj in latest.items():
                    if obj.kind != kind:
                        continue
                    if name not in current:
                        db.execute(obj.sql)
                    elif normalize(current[name]) != normalize(obj.sql):
                        # The preflight permits only recognized older triggers/views.
                        quoted = '"'+name.replace('"', '""')+'"'
                        db.execute(f'DROP {kind.upper()} {quoted}')
                        db.execute(obj.sql)
            if 'seat_occupancy' not in current:
                db.execute('INSERT INTO seat_occupancy(seat_id) SELECT id FROM seats')
            if 'reservation_moves' not in current:
                db.execute('UPDATE reservation_history_progress SET last_move_id=0')
            if 'user_seat_history' not in current:
                db.execute('DELETE FROM reservation_history_progress')
                from .seat_history import record
                record(db)
            elif 'reservation_history_progress' not in current:
                from .seat_history import record
                record(db)
            after = definitions(db)
            if not all(normalize(after.get(name)) == normalize(sql) for name, sql in expected.items()):
                raise RuntimeError('Migration schema verification failed.')
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Migration foreign key verification failed.')
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {'status': 'upgraded', 'backup': str(backup)}
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=default_path())
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(upgrade(args.database, args.backup), ensure_ascii=False))
