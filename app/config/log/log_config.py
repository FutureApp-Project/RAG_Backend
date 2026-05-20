# app/config/log/log_config.py

import logging
import os
from datetime import date
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

# Production logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()  # Capture everything in production
LOG_FORMAT = os.getenv("LOG_FORMAT", "detailed")  # detailed or simple
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB default
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))  # Keep 10 backups

# Convert string to logging constant
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

FILE_LEVEL = LOG_LEVELS.get(LOG_LEVEL, logging.DEBUG)


class OnDemandRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that creates file only on first log"""

    def __init__(self, filename, **kwargs):
        self._initialized = False
        super().__init__(filename, **kwargs)

    def emit(self, record):
        if not self._initialized:
            directory = os.path.dirname(self.baseFilename)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            self._initialized = True

        if not os.path.exists(self.baseFilename):
            open(self.baseFilename, "a").close()

        super().emit(record)


def get_logger(name: str):
    if not hasattr(get_logger, "_loggers"):
        get_logger._loggers = {}

    if not hasattr(get_logger, "_dates"):
        get_logger._dates = {}

    today = date.today().isoformat()  # YYYY-MM-DD

    # Check if logger exists AND date hasn't changed
    if name in get_logger._loggers and get_logger._dates.get(name) == today:
        return get_logger._loggers[name]

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Always DEBUG to capture everything
    logger.handlers.clear()

    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)

    # Define detailed formatter for files (includes line numbers, etc.)
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s"
    )

    # 1. MAIN LOG FILE - Captures ALL levels (DEBUG and above)
    main_log_file = f"logs/{name}_{today}.log"
    main_handler = OnDemandRotatingFileHandler(
        main_log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    main_handler.setLevel(logging.DEBUG)  # Capture everything
    main_handler.setFormatter(detailed_formatter)
    logger.addHandler(main_handler)

    # 2. ERROR LOG FILE - Captures only ERROR and CRITICAL
    error_log_file = f"logs/{name}_errors_{today}.log"
    error_handler = OnDemandRotatingFileHandler(
        error_log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    error_handler.setLevel(logging.ERROR)  # Only errors
    error_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_handler)

    # 3. Optional: Also log warnings to a separate file
    warning_log_file = f"logs/{name}_warnings_{today}.log"
    warning_handler = OnDemandRotatingFileHandler(
        warning_log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    warning_handler.setLevel(logging.WARNING)  # WARNING and above
    warning_handler.setFormatter(detailed_formatter)
    logger.addHandler(warning_handler)

    # Cache logger and its date
    get_logger._loggers[name] = logger
    get_logger._dates[name] = today

    # Log initialization
    logger.info(f"Logger '{name}' initialized for date {today}")
    logger.debug("Debug logging enabled")

    return logger
