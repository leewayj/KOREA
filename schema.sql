PRAGMA foreign_keys = ON;

-- Demonstration identity only: an ID is not proof of real student identity.
CREATE TABLE users (
    s_id TEXT PRIMARY KEY NOT NULL
        CHECK (typeof(s_id) = 'text' AND length(s_id) = 10 AND s_id NOT GLOB '*[^0-9]*'),
    created_at INTEGER NOT NULL DEFAULT (unixepoch()) CHECK (typeof(created_at) = 'integer')
);

CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY NOT NULL
        CHECK (length(token_hash) = 64 AND token_hash NOT GLOB '*[^0-9a-f]*'),
    s_id TEXT NOT NULL REFERENCES users(s_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL CHECK (typeof(created_at) = 'integer'),
    expires_at INTEGER NOT NULL CHECK (typeof(expires_at) = 'integer'),
    CHECK (created_at < expires_at)
);
CREATE INDEX auth_sessions_user ON auth_sessions(s_id);
CREATE INDEX auth_sessions_expiry ON auth_sessions(expires_at);

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
    id INTEGER PRIMARY KEY CHECK (id >= 1),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    number TEXT NOT NULL,
    UNIQUE (room_id, number)
);

-- All timestamps are UTC Unix seconds. Convert to Asia/Seoul for display.
-- def_time is seconds per reservation; provisional default: 6 hours.
-- For another duration: INSERT ... (seat_id, def_time) VALUES (1, 3600).
CREATE TABLE reservations (
    id INTEGER PRIMARY KEY,
    seat_id INTEGER NOT NULL REFERENCES seats(id),
    confirmed_at INTEGER NOT NULL DEFAULT (unixepoch())
        CHECK (typeof(confirmed_at) = 'integer'),
    -- Starts at the database current Unix second; immutable after insertion.
    starts_at INTEGER NOT NULL DEFAULT (unixepoch())
        CHECK (typeof(starts_at) = 'integer'),
    def_time INTEGER NOT NULL DEFAULT 21600
        CHECK (typeof(def_time) = 'integer' AND def_time > 0),
    ends_at INTEGER GENERATED ALWAYS AS (starts_at + def_time) STORED,
    status TEXT NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('CONFIRMED', 'ENDED', 'CANCELLED')),
    status_changed_at INTEGER NOT NULL DEFAULT (unixepoch()),
    CHECK (typeof(ends_at) = 'integer' AND starts_at < ends_at)
);
CREATE INDEX reservations_seat_time ON reservations(seat_id, starts_at, ends_at)
    WHERE status = 'CONFIRMED';

CREATE TABLE reservation_moves (
    id INTEGER PRIMARY KEY,
    reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
    from_seat_id INTEGER NOT NULL REFERENCES seats(id),
    to_seat_id INTEGER NOT NULL REFERENCES seats(id),
    moved_at INTEGER NOT NULL CHECK (typeof(moved_at) = 'integer'),
    CHECK (from_seat_id <> to_seat_id)
);
CREATE INDEX reservation_moves_reservation ON reservation_moves(reservation_id, id);

-- [starts_at, ends_at): adjacent reservations are allowed.
-- BEGIN/COMMIT on the server plus these triggers protect concurrent inserts.
CREATE TRIGGER reservations_validate_insert BEFORE INSERT ON reservations
BEGIN
    SELECT RAISE(ABORT, 'reservation must start at current time')
        WHERE NEW.starts_at <> unixepoch();
    SELECT RAISE(ABORT, 'new reservation must be CONFIRMED') WHERE NEW.status <> 'CONFIRMED';
    SELECT RAISE(ABORT, 'reservation overlaps') WHERE EXISTS (
        SELECT 1 FROM reservations r
        WHERE r.seat_id = NEW.seat_id AND r.status = 'CONFIRMED'
          AND COALESCE((SELECT m.moved_at FROM reservation_moves m
                        WHERE m.reservation_id = r.id ORDER BY m.id DESC LIMIT 1), r.starts_at)
              < NEW.starts_at + NEW.def_time
          AND NEW.starts_at < r.ends_at
    );
END;

