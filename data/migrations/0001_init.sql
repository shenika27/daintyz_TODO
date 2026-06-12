-- ============================================================
-- Character TODO - SQLite 스키마 (migration 0001_init)
--   적용 후 PRAGMA user_version = 1
--   반복 할일 = "조회 시점 생성" 방식
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS recurring_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content      TEXT    NOT NULL,
    rule_type    TEXT    NOT NULL,                 -- 'daily' | 'weekly' | 'monthly'
    weekdays     TEXT,                             -- '0,3,5' (0=일 ~ 6=토)
    day_of_month INTEGER,                          -- 1~31
    remind_time  TEXT,                             -- 'HH:MM' (nullable)
    start_date   TEXT    NOT NULL DEFAULT (date('now','localtime')),
    end_date     TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content      TEXT    NOT NULL,
    due_date     TEXT    NOT NULL,                 -- 'YYYY-MM-DD'
    completed    INTEGER NOT NULL DEFAULT 0,
    hidden       INTEGER NOT NULL DEFAULT 0,       -- 1=사용자가 치운 반복 회차(tombstone)
    sort_order   INTEGER NOT NULL DEFAULT 0,
    remind_at    TEXT,                             -- 'YYYY-MM-DD HH:MM' (지금은 NULL)
    recurring_id INTEGER,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (recurring_id) REFERENCES recurring_rules(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_todos_date_order
    ON todos (due_date, sort_order);

CREATE UNIQUE INDEX IF NOT EXISTS idx_todos_recur_once
    ON todos (recurring_id, due_date) WHERE recurring_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_todos_remind
    ON todos (remind_at) WHERE remind_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

PRAGMA user_version = 1;
