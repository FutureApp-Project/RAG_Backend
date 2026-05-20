# app/config/helper/time_helper.py
from datetime import datetime
import pytz

def get_current_berlin_time() -> datetime:
    """
    Get current time in Berlin timezone
    """
    berlin_tz = pytz.timezone('Europe/Berlin')
    return datetime.now(berlin_tz)