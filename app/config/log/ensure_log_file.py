# This file is used to ensure the log directory and log file exist for logger.info calls.
# You can import and call ensure_log_file_exists() before logging if needed.
import os


def ensure_log_file_exists(log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if not os.path.exists(log_path):
        with open(log_path, "a"):
            pass
