PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

INSERT INTO users(s_id) VALUES ('2026123456'), ('2026987654')
ON CONFLICT(s_id) DO NOTHING;

INSERT INTO user_profiles(s_id, name, college, department) VALUES
    ('2026123456', '홍길동', '소프트웨어융합대학', '컴퓨터학부'),
    ('2026987654', '이하냥', '소프트웨어융합대학', '수리데이터사이언스학과')
ON CONFLICT(s_id) DO NOTHING;

INSERT INTO floors(id, code, name, sort_order) VALUES
    (1, '2', '2F', 2),
    (2, '4', '4F', 4)
ON CONFLICT(id) DO NOTHING;

INSERT INTO rooms(id, name, floor_id, code) VALUES
    (1, '제1열람실', 1, 'R1'),
    (2, '제2열람실', 2, 'R2'),
    (3, '집중열람실', 2, 'Focus'),
    (4, '노상일', 2, 'HOLMZ')
ON CONFLICT(id) DO NOTHING;

-- Each room displays numbers 1..72; seat IDs are globally unique 1..288.
WITH RECURSIVE numbers(n) AS (
    SELECT 1 UNION ALL SELECT n+1 FROM numbers WHERE n<72
)
INSERT INTO seats(id, room_id, number)
SELECT (r.id-1)*72+n.n, r.id, CAST(n.n AS TEXT)
FROM rooms r CROSS JOIN numbers n
WHERE r.id IN (1,2,3,4)
ORDER BY r.id,n.n
ON CONFLICT(id) DO NOTHING;

COMMIT;
