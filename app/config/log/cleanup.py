from pathlib import Path
from datetime import datetime, timedelta

from app.config.log.log_config import get_logger

LOG_DIR = Path("logs")
logger = get_logger("log_cleanup")


def delete_old_logs():
    cutoff = datetime.now() - timedelta(days=1)

    for file in LOG_DIR.glob("*.log"):
        if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
            file.unlink()
            logger.info("Deleted old log file: %s", file)
