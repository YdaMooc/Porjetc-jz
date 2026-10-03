from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from project_stats.runtime.app_paths import DATA_DIR_NAME, get_data_dir, resolve_writable_dir


LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "project_stats.log"


def setup_logging(app_root: Path | None = None) -> Path:
    # 显式传入 app_root 时仍尝试「跟随程序目录」，不可写则回退到 %LOCALAPPDATA%。
    if app_root is not None:
        data_dir = resolve_writable_dir(app_root / DATA_DIR_NAME, get_data_dir())
    else:
        data_dir = get_data_dir()

    # data_dir 已确认可写；万一 logs 子目录建不出来，也不该让启动失败。
    try:
        log_dir = data_dir / LOG_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = data_dir

    log_path = log_dir / LOG_FILE_NAME
    root_logger = logging.getLogger()
    if any(getattr(handler, "baseFilename", None) == str(log_path) for handler in root_logger.handlers):
        return log_path

    root_logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=512 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(file_handler)
    return log_path
