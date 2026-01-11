import os
import logging
from logging.config import dictConfig


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    logfile = os.path.join(log_dir, "spotify_analysis.log")
    debug_logfile = os.path.join(log_dir, "debug.log")

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": log_level,
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard",
                "level": log_level,
                "filename": logfile,
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf8",
            },
            "debug_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard",
                "level": "DEBUG",
                "filename": debug_logfile,
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf8",
            }
        },
        "root": {"level": log_level, "handlers": ["console", "file"]},
        "loggers": {
            "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "nicegui": {"level": "INFO", "handlers": ["console"], "propagate": False},
            # watchfiles level is warning to stop creating logs from detecting changes in log file
            "watchfiles": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        },
    }

    dictConfig(config)