PRAGMA foreign_keys = ON;

-- Demonstration identity only: an ID is not proof of real student identity.
CREATE TABLE users (
    s_id TEXT PRIMARY KEY NOT NULL
        CHECK (typeof(s_id) = 'text' AND length(s_id) = 10 AND s_id NOT GLOB '*[^0-9]*'),
    created_at INTEGER NOT NULL DEFAULT (unixepoch()) CHECK (typeof(created_at) = 'integer')
);

-- Profile registration is independent of login/session creation.
CREATE TABLE user_profiles (
    s_id TEXT PRIMARY KEY NOT NULL REFERENCES users(s_id),
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100 AND name = trim(name)),
    college TEXT NOT NULL CHECK (length(trim(college)) BETWEEN 1 AND 100 AND college = trim(college)),
    department TEXT NOT NULL CHECK (length(trim(department)) BETWEEN 1 AND 100 AND department = trim(department))
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

-- Administrator credentials are provisioned locally, never by demo student login.
CREATE TABLE admins (
    username TEXT PRIMARY KEY NOT NULL,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE TABLE admin_sessions (
    token_hash TEXT PRIMARY KEY NOT NULL,
    username TEXT NOT NULL REFERENCES admins(username) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    CHECK (created_at < expires_at)
);
CREATE INDEX admin_sessions_expiry ON admin_sessions(expires_at);

-- Current policy. Each new reservation stores its own immutable copy.
CREATE TABLE reservation_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    default_duration_seconds INTEGER NOT NULL CHECK (
        typeof(default_duration_seconds) = 'integer' AND default_duration_seconds > 0),
    max_extensions INTEGER NOT NULL CHECK (typeof(max_extensions) = 'integer' AND max_extensions >= 0),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_by TEXT REFERENCES admins(username)
);
INSERT INTO reservation_settings(id, default_duration_seconds, max_extensions) VALUES (1, 21600, 2);
CREATE TRIGGER reservation_settings_no_delete BEFORE DELETE ON reservation_settings
BEGIN
    SELECT RAISE(ABORT, 'reservation settings cannot be deleted');
END;

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
-- API defaults come from reservation_settings; SQL fallback remains 6 hours.
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

CREATE TABLE reservation_policies (
    reservation_id INTEGER PRIMARY KEY REFERENCES reservations(id) ON DELETE CASCADE,
    default_duration_seconds INTEGER NOT NULL CHECK (
        typeof(default_duration_seconds) = 'integer' AND default_duration_seconds > 0),
    max_extensions INTEGER CHECK (max_extensions IS NULL OR
        (typeof(max_extensions) = 'integer' AND max_extensions >= 0)),
    extension_count INTEGER NOT NULL DEFAULT 0 CHECK (
        typeof(extension_count) = 'integer' AND extension_count >= 0),
    is_legacy INTEGER NOT NULL DEFAULT 0 CHECK (is_legacy IN (0, 1)),
    CHECK (max_extensions IS NOT NULL OR is_legacy = 1),
    CHECK (max_extensions IS NULL OR extension_count <= max_extensions)
);

CREATE TRIGGER reservations_capture_policy AFTER INSERT ON reservations
BEGIN
    SELECT RAISE(ABORT, 'reservation settings missing')
        WHERE NOT EXISTS (SELECT 1 FROM reservation_settings WHERE id = 1);
    INSERT INTO reservation_policies(reservation_id, default_duration_seconds, max_extensions)
        SELECT NEW.id, default_duration_seconds, max_extensions FROM reservation_settings WHERE id = 1;
END;

CREATE TRIGGER reservation_policies_immutable BEFORE UPDATE ON reservation_policies
BEGIN
    SELECT RAISE(ABORT, 'reservation policy is immutable')
        WHERE NEW.reservation_id IS NOT OLD.reservation_id
           OR NEW.default_duration_seconds IS NOT OLD.default_duration_seconds
           OR NEW.max_extensions IS NOT OLD.max_extensions
           OR NEW.is_legacy IS NOT OLD.is_legacy;
    SELECT RAISE(ABORT, 'extension count cannot decrease')
        WHERE NEW.extension_count < OLD.extension_count;
END;

