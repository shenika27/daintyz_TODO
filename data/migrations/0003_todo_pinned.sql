PRAGMA foreign_keys = ON;

ALTER TABLE todos
    ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_todos_date_pinned_order
    ON todos (due_date, pinned, sort_order);

PRAGMA user_version = 3;
