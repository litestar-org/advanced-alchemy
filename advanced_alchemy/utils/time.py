import datetime


def get_utc_now() -> datetime.datetime:  # pragma: no cover
    """Get the current UTC time with timezone info.

    Returns:
        A timezone-aware datetime object in UTC.
    """
    return datetime.datetime.now(datetime.timezone.utc)