-- Any ordinary increase, including PATCH, consumes one extension.
-- Verified administrator edits use their existing transaction-local context.
CREATE TRIGGER reservations_extension_limit BEFORE UPDATE OF def_time ON reservations
WHEN NEW.def_time > OLD.def_time
 AND NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'reservation policy missing')
        WHERE NOT EXISTS (SELECT 1 FROM reservation_policies WHERE reservation_id = OLD.id);
    SELECT RAISE(ABORT, 'extension limit reached') WHERE EXISTS (
        SELECT 1 FROM reservation_policies WHERE reservation_id = OLD.id
          AND max_extensions IS NOT NULL AND extension_count >= max_extensions
    );
END;

CREATE TRIGGER reservations_count_extension AFTER UPDATE OF def_time ON reservations
WHEN NEW.def_time > OLD.def_time
 AND NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id)
BEGIN
    UPDATE reservation_policies SET extension_count = extension_count + 1 WHERE reservation_id = NEW.id;
END;

-- Ownership is separate so public reservation projections never expose student IDs.
-- Existing ownerless reservations remain ownerless after migration.
CREATE TABLE reservation_owners (
    reservation_id INTEGER PRIMARY KEY REFERENCES reservations(id) ON DELETE CASCADE,
    s_id TEXT NOT NULL REFERENCES users(s_id)
);
CREATE INDEX reservation_owners_user ON reservation_owners(s_id, reservation_id);

-- Active means CONFIRMED and not expired, including future SCHEDULED rows.
-- These triggers run inside serialized write transactions, including admin edits.
CREATE TRIGGER reservation_owners_one_active BEFORE INSERT ON reservation_owners
WHEN EXISTS (SELECT 1 FROM reservations WHERE id = NEW.reservation_id
             AND status = 'CONFIRMED' AND ends_at > unixepoch())
BEGIN
    SELECT RAISE(ABORT, 'user already has active reservation') WHERE EXISTS (
        SELECT 1 FROM reservation_owners owner JOIN reservations r ON r.id = owner.reservation_id
        WHERE owner.s_id = NEW.s_id AND owner.reservation_id <> NEW.reservation_id
          AND r.status = 'CONFIRMED' AND r.ends_at > unixepoch()
    );
END;

CREATE TRIGGER reservation_owners_immutable BEFORE UPDATE ON reservation_owners
WHEN NEW.reservation_id IS NOT OLD.reservation_id OR NEW.s_id IS NOT OLD.s_id
BEGIN
    SELECT RAISE(ABORT, 'reservation owner is immutable');
END;

CREATE TRIGGER reservations_one_active_user BEFORE UPDATE OF starts_at, def_time, status ON reservations
WHEN NEW.status = 'CONFIRMED' AND NEW.starts_at + NEW.def_time > unixepoch()
BEGIN
    SELECT RAISE(ABORT, 'user already has active reservation') WHERE EXISTS (
        SELECT 1 FROM reservation_owners mine
        JOIN reservation_owners other ON other.s_id = mine.s_id AND other.reservation_id <> NEW.id
        JOIN reservations r ON r.id = other.reservation_id
        WHERE mine.reservation_id = NEW.id AND r.status = 'CONFIRMED' AND r.ends_at > unixepoch()
    );
END;

CREATE TABLE reservation_moves (
    id INTEGER PRIMARY KEY,
    reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
    from_seat_id INTEGER NOT NULL REFERENCES seats(id),
    to_seat_id INTEGER NOT NULL REFERENCES seats(id),
    moved_at INTEGER NOT NULL CHECK (typeof(moved_at) = 'integer'),
    CHECK (from_seat_id <> to_seat_id)
);
CREATE INDEX reservation_moves_reservation ON reservation_moves(reservation_id, id);

-- Independent reservation/move-based usage log. Deleting reservations must not
-- delete this log. There is deliberately no reservation foreign key here.
CREATE TABLE user_seat_history (
    id INTEGER PRIMARY KEY,
    s_id TEXT NOT NULL REFERENCES users(s_id),
    seat_id INTEGER NOT NULL REFERENCES seats(id),
    used_at INTEGER NOT NULL CHECK (typeof(used_at) = 'integer')
);
CREATE INDEX user_seat_history_user_time
    ON user_seat_history(s_id, used_at DESC, id DESC);

-- Ephemeral write cursor, not a link from historical entries to reservations.
-- Cascades when the source reservation is removed, leaving history intact.
CREATE TABLE reservation_history_progress (
    reservation_id INTEGER PRIMARY KEY REFERENCES reservations(id) ON DELETE CASCADE,
    last_move_id INTEGER NOT NULL DEFAULT 0 CHECK (last_move_id >= 0)
);

