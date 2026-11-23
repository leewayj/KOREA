import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from api.db import initialize
from api.errors import APIError
from api.models import RoomStatus
from api.service import Service, room_summary


class RoomStatusTests(unittest.TestCase):
    def test_thresholds_before_rounding_and_coverage(self):
        cases = [
            # occupied, empty, unknown, displayed percent, level, reason
            (0, 0, 0, None, None, 'NO_SEATS'),
            (0, 0, 5, None, None, 'NO_VALID_SEATS'),
            (7, 0, 2, None, None, 'LOW_COVERAGE'),
            (0, 4, 1, 0, 'LOW', None),
            (29, 71, 0, 29, 'LOW', None),
            (2, 6, 0, 25, 'LOW', None),
            (1, 7, 0, 13, 'LOW', None),
            (59, 141, 0, 30, 'LOW', None),
            (3, 7, 0, 30, 'MODERATE', None),
            (139, 61, 0, 70, 'MODERATE', None),
            (7, 3, 0, 70, 'HIGH', None),
            (1, 0, 0, 100, 'HIGH', None),
        ]
        for occupied, empty, unknown, percent, level, reason in cases:
            with self.subTest(occupied=occupied, empty=empty, unknown=unknown):
                states = ['UNRESERVED_OCCUPIED'] * occupied + ['AVAILABLE'] * empty + ['UNKNOWN'] * unknown
                _, result = room_summary([{'seat_status': state} for state in states], datetime.now(UTC))
                self.assertEqual((result.percent, result.level, result.reason), (percent, level, reason))
                self.assertEqual(result.status, 'INSUFFICIENT_DATA' if reason else 'OK')

    def test_all_final_states(self):
        states = ['RESERVED_OCCUPIED', 'EXPIRING_OCCUPIED', 'EXPIRED_OCCUPIED',
                  'UNRESERVED_OCCUPIED', 'RESERVED_EMPTY', 'AVAILABLE', 'UNKNOWN']
        counts, result = room_summary([{'seat_status': state} for state in states], datetime.now(UTC))
        self.assertEqual(counts.model_dump(), dict(total=7, valid=6, occupied=4, available=1,
                                                  reservedEmpty=1, unknown=1))
        self.assertEqual(result.percent, 67)

    def test_snapshot_includes_every_seat_in_only_the_requested_room(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.db'
            initialize(path, demo=True)
            with sqlite3.connect(path) as db:
                db.executemany("INSERT INTO seats(room_id, number) VALUES(1, ?)",
                               [(str(i),) for i in range(3, 102)])
                db.execute("""INSERT INTO seat_device_reports(seat_id, device_kind, received_at)
                    SELECT id, 'VIRTUAL', 1 FROM seats WHERE room_id=1 AND number != '1'""")
                db.execute("""UPDATE seat_occupancy SET state='EMPTY' WHERE seat_id IN
                    (SELECT seat_id FROM seat_device_reports)""")
            service = Service(path)
            snapshot = RoomStatus.model_validate(service.room_status(1))
            self.assertEqual(len(snapshot.seats), 101)
            self.assertEqual(snapshot.seatCounts.total, 101)
            self.assertEqual(snapshot.seatCounts.available, 100)
            self.assertEqual(snapshot.seatCounts.unknown, 1)
            self.assertEqual(snapshot.congestion.percent, 0)
            self.assertEqual(snapshot.serverTime, snapshot.congestion.calculatedAt)
            self.assertTrue(snapshot.hasSimulatedData)
            self.assertFalse(service.room_status(2)['hasSimulatedData'])
            with self.assertRaises(APIError) as missing:
                service.room_status(999)
            self.assertEqual((missing.exception.status, missing.exception.code), (404, 'ROOM_NOT_FOUND'))
            with self.assertRaises(APIError) as failure:
                Service(Path(tmp) / 'missing.db').room_status(1)
            self.assertEqual((failure.exception.status, failure.exception.code), (503, 'STATUS_UNAVAILABLE'))
