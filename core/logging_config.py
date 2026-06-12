"""core/logging_config.py — 회전 파일 + 콘솔 로깅 설정."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core import paths


def setup_logging(level: int = logging.INFO) -> None:
    log_file = paths.log_dir() / "app.log"

    root = logging.getLogger()
    if root.handlers:  # 중복 초기화 방지
        return
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)