-- Transaction-local permission marker. The server removes it before commit;
-- BEGIN IMMEDIATE serializes writers, and rollback removes it on failure.
CREATE TABLE reservation_admin_context (
    reservation_id INTEGER PRIMARY KEY REFERENCES reservations(id),
    username TEXT NOT NULL REFERENCES admins(username)
);

CREATE TABLE reservation_admin_insert_context (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    username TEXT NOT NULL REFERENCES admins(username)
);

CREATE TABLE reservation_time_states (
    reservation_id INTEGER PRIMARY KEY REFERENCES reservations(id) ON DELETE CASCADE,
    effective_status TEXT NOT NULL CHECK (effective_status IN ('SCHEDULED','IN_USE','ENDED','CANCELLED')),
    notice_code TEXT,
    evaluated_at INTEGER NOT NULL
);

CREATE TABLE reservation_clock_lease (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    owner TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);

-- [starts_at, ends_at): adjacent reservations are allowed.
-- BEGIN/COMMIT on the server plus these triggers protect concurrent inserts.
CREATE TRIGGER reservations_validate_insert BEFORE INSERT ON reservations
BEGIN
    SELECT RAISE(ABORT, 'reservation must start at current time')
        WHERE NEW.starts_at <> unixepoch()
          AND NOT EXISTS (SELECT 1 FROM reservation_admin_insert_context);
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
        WHERE NEW.starts_at IS NOT OLD.starts_at
          AND NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id);
    SELECT RAISE(ABORT, 'terminal reservation cannot be changed')
        WHERE OLD.status IN ('ENDED', 'CANCELLED')
          AND NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id);
    SELECT RAISE(ABORT, 'confirmed_at is immutable')
        WHERE NEW.confirmed_at <> OLD.confirmed_at;
    SELECT RAISE(ABORT, 'cannot change duration while moving seat')
        WHERE NEW.seat_id <> OLD.seat_id AND NEW.def_time <> OLD.def_time;
    SELECT RAISE(ABORT, 'seat move clock is inconsistent')
        WHERE NEW.seat_id <> OLD.seat_id AND unixepoch() <
            COALESCE((SELECT moved_at FROM reservation_moves WHERE reservation_id = OLD.id
                      ORDER BY id DESC LIMIT 1), OLD.starts_at);
    SELECT RAISE(ABORT, 'duration ends before latest seat move')
        WHERE EXISTS (SELECT 1 FROM reservation_moves WHERE reservation_id = OLD.id)
          AND (NEW.starts_at > (SELECT moved_at FROM reservation_moves WHERE reservation_id = OLD.id ORDER BY id DESC LIMIT 1)
               OR NEW.starts_at + NEW.def_time <= (SELECT moved_at FROM reservation_moves WHERE reservation_id = OLD.id ORDER BY id DESC LIMIT 1));
    SELECT RAISE(ABORT, 'cannot change booking while ending or cancelling')
        WHERE NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id)
          AND NEW.status <> 'CONFIRMED' AND
            (NEW.seat_id <> OLD.seat_id OR NEW.starts_at <> OLD.starts_at OR NEW.def_time <> OLD.def_time);
    SELECT RAISE(ABORT, 'reservation already expired')
        WHERE OLD.ends_at <= unixepoch()
          AND NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id);
    SELECT RAISE(ABORT, 'future reservation can only be cancelled')
        WHERE NEW.status = 'ENDED' AND OLD.starts_at > unixepoch()
          AND NOT EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id);
    SELECT RAISE(ABORT, 'reservation overlaps') WHERE NEW.status = 'CONFIRMED' AND EXISTS (
        SELECT 1 FROM reservations r
        WHERE r.id <> NEW.id AND r.seat_id = NEW.seat_id AND r.status = 'CONFIRMED'
          AND COALESCE((SELECT m.moved_at FROM reservation_moves m
                        WHERE m.reservation_id = r.id ORDER BY m.id DESC LIMIT 1), r.starts_at)
              < NEW.starts_at + NEW.def_time
          AND (CASE WHEN EXISTS (SELECT 1 FROM reservation_admin_context WHERE reservation_id = OLD.id) THEN NEW.starts_at
                    WHEN NEW.seat_id <> OLD.seat_id THEN unixepoch()
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
    WHEN starts_at > unixepoch() THEN 'SCHEDULED'
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
