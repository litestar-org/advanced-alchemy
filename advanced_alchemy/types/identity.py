from __future__ import annotations

from sqlalchemy.types import BigInteger, Integer

BigIntIdentity = BigInteger().with_variant(Integer, "sqlite")
"""A ``BigInteger`` variant that reverts to an ``Integer`` for unsupported variants."""
