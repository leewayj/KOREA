"""Initialize only a missing database, then start one SQLite-backed API worker."""
import os
import sys
from api.db import default_path, initialize, validate


def main():
    path = default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        initialize(path, demo=os.getenv('KOREA_SEED_DEMO', '1') == '1')
    else:
        validate(path)
    port = int(os.getenv('PORT', '8000'))
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'deploy.app:app',
                            '--host', '0.0.0.0', '--port', str(port), '--workers', '1'])


if __name__ == '__main__':
    main()