CREATE TRIGGER reservations_validate_update
BEFORE UPDATE OF seat_id, starts_at, def_time, status, confirmed_at ON reservations
BEGIN
    -- Preserve the original start even when changing it to the current time.
    SELECT RAISE(ABORT, 'starts_at is immutable')
        WHERE NEW.starts_at IS NOT OLD.starts_at;
    SELECT RAISE(ABORT, 'terminal reservation cannot be changed')
        WHERE OLD.status IN ('ENDED', 'CANCELLED');
    SELECT RAISE(ABORT, 'confirmed_at is immutable')
        WHERE NEW.confirmed_at <> OLD.confirmed_at;
    SELECT RAISE(ABORT, 'cannot change duration while moving seat')
        WHERE NEW.seat_id <> OLD.seat_id AND NEW.def_time <> OLD.def_time;
    SELECT RAISE(ABORT, 'seat move clock is inconsistent')
        WHERE NEW.seat_id <> OLD.seat_id AND unixepoch() <
            COALESCE((SELECT moved_at FROM reservation_moves WHERE reservation_id = OLD.id
                      ORDER BY id DESC LIMIT 1), OLD.starts_at);
    SELECT RAISE(ABORT, 'duration ends before latest seat move')
        WHERE NEW.starts_at + NEW.def_time <=
            COALESCE((SELECT moved_at FROM reservation_moves WHERE reservation_id = OLD.id
                      ORDER BY id DESC LIMIT 1), OLD.starts_at);
    SELECT RAISE(ABORT, 'cannot change booking while ending or cancelling')
        WHERE NEW.status <> 'CONFIRMED' AND
            (NEW.seat_id <> OLD.seat_id OR NEW.starts_at <> OLD.starts_at OR NEW.def_time <> OLD.def_time);
    SELECT RAISE(ABORT, 'reservation already expired')
        WHERE OLD.ends_at <= unixepoch();
    SELECT RAISE(ABORT, 'future reservation can only be cancelled')
        WHERE NEW.status = 'ENDED' AND OLD.starts_at > unixepoch();
    SELECT RAISE(ABORT, 'reservation overlaps') WHERE NEW.status = 'CONFIRMED' AND EXISTS (
        SELECT 1 FROM reservations r
        WHERE r.id <> NEW.id AND r.seat_id = NEW.seat_id AND r.status = 'CONFIRMED'
          AND COALESCE((SELECT m.moved_at FROM reservation_moves m
                        WHERE m.reservation_id = r.id ORDER BY m.id DESC LIMIT 1), r.starts_at)
              < NEW.starts_at + NEW.def_time
          AND (CASE WHEN NEW.seat_id <> OLD.seat_id THEN unixepoch()
                    ELSE COALESCE((SELECT moved_at FROM reservation_moves WHERE reservation_id = OLD.id
                                   ORDER BY id DESC LIMIT 1), NEW.starts_at) END) < r.ends_at
    );
END;

CREATE TRIGGER reservations_record_move AFTER UPDATE OF seat_id ON reservations
WHEN NEW.seat_id <> OLD.seat_id
BEGIN
    INSERT INTO reservation_moves(reservation_id, from_seat_id, to_seat_id, moved_at)
    VALUES (NEW.id, OLD.seat_id, NEW.seat_id, unixepoch());
END;

CREATE TRIGGER reservations_stamp_status AFTER UPDATE OF status ON reservations
WHEN NEW.status <> OLD.status
BEGIN
    UPDATE reservations SET status_changed_at = unixepoch() WHERE id = NEW.id;
END;

CREATE TABLE seat_occupancy (
    seat_id INTEGER PRIMARY KEY REFERENCES seats(id),
    state TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (state IN ('UNKNOWN', 'EMPTY', 'OCCUPIED', 'SENSOR_ERROR')),
    occupied_since INTEGER,
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    CHECK (occupied_since IS NULL OR typeof(occupied_since) = 'integer'),
    CHECK ((state = 'OCCUPIED' AND occupied_since IS NOT NULL)
        OR (state <> 'OCCUPIED' AND occupied_since IS NULL))
);
CREATE TRIGGER seats_initialize_occupancy AFTER INSERT ON seats
BEGIN
    INSERT INTO seat_occupancy(seat_id) VALUES (NEW.id);
END;

CREATE VIEW reservation_status AS
SELECT r.*, CASE
    WHEN status = 'CANCELLED' THEN 'CANCELLED'
    WHEN status = 'ENDED' OR ends_at <= unixepoch() THEN 'ENDED'
    ELSE 'IN_USE' END AS effective_status
FROM reservations r;

-- IN_USE refers to an active time interval, not the identity/presence of a person.
CREATE VIEW seat_status AS
SELECT s.id AS seat_id, f.code AS floor_code, f.name AS floor_name,
    rm.code AS room_code, rm.name AS room_name, s.number AS seat_number,
    r.id AS active_reservation_id, r.starts_at, r.ends_at,
    CASE WHEN r.id IS NULL THEN 'AVAILABLE' ELSE 'RESERVED' END AS reservation_state,
    o.state AS occupancy_state, o.occupied_since, o.updated_at AS occupancy_updated_at
FROM seats s JOIN rooms rm ON rm.id = s.room_id
JOIN floors f ON f.id = rm.floor_id
LEFT JOIN reservations r ON r.seat_id = s.id AND r.status = 'CONFIRMED'
    AND r.starts_at <= unixepoch() AND unixepoch() < r.ends_at
LEFT JOIN seat_occupancy o ON o.seat_id = s.id;
