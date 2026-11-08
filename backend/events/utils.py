from datetime import datetime
from datetime import timezone as tz


def starts_in_future(scheduled_at: str | datetime, now: datetime | None = None) -> bool:
    """Whether Discord would still accept a scheduled event starting at this time.

    The sync loop, the create task, the task panel and the fire endpoint all
    use this one rule. It lives here, not in events.tasks, so that views can
    import it at module level.
    """
    # A value that can't be parsed or compared counts as not eligible, so one
    # bad row can't abort the whole sync loop.
    try:
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at)
        return scheduled_at > (now or datetime.now(tz.utc))
    except (TypeError, ValueError):
        return False
