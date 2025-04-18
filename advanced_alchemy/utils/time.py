import datetime
import sys


def get_utc_now() -> datetime.datetime:  # pragma: no cover
    if sys.version_info >= (3, 11):
        return datetime.datetime.now(datetime.UTC)
    return datetime.datetime.utcnow().replace(tzinfo=None)  # pyright: ignore  # noqa: DTZ003
