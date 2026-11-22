import argparse
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import database_error
from .schema_objects import load_schema, read_objects

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
            # Capture due events before edits/deletion can remove their sources.
            from .seat_history import record
            record(db)
        else:
            db.execute('BEGIN')
        yield db
        if write:
            if db.execute('SELECT 1 FROM reservation_admin_context LIMIT 1').fetchone():
                raise RuntimeError('Administrator context must be cleared before commit.')
            if db.execute('SELECT 1 FROM reservation_admin_insert_context LIMIT 1').fetchone():
                raise RuntimeError('Administrator insert context must be cleared before commit.')
            from .timing import reconcile
            reconcile(db)
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
        actual = read_objects(db)
        definitions = {name: obj.sql for name, obj in actual.items()}
        expected = load_schema(ROOT/'schema.sql')
        missing = [name for name in expected if name not in actual]
        if missing:
            raise RuntimeError('Incompatible database: missing required objects: '
                               + ', '.join(missing)
                               + '. Back up and run python -m api.migrations --backup <backup.db>.')
        wrong_types = [name for name, obj in expected.items() if actual[name].kind != obj.kind]
        if wrong_types:
            raise RuntimeError('Incompatible database: unexpected object types: '+', '.join(wrong_types))
        if ("'CONFIRMED'" not in definitions['reservations']
                or 'starts_at is immutable' not in definitions['reservations_validate_update']
                or 'confirmed_at is immutable' not in definitions['reservations_validate_update']
                or 'reservation must start at current time' not in definitions['reservations_validate_insert']):
            raise RuntimeError('Incompatible reservation rules; use the current KOREA schema.')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Database contains foreign key violations.')
        for name in ('reservations_validate_update', 'reservations_record_move'):
            if ' '.join(definitions[name].split()) != ' '.join(expected[name].sql.split()):
                raise RuntimeError('Reservation state rules require migration: '+name)
        if db.execute('SELECT COUNT(*) FROM reservation_settings WHERE id=1').fetchone()[0] != 1:
            raise RuntimeError('Reservation settings are missing; inspect the database before startup.')
        if db.execute('''SELECT 1 FROM reservations r LEFT JOIN reservation_policies p
                         ON p.reservation_id=r.id WHERE p.reservation_id IS NULL LIMIT 1''').fetchone():
            raise RuntimeError('Reservation policy snapshot is missing; back up and run migration.')
        db.execute('''SELECT default_duration_seconds,max_extensions,extension_count,is_legacy
                      FROM reservation_policies LIMIT 0''')
        if db.execute('SELECT 1 FROM reservation_admin_context LIMIT 1').fetchone():
            raise RuntimeError('Unexpected persisted administrator context.')
        if db.execute('SELECT 1 FROM reservation_admin_insert_context LIMIT 1').fetchone():
            raise RuntimeError('Unexpected persisted administrator insert context.')
        if 'led_state' not in {r[1] for r in db.execute('PRAGMA table_info(seat_device_reports)')}:
            raise RuntimeError('LED field rename requires database migration.')
        db.execute('SELECT seat_id,device_kind,received_at,led_state,led_state_updated_at,tracked_reservation_id,tracked_starts_at,tracked_ends_at FROM seat_device_reports LIMIT 0')
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
