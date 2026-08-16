from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "ML Learning Lab for Analysts"
APP_VERSION = "0.1.0-m1"
SCHEMA_VERSION = 1
CONTENT_VERSION = "1.0.0-m1"


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    override = os.environ.get("MLLAB_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    return Path(local_app_data) / "MLLearningLab"


def ensure_app_directories() -> dict[str, Path]:
    root = data_root()
    paths = {
        "root": root,
        "state": root / "state",
        "backups": root / "backups",
        "logs": root / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def configure_logging() -> logging.Logger:
    paths = ensure_app_directories()
    logger = logging.getLogger("ml_learning_lab")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        paths["logs"] / "ml-learning-lab.log",
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
