import contextlib

import pytest


async def test_repo_get_or_create_deprecation() -> None:
    with pytest.warns(DeprecationWarning):
        from advanced_alchemy.exceptions import ConflictError

        with contextlib.suppress(Exception):
            raise ConflictError
