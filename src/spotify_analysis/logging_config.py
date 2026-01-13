import os
import logging
from logging.config import dictConfig
from logging.handlers import QueueHandler, QueueListener
import multiprocessing

# We need a global queue that can be shared across processes
log_queue = multiprocessing.Queue(-1)

def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    logfile = os.path.join(log_dir, "spotify_analysis.log")

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
                "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                "formatter": "standard",
                "level": log_level,
                "filename": logfile,
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf8",
            },
        },
        "root": {"level": log_level, "handlers": ["console", "file"]},
        "loggers": {
            "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "nicegui": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "aiosqlite": {"level": "INFO", "handlers": ["console"], "propagate": False},
            # watchfiles level is warning to stop creating logs from detecting changes in log file
            "watchfiles": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        },
    }

    dictConfig(config)
    
    # --- SETUP THE LISTENER (The part that actually writes to the file) ---
    # This part should only run ONCE in the main process
    if multiprocessing.current_process().name == 'MainProcess':
        # Create the actual file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=logfile,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf8"
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))

        # Start the listener
        listener = QueueListener(log_queue, file_handler)
        listener.start()