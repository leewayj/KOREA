import argparse
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import database_error

ROOT = Path(__file__).resolve().parents[1]


def default_path() -> Path:
    return Path(os.environ.get('KOREA_DB_PATH', str(ROOT / 'library.db'))).resolve()


@contextmanager
def connection(path: Path, write=False):
    db = None
    try:
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA busy_timeout = 5000')
        if write:
            db.execute('BEGIN IMMEDIATE')
        yield db
        if write:
            if db.execute('SELECT 1 FROM reservation_admin_context LIMIT 1').fetchone():
                raise RuntimeError('Administrator context must be cleared before commit.')
            db.commit()
    except sqlite3.Error as error:
        if db is not None:
            db.rollback()
        raise database_error(error) from error
    except Exception:
        if db is not None:
            db.rollback()
        raise
    finally:
        if db is not None:
            db.close()


def validate(path: Path):
    if not path.is_file():
        raise RuntimeError(f'Database not found: {path}. Run python -m api.db init --demo first.')
    with connection(path) as db:
        definitions = {row['name']: row['sql'] for row in db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table','view','trigger')")}
        required = ('floors', 'rooms', 'seats', 'reservations', 'seat_occupancy',
                    'reservation_status', 'seat_status', 'reservations_validate_insert',
                    'reservations_validate_update', 'reservations_stamp_status', 'seats_initialize_occupancy',
                    'reservation_moves', 'reservations_record_move', 'users', 'auth_sessions',
                    'admins', 'admin_sessions', 'reservation_admin_context', 'reservation_owners',
                    'reservation_owners_one_active', 'reservation_owners_immutable', 'reservations_one_active_user')
        if not all(name in definitions for name in required):
            raise RuntimeError('Incompatible database: seat-move schema, ID-auth schema, admin schema and reservation ownership schema are required. Back up and run python -m api.migrations --backup <backup.db>.')
        if ("'CONFIRMED'" not in definitions['reservations']
                or 'starts_at is immutable' not in definitions['reservations_validate_update']
                or 'confirmed_at is immutable' not in definitions['reservations_validate_update']
                or 'reservation must start at current time' not in definitions['reservations_validate_insert']):
            raise RuntimeError('Incompatible reservation rules; use the current KOREA schema.')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Database contains foreign key violations.')
        if db.execute('SELECT 1 FROM reservation_admin_context LIMIT 1').fetchone():
            raise RuntimeError('Unexpected persisted administrator context.')
        db.execute('SELECT * FROM seat_status LIMIT 0')
        db.execute('SELECT * FROM reservation_status LIMIT 0')


def initialize(path: Path, demo=False):
    path = path.resolve()
    # Refuse to replace any existing file, including legacy databases.
    with path.open('xb'):
        pass
    db = None
    try:
        db = sqlite3.connect(path)
        db.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        if demo:
            db.executescript((ROOT / 'seed.sql').read_text(encoding='utf-8'))
        db.close()
        db = None
        validate(path)
    except Exception:
        if db is not None:
            db.close()
        path.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create a new KOREA database; never overwrites existing files.')
    parser.add_argument('command', choices=['init'])
    parser.add_argument('--demo', action='store_true', help='Load the 8-seat seed data')
    parser.add_argument('--output', type=Path, default=default_path())
    args = parser.parse_args()
    initialize(args.output, args.demo)
    print(f'Created: {args.output.resolve()}')
