PRAGMA foreign_keys = ON;

ALTER TABLE todos
    ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_todos_date_priority_order
    ON todos (due_date, priority, sort_order);

PRAGMA user_version = 2;
