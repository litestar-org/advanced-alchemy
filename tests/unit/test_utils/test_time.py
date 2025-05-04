import datetime
import sys

import pytest

from advanced_alchemy.utils.time import get_utc_now


def test_get_utc_now_returns_datetime() -> None:
    """Test that get_utc_now returns a datetime object."""
    now = get_utc_now()
    assert isinstance(now, datetime.datetime)


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Requires Python 3.11+ for timezone.UTC")
def test_get_utc_now_py311_plus() -> None:
    """Test get_utc_now on Python 3.11+ returns tz-aware UTC datetime."""
    now = get_utc_now()
    assert now.tzinfo is datetime.timezone.utc


@pytest.mark.skipif(sys.version_info >= (3, 11), reason="Requires Python < 3.11 for utcnow()")
def test_get_utc_now_py_less_than_311() -> None:
    """Test get_utc_now on Python < 3.11 returns naive UTC datetime."""
    # Ensure the correct branch is taken by mocking version_info if necessary,
    # although skipif should handle this for test execution environment.
    now = get_utc_now()
    # Before 3.11, it returns a naive datetime representing UTC
    assert now.tzinfo is None


def test_get_utc_now_within_tolerance() -> None:
    """Test that the returned time is close to the actual UTC time."""
    # This test assumes the system clock is reasonably accurate
    expected_now = datetime.datetime.now(datetime.timezone.utc)
    actual_now = get_utc_now()

    # On Python < 3.11, actual_now is naive, make expected_now naive for comparison
    if sys.version_info < (3, 11):
        expected_now = expected_now.replace(tzinfo=None)

    # Allow a small difference (e.g., 1 second) to account for execution time
    assert abs(actual_now - expected_now) < datetime.timedelta(seconds=1)
