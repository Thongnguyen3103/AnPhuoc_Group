-- 001_init: người dùng, phiên, snapshot dữ liệu, bảng tra Mã hàng, nhật ký

CREATE TABLE users (
    id                   INTEGER PRIMARY KEY,
    username             TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name            TEXT    NOT NULL DEFAULT '',
    password_hash        TEXT    NOT NULL,
    role                 TEXT    NOT NULL CHECK (role IN ('admin', 'viewer')),
    is_active            INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL,
    last_login_at        TEXT
);

CREATE TABLE sessions (
    token_hash   TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at   TEXT    NOT NULL,
    expires_at   TEXT    NOT NULL,
    last_seen_at TEXT    NOT NULL,
    ip           TEXT,
    user_agent   TEXT
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
CREATE INDEX idx_sessions_expires ON sessions (expires_at);

CREATE TABLE snapshots (
    id          INTEGER PRIMARY KEY,
    sha256      TEXT    NOT NULL UNIQUE,
    ref_label   TEXT,
    ref_year    INTEGER,
    ref_month   INTEGER,
    built_at    TEXT,
    file_name   TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL,
    sku_count   INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT    NOT NULL,
    imported_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
    is_active   INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX idx_snapshots_one_active ON snapshots (is_active) WHERE is_active = 1;

CREATE TABLE sku_track (
    snapshot_id       INTEGER NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    mh                TEXT    NOT NULL,
    op                TEXT    NOT NULL,
    brand             TEXT,
    cat_group         TEXT,
    group_report      TEXT,
    item              TEXT,
    status            TEXT,
    price             INTEGER,
    prod_ym           INTEGER,
    age_months        INTEGER,
    ton_ch            INTEGER NOT NULL DEFAULT 0,
    ton_kho           INTEGER NOT NULL DEFAULT 0,
    ban_1m            INTEGER NOT NULL DEFAULT 0,
    ban_3m            INTEGER NOT NULL DEFAULT 0,
    ban_6m            INTEGER NOT NULL DEFAULT 0,
    ban_ytd           INTEGER NOT NULL DEFAULT 0,
    ban_all           INTEGER NOT NULL DEFAULT 0,
    months_since_sale INTEGER,
    PRIMARY KEY (snapshot_id, mh, op)
);
CREATE INDEX idx_sku_item ON sku_track (snapshot_id, brand, item);

CREATE TABLE audit_log (
    id       INTEGER PRIMARY KEY,
    at       TEXT NOT NULL,
    user_id  INTEGER,
    username TEXT,
    action   TEXT NOT NULL,
    detail   TEXT,
    ip       TEXT
);
CREATE INDEX idx_audit_at ON audit_log (at);
