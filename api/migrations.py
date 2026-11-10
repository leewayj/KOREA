"""Backed-up, additive seat-move schema migration. No reservation rows are rewritten."""
import argparse
import json
import sqlite3
from pathlib import Path

from .db import ROOT, default_path

OBJECTS = ('reservation_moves', 'reservation_moves_reservation',
           'reservations_validate_insert', 'reservations_validate_update', 'reservations_record_move')


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
    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        current = definitions(db)
        if all(normalize(current.get(name)) == normalize(expected[name]) for name in OBJECTS):
            return {'status': 'already_current', 'backup': None}
        if 'reservation_moves' in current or 'reservations_record_move' in current:
            raise RuntimeError('Partial or different seat-move schema found; inspect before migration.')
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
            db.execute(expected['reservation_moves'])
            db.execute(expected['reservation_moves_reservation'])
            for name in ('reservations_validate_insert', 'reservations_validate_update'):
                db.execute(f'DROP TRIGGER {name}')
                db.execute(expected[name])
            db.execute(expected['reservations_record_move'])
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
