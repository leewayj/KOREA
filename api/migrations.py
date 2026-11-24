"""Schema migration; create dependency tables before other objects."""
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


# Exact preceding state-policy trigger definitions.
PRE_STATE_POLICY_HASHES = {'reservations_validate_update': 'ff378f88c965a666278ec988c4de3a5d01c65efab8fa70083bc43f1919cdd700', 'reservations_record_move': '06a32c5bc979c0131347442aad775c3a210d31de3a892078d8601b91cc5109ff'}

# Exact preceding telemetry table; rename columns without rebuilding data.
PRE_LED_TABLE_HASH = 'e61cefc1481e6326ae4dae8b32b8ffcb90ecaf6d408093f09a3ad077d2026d0e'

PRE_FINAL_HISTORY_HASH = '1eb866c01b75ad68fbe6835207ca67174229e71ebbf4eafddbc593dd00d191e0'

def definitions(db):
    return {name: obj.sql for name, obj in read_objects(db).items()}


def normalize(sql):
    if sql is None:
        return None
    # SQLite versions differ in quoting identifiers after RENAME COLUMN.
    result = ' '.join(sql.split()).replace('"led_state"', 'led_state').replace('"led_state_updated_at"', 'led_state_updated_at').replace(' ,', ',')
    if result.startswith('CREATE TABLE reservation_history_progress '):
        result = result[:-1].rstrip()+')'
    return result


def upgrade(path: Path, backup: Path | None):
    path = path.resolve()
    backup = backup.resolve() if backup is not None else None
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
        rename_led = ('seat_device_reports' in current and
            hashlib.sha256(normalize(current['seat_device_reports']).encode()).hexdigest() == PRE_LED_TABLE_HASH)
        upgrade_history = ('reservation_history_progress' in current and
            hashlib.sha256(normalize(current['reservation_history_progress']).encode()).hexdigest() == PRE_FINAL_HISTORY_HASH)
        history_result = None
        missing_core = [name for name in CORE_TABLES if name not in current]
        if missing_core:
            raise RuntimeError('Compatible KOREA database is required; missing source tables: '
                               + ', '.join(missing_core))
        if ('reservation_settings' in current and
                db.execute('SELECT COUNT(*) FROM reservation_settings WHERE id=1').fetchone()[0] != 1):
            raise RuntimeError('Existing reservation settings are missing; inspect before migration.')
        if ('reservation_policies' in current and db.execute('''
            SELECT 1 FROM reservations r LEFT JOIN reservation_policies p ON p.reservation_id=r.id
            WHERE p.reservation_id IS NULL LIMIT 1
        ''').fetchone()):
            raise RuntimeError('Existing reservation policy snapshot is missing; inspect before migration.')
        for name, obj in latest.items():
            if name not in current or normalize(current[name]) == normalize(obj.sql):
                continue
            known_old = (obj.kind in ('trigger', 'view') and (
                (name in legacy and normalize(current[name]) == normalize(legacy[name]))
                or hashlib.sha256(normalize(current[name]).encode()).hexdigest()
                    in (PRE_MOVE_RULE_HASHES.get(name), PRE_STATE_POLICY_HASHES.get(name))))
            known_old = known_old or (name == 'seat_device_reports' and rename_led)
            known_old = known_old or (name == 'reservation_history_progress' and upgrade_history)
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
        if backup is not None:
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
            if upgrade_history:
                db.execute('ALTER TABLE reservation_history_progress ADD COLUMN history_id INTEGER REFERENCES user_seat_history(id) ON DELETE SET NULL')
                current = definitions(db)
                if normalize(current['reservation_history_progress']) != normalize(expected['reservation_history_progress']):
                    raise RuntimeError('History schema verification failed.')
            if rename_led:
                db.execute('ALTER TABLE seat_device_reports RENAME COLUMN applied_led TO led_state')
                db.execute('ALTER TABLE seat_device_reports RENAME COLUMN applied_led_updated_at TO led_state_updated_at')
                current = definitions(db)
                if normalize(current['seat_device_reports']) != normalize(expected['seat_device_reports']):
                    raise RuntimeError('LED column rename schema verification failed; no data was changed.')
            # No hard-coded feature table lists: every current schema table is
            # available before indexes, views, or triggers are installed.
            for kind in ('table', 'index', 'view', 'trigger'):
                for name, obj in latest.items():
                    if obj.kind != kind:
                        continue
                    if name not in current:
                        db.execute(obj.sql)
                    elif normalize(current[name]) != normalize(obj.sql):
                        if kind == 'table':
                            raise RuntimeError('Refusing to rebuild an existing source table: '+name)
                        # The preflight permits only recognized older triggers/views.
                        quoted = '"'+name.replace('"', '""')+'"'
                        db.execute(f'DROP {kind.upper()} {quoted}')
                        db.execute(obj.sql)
            if 'reservation_settings' not in current:
                db.execute('''INSERT INTO reservation_settings(id,default_duration_seconds,max_extensions)
                              VALUES(1,21600,2)''')
            if 'reservation_policies' not in current:
                # Legacy bookings had no extension cap. Preserve that policy;
                # zero counts only extensions after this migration, not inferred history.
                db.execute('''INSERT INTO reservation_policies(reservation_id,default_duration_seconds,
                              max_extensions,extension_count,is_legacy)
                              SELECT id,21600,NULL,0,1 FROM reservations''')
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
            if upgrade_history:
                from .seat_history import migrate_links
                history_result = migrate_links(db)
            after = definitions(db)
            if not all(normalize(after.get(name)) == normalize(sql) for name, sql in expected.items()):
                raise RuntimeError('Migration schema verification failed.')
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Migration foreign key verification failed.')
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {'status': 'upgraded', 'backup': str(backup) if backup is not None else None, 'history': history_result}
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=default_path())
    backup_option = parser.add_mutually_exclusive_group(required=True)
    backup_option.add_argument('--backup', type=Path)
    backup_option.add_argument('--no-backup', action='store_true', help='Explicitly migrate without creating a backup.')
    args = parser.parse_args()
    print(json.dumps(upgrade(args.database, args.backup), ensure_ascii=False))
