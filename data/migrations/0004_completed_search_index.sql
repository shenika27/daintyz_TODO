PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_todos_completed_visible_date_order
    ON todos (due_date DESC, sort_order, id)
    WHERE completed = 1 AND hidden = 0;

PRAGMA user_version = 4;
