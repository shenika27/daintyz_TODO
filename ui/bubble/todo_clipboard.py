from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtWidgets import QApplication

from domain import policies
from domain.models import PRIORITY_HIGH, PRIORITY_NONE, Todo

MIME_TODO_COPY = "application/x-character-todo-copy"


def copy_todo_to_clipboard(todo: Todo) -> None:
    payload = {
        "content": todo.content,
        "priority": int(todo.priority),
    }
    mime = QMimeData()
    mime.setText(todo.content)
    mime.setData(
        MIME_TODO_COPY,
        QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
    )
    QApplication.clipboard().setMimeData(mime)


def can_paste_todo_from_clipboard() -> bool:
    payload = _clipboard_payload()
    return bool(payload and payload[0].strip())


def paste_todo_from_clipboard(service, settings_repo, iso: str) -> int:
    payload = _clipboard_payload()
    if payload is None:
        return 0

    content, priority = payload
    split_lines = bool(
        settings_repo is not None
        and settings_repo.get_bool(policies.KEY_CLIPBOARD_SPLIT_LINES, False)
    )
    if split_lines:
        contents = [line.strip() for line in content.splitlines() if line.strip()]
    else:
        contents = [content.strip()]
    if not contents:
        return 0
    return service.add_many(contents, iso, priority=priority)


def add_paste_action(menu, service, settings_repo, iso: str) -> None:
    paste = menu.addAction("붙여넣기")
    paste.setEnabled(can_paste_todo_from_clipboard())
    paste.triggered.connect(
        lambda: paste_todo_from_clipboard(service, settings_repo, iso)
    )


def _clipboard_payload() -> tuple[str, int] | None:
    mime = QApplication.clipboard().mimeData()
    if mime.hasFormat(MIME_TODO_COPY):
        try:
            raw = bytes(mime.data(MIME_TODO_COPY)).decode("utf-8")
            data = json.loads(raw)
            content = str(data.get("content", "")).strip()
            priority = _clamp_priority(data.get("priority", PRIORITY_NONE))
            if content:
                return content, priority
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    if mime.hasText():
        text = mime.text().strip()
        if text:
            return text, PRIORITY_NONE
    return None


def _clamp_priority(value) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return PRIORITY_NONE
    return max(PRIORITY_NONE, min(PRIORITY_HIGH, priority))
