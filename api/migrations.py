"""Backed-up seat-move, ID-auth and administrator migration; existing rows are preserved."""
import argparse
import json
import sqlite3
from pathlib import Path

from .db import ROOT, default_path

SEAT_OBJECTS = ('reservation_moves', 'reservation_moves_reservation',
                'reservations_validate_insert', 'reservations_validate_update', 'reservations_record_move')
AUTH_OBJECTS = ('users', 'auth_sessions', 'auth_sessions_user', 'auth_sessions_expiry')
ADMIN_OBJECTS = ('admins', 'admin_sessions', 'admin_sessions_expiry', 'reservation_admin_context')
OWNER_OBJECTS = ('reservation_owners', 'reservation_owners_user')
ACTIVE_OBJECTS = ('reservation_owners_one_active', 'reservation_owners_immutable', 'reservations_one_active_user')
OBJECTS = SEAT_OBJECTS + AUTH_OBJECTS + ADMIN_OBJECTS + OWNER_OBJECTS + ACTIVE_OBJECTS + ('reservation_status',)


def definitions(db):
    return dict(db.execute('SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL'))


def normalize(sql):
    return ' '.join(sql.split()) if sql is not None else None


def upgrade(path: Path, backup: Path):
    path, backup = path.resolve(), backup.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path == backup:
        raise ValueError('Backup and database paths must be different.')
    with sqlite3.connect(':memory:') as template:
        template.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        expected = definitions(template)
    with sqlite3.connect(':memory:') as template:
        template.executescript((ROOT / 'api' / 'schema_v1_3.sql').read_text(encoding='utf-8'))
        legacy = definitions(template)
    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        current = definitions(db)
        if all(normalize(current.get(name)) == normalize(expected[name]) for name in OBJECTS):
            return {'status': 'already_current', 'backup': None}
        seat_current = all(normalize(current.get(name)) in (normalize(expected[name]), normalize(legacy[name])) for name in SEAT_OBJECTS)
        auth_current = all(normalize(current.get(name)) == normalize(expected[name]) for name in AUTH_OBJECTS)
        admin_current = all(normalize(current.get(name)) == normalize(expected[name]) for name in ADMIN_OBJECTS)
        owner_current = all(normalize(current.get(name)) == normalize(expected[name]) for name in OWNER_OBJECTS)
        active_current = all(normalize(current.get(name)) == normalize(expected[name]) for name in ACTIVE_OBJECTS)
        if not seat_current and ('reservation_moves' in current or 'reservations_record_move' in current):
            raise RuntimeError('Partial or different seat-move schema found; inspect before migration.')
        if not auth_current and any(name in current for name in AUTH_OBJECTS):
            raise RuntimeError('Partial or different ID-auth schema found; inspect before migration.')
        if not admin_current and any(name in current for name in ADMIN_OBJECTS):
            raise RuntimeError('Partial or different admin schema found; inspect before migration.')
        if not owner_current and any(name in current for name in OWNER_OBJECTS):
            raise RuntimeError('Partial or different reservation ownership schema found; inspect before migration.')
        if not active_current and any(name in current for name in ACTIVE_OBJECTS):
            raise RuntimeError('Partial or different single-active schema found; inspect before migration.')
        if 'reservation_owners' in current and db.execute('''
            SELECT 1 FROM reservation_owners owner JOIN reservations r ON r.id=owner.reservation_id
            WHERE r.status='CONFIRMED' AND r.ends_at>unixepoch()
            GROUP BY owner.s_id HAVING COUNT(*)>1 LIMIT 1
        ''').fetchone():
            raise RuntimeError('Existing users have multiple active reservations. Resolve these reservations before migration; no data was changed.')
        if normalize(current.get('reservation_status')) not in (normalize(expected['reservation_status']), normalize(legacy['reservation_status'])):
            raise RuntimeError('Different reservation status view found; inspect before migration.')
        if not all(name in current for name in ('reservations', 'seats', 'reservations_validate_insert', 'reservations_validate_update')):
            raise RuntimeError('Compatible KOREA database is required.')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Foreign key violations must be resolved before migration.')
        # Exclusive creation: never replace an existing backup.
        with backup.open('xb'):
            pass
        try:
            with sqlite3.connect(backup) as copy:
                db.backup(copy)
        except Exception:
            backup.unlink(missing_ok=True)
            raise
        try:
            db.execute('BEGIN IMMEDIATE')
            if not seat_current:
                db.execute(expected['reservation_moves'])
                db.execute(expected['reservation_moves_reservation'])
            if not admin_current:
                for name in ADMIN_OBJECTS:
                    db.execute(expected[name])
            for name in ('reservations_validate_insert', 'reservations_validate_update', 'reservations_record_move'):
                if normalize(current.get(name)) != normalize(expected[name]):
                    db.execute(f'DROP TRIGGER IF EXISTS {name}')
                    db.execute(expected[name])
            if not auth_current:
                for name in AUTH_OBJECTS:
                    db.execute(expected[name])
            if not owner_current:
                for name in OWNER_OBJECTS:
                    db.execute(expected[name])
            if not active_current:
                for name in ACTIVE_OBJECTS:
                    db.execute(expected[name])
            if normalize(current.get('reservation_status')) != normalize(expected['reservation_status']):
                db.execute('DROP VIEW reservation_status')
                db.execute(expected['reservation_status'])
            after = definitions(db)
            if not all(normalize(after.get(name)) == normalize(expected[name]) for name in OBJECTS):
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
