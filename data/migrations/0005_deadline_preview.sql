PRAGMA foreign_keys = ON;

ALTER TABLE todos ADD COLUMN deadline_date TEXT;
ALTER TABLE todos ADD COLUMN visible_from_date TEXT;

CREATE INDEX IF NOT EXISTS idx_todos_deadline_preview
    ON todos (visible_from_date, deadline_date, completed, hidden)
    WHERE deadline_date IS NOT NULL;

PRAGMA user_version = 5;
