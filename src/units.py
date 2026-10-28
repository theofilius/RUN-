"""Turn seconds back into the formats runners read."""

import math


def format_pace(seconds_per_km):
    """543 -> "9:03" (min:sec per km)."""
    if seconds_per_km is None or math.isnan(seconds_per_km):
        return "-"
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}"


def format_duration(seconds):
    """11653 -> "3:14:13" (h:mm:ss)."""
    if seconds is None or math.isnan(seconds):
        return "-"
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"
