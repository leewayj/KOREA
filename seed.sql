PRAGMA foreign_keys = ON;
BEGIN;

-- Re-running the seed preserves existing data, bookings, and occupancy.
INSERT INTO floors (id, code, name) VALUES (2, '2', '2F'), (4, '4', '4F')
ON CONFLICT(code) DO NOTHING;

INSERT INTO rooms (id, floor_id, code, name) VALUES
    (1, (SELECT id FROM floors WHERE code = '2'), 'R1', '제1열람실'),
    (2, (SELECT id FROM floors WHERE code = '4'), 'R2', '제2열람실'),
    (3, (SELECT id FROM floors WHERE code = '4'), 'HOLMZ', '노상일 HOLMZ'),
    (4, (SELECT id FROM floors WHERE code = '4'), 'FOCUS', '집중열람실')
ON CONFLICT(floor_id, code) DO NOTHING;

-- Omit id: new databases assign 1 through 8, not 0 through 7.
-- The same displayed number is allowed in different rooms.
INSERT INTO seats (room_id, number)
SELECT r.id, n.number FROM rooms r
JOIN floors f ON f.id = r.floor_id
CROSS JOIN (SELECT '1' AS number UNION ALL SELECT '2') n
WHERE (f.code = '2' AND r.code = 'R1')
   OR (f.code = '4' AND r.code IN ('R2', 'HOLMZ', 'FOCUS'))
ORDER BY r.id, n.number
ON CONFLICT(room_id, number) DO NOTHING;

COMMIT;
