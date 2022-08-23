import re
from datetime import timedelta, datetime

TIME_PATTERN = re.compile(r"(\d+\.?\d?[s|m|h|d|w]{1})\s?", re.I)


def process_duration(duration) -> datetime:
    units = {"w": "weeks", "d": "days", "h": "hours", "m": "minutes", "s": "seconds"}
    delta = {"weeks": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    # delay: str = ctx.kwargs.get("duration")
    if duration:
        if times := TIME_PATTERN.findall(duration):
            for t in times:
                delta[units[t[-1]]] += float(t[:-1])
        else:
            raise ValueError("Invalid time string, please follow example: `1w 3d 7h 5m 20s`")

        if not any(value for value in delta.items()):
            raise ValueError("At least one time period is required")

        remind_at = datetime.now() + timedelta(**delta)
        return remind_at
    return duration
