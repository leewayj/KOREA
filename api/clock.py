"""One-second reconciliation with a database lease across server processes."""
import logging
import sqlite3
import threading
import uuid

from .timing import reconcile


class ReservationClock:
    def __init__(self, path):
        self.path = path.resolve()
        self.owner = uuid.uuid4().hex
        self.stopped = threading.Event()
        self.thread = None

    def connect(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=0.2)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def tick(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            now = db.execute('SELECT unixepoch()').fetchone()[0]
            db.execute('''INSERT INTO reservation_clock_lease VALUES(1,?,?)
                ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at
                WHERE reservation_clock_lease.owner=excluded.owner OR reservation_clock_lease.expires_at<=?''',
                (self.owner, now + 3, now))
            owner = db.execute('SELECT owner FROM reservation_clock_lease WHERE id=1').fetchone()[0]
            acquired = owner == self.owner
            if acquired:
                reconcile(db, now)
            db.commit()
            return acquired
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def run(self):
        while not self.stopped.is_set():
            try:
                self.tick()
            except sqlite3.OperationalError as error:
                if 'locked' not in str(error) and 'busy' not in str(error):
                    logging.getLogger(__name__).exception('Reservation clock failed')
            except Exception:
                logging.getLogger(__name__).exception('Reservation clock failed')
            self.stopped.wait(1)

    def start(self):
        self.thread = threading.Thread(target=self.run, name='reservation-clock', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        db = self.connect()
        try:
            db.execute('UPDATE reservation_clock_lease SET expires_at=0 WHERE id=1 AND owner=?', (self.owner,))
            db.commit()
        except sqlite3.OperationalError:
            db.rollback()  # A lease also expires automatically after three seconds.
        finally:
            db.close()
