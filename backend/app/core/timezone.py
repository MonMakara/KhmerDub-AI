"""Timezone utilities for KhmerDub AI.

Standardizes all timestamp generation to Cambodia Time (Asia/Phnom_Penh, UTC+7).
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from app.core.config import settings

CAMBODIA_TZ_NAME = getattr(settings, "TIMEZONE", "Asia/Phnom_Penh")
try:
    CAMBODIA_TZ = ZoneInfo(CAMBODIA_TZ_NAME)
except Exception:
    CAMBODIA_TZ = ZoneInfo("Asia/Phnom_Penh")


def get_cambodia_now() -> datetime:
    """Return timezone-aware datetime representing current time in Cambodia (UTC+7)."""
    return datetime.now(CAMBODIA_TZ)


def get_cambodia_now_naive() -> datetime:
    """Return naive datetime representing current time in Cambodia.

    Ideal for SQLite DateTime fields so that values stored in the database
    consistently reflect local Cambodia time.
    """
    return datetime.now(CAMBODIA_TZ).replace(tzinfo=None)
