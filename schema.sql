PRAGMA foreign_keys = ON;

CREATE TABLE floors (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE rooms (
    id INTEGER PRIMARY KEY,
    floor_id INTEGER NOT NULL REFERENCES floors(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (floor_id, code)
);

CREATE TABLE seats (
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    number TEXT NOT NULL,
    UNIQUE (room_id, number)
);

CREATE TABLE reservations (
    id INTEGER PRIMARY KEY,
    seat_id INTEGER NOT NULL REFERENCES seats(id),
    starts_at INTEGER NOT NULL CHECK (typeof(starts_at) = 'integer'),
    ends_at INTEGER NOT NULL CHECK (typeof(ends_at) = 'integer'),
    CHECK (starts_at < ends_at)
);