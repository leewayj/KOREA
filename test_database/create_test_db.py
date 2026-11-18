"""Create a separate test DB from the chosen project's current schema."""
import argparse
import sqlite3
import sys
from pathlib import Path


def seed_test_admin(db):
    # Requested test fixture only; keep the API's 8-character provisioning rule.
    from api.admin import hash_password, verify_password
    row = db.execute('SELECT password_hash FROM admins WHERE username=?', ('admin',)).fetchone()
    if row is not None and verify_password('admin', row[0]):
        return
    db.execute('''INSERT INTO admins(username,password_hash) VALUES(?,?)
        ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash''',
        ('admin', hash_password('admin')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, required=True)
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).resolve().parent/'library_test.db')
    args = parser.parse_args()
    project = args.project_root.resolve()
    if not (project/'api/db.py').is_file() or not (project/'schema.sql').is_file():
        parser.error('--project-root must contain api/db.py and schema.sql')
    output = args.output.resolve()
    if output == project/'library.db':
        parser.error('Use a separate test DB, not the project library.db')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(project))
    from api.db import initialize, validate
    # initialize refuses to overwrite any existing file.
    initialize(output, demo=False)
    with sqlite3.connect(output) as db:
        db.executescript(Path(__file__).with_name('seed.sql').read_text(encoding='utf-8'))
        seed_test_admin(db)
    validate(output)
    print(f'Created: {output}')


if __name__ == '__main__':
    main()
