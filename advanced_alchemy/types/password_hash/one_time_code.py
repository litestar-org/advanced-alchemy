"""One-time-code column type: hashed, self-expiring, single-use.

Stores the code as a JSON object holding the hash plus expiry, redemption, and
attempt state, so a single column captures the full lifecycle of a one-time
code: it can reject an expired code, reject an already-used code, and lock after
too many failed attempts. Persisting a state change (consuming the code or
recording a failed attempt) still requires committing the updated value, since a
column type has no session of its own; the type owns the state model and the
caller commits it.
"""

import secrets
import string
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy.types import TypeDecorator

from advanced_alchemy.types.json import JsonB
from advanced_alchemy.utils.serialization import decode_json

if TYPE_CHECKING:
    from advanced_alchemy.types.password_hash.base import HashingBackend

__all__ = ("HashedOneTimeCode", "OneTimeCode", "generate_one_time_code")


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def generate_one_time_code(length: int = 6, *, digits_only: bool = True) -> str:
    """Generate a cryptographically secure random one-time code.

    Args:
        length: Number of characters in the code. Defaults to 6.
        digits_only: Use digits only when True (default); otherwise uppercase letters and digits.

    Returns:
        A random one-time code string.
    """
    alphabet = string.digits if digits_only else string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class HashedOneTimeCode:
    """Read-side wrapper over a stored one-time code's hash and lifecycle state.

    ``verify`` only succeeds while the code is still redeemable (not expired, not used, and
    not locked out). State transitions return a new instance to assign back to the column;
    commit it to persist single-use and attempt tracking.
    """

    __slots__ = ("_backend", "_max_attempts", "attempts", "expires_at", "hash_string", "used_at")

    def __init__(
        self,
        hash_string: str,
        backend: "HashingBackend",
        *,
        expires_at: "Optional[float]" = None,
        used_at: "Optional[float]" = None,
        attempts: int = 0,
        max_attempts: "Optional[int]" = None,
    ) -> None:
        """Initialize the wrapper.

        Args:
            hash_string: The stored hash of the code.
            backend: The hashing backend used to verify candidates.
            expires_at: POSIX timestamp after which the code is expired, or None for no expiry.
            used_at: POSIX timestamp when the code was redeemed, or None if unused.
            attempts: Number of failed verification attempts recorded so far.
            max_attempts: Attempt ceiling after which the code locks, or None for no limit.
        """
        self.hash_string = hash_string
        self._backend = backend
        self.expires_at = expires_at
        self.used_at = used_at
        self.attempts = attempts
        self._max_attempts = max_attempts

    @property
    def is_expired(self) -> bool:
        """True if the code has an expiry and it has passed."""
        return self.expires_at is not None and _now() > self.expires_at

    @property
    def is_used(self) -> bool:
        """True if the code has already been redeemed."""
        return self.used_at is not None

    @property
    def is_locked(self) -> bool:
        """True if failed attempts have reached ``max_attempts``."""
        return self._max_attempts is not None and self.attempts >= self._max_attempts

    @property
    def is_redeemable(self) -> bool:
        """True if the code can still be redeemed (not expired, used, or locked)."""
        return not (self.is_expired or self.is_used or self.is_locked)

    def verify(self, code: "Union[str, bytes]") -> bool:
        """Return True only if ``code`` matches and the code is still redeemable.

        This does not mutate state. Use :meth:`redeem` to also produce the updated value to
        persist, or pair with :meth:`consume`/:meth:`register_failure`.

        Args:
            code: The candidate code.

        Returns:
            True on a match of a still-redeemable code, otherwise False.
        """
        if not self.is_redeemable:
            return False
        return self._backend.verify(code, self.hash_string)

    def redeem(self, code: "Union[str, bytes]") -> "tuple[bool, HashedOneTimeCode]":
        """Verify ``code`` and return the updated state to persist.

        On success the returned value is marked used (single-use); on a redeemable failure the
        attempt counter is incremented. Assign the returned wrapper back to the column and
        commit to enforce single-use, expiry, and attempt limits on the next load.

        Args:
            code: The candidate code.

        Returns:
            A ``(ok, new_state)`` tuple. ``new_state`` is unchanged when the code was already
            expired, used, or locked.
        """
        if not self.is_redeemable:
            return (False, self)
        if self._backend.verify(code, self.hash_string):
            return (True, self.consume())
        return (False, self.register_failure())

    def consume(self) -> "HashedOneTimeCode":
        """Return a copy marked used now. Assign back and commit to enforce single-use."""
        return self._copy(used_at=_now())

    def register_failure(self) -> "HashedOneTimeCode":
        """Return a copy with the failed-attempt counter incremented. Assign back and commit."""
        return self._copy(attempts=self.attempts + 1)

    def _copy(self, **changes: Any) -> "HashedOneTimeCode":
        data: dict[str, Any] = {
            "expires_at": self.expires_at,
            "used_at": self.used_at,
            "attempts": self.attempts,
            "max_attempts": self._max_attempts,
        }
        data.update(changes)
        return HashedOneTimeCode(self.hash_string, self._backend, **data)

    def __hash__(self) -> int:
        return hash(self.hash_string)


class OneTimeCode(TypeDecorator[Any]):
    """Stores a transient one-time code hashed, with expiry and single-use state in JSON.

    The column holds ``{"hash", "expires_at", "used_at", "attempts"}`` so the full lifecycle
    lives in one value: an expired or already-redeemed code fails verification, and the code
    can lock after ``max_attempts`` failures. Reads return a :class:`HashedOneTimeCode`.
    Requires an explicit backend.
    """

    impl = JsonB
    cache_ok = True

    def __init__(
        self,
        backend: "HashingBackend",
        ttl_seconds: "Optional[int]" = None,
        max_attempts: "Optional[int]" = 3,
        **kwargs: Any,
    ) -> None:
        """Initialize the OneTimeCode type.

        Single-use is always enforced (a successful redemption marks the code used);
        ``max_attempts`` governs how many *wrong* guesses lock the code before then.

        Args:
            backend: The hashing backend used to hash and verify codes.
            ttl_seconds: Lifetime of a written code in seconds, or None for no expiry.
            max_attempts: Wrong-guess ceiling after which a code locks. Defaults to 3; pass
                None to disable the lockout (the code stays single-use and still expires).
            **kwargs: Additional arguments passed to the underlying JSON type.
        """
        super().__init__(**kwargs)
        self.backend = backend
        self.ttl_seconds = ttl_seconds
        self.max_attempts = max_attempts

    def __repr__(self) -> str:
        """Return a reconstructable representation for Alembic autogenerate."""
        return (
            f"{type(self).__name__}(backend=sa.{self.backend.__class__.__name__}(), "
            f"ttl_seconds={self.ttl_seconds}, max_attempts={self.max_attempts})"
        )

    @property
    def python_type(self) -> "type[dict[str, Any]]":
        """Returns the Python type for this type decorator."""
        return dict

    def process_bind_param(self, value: Any, dialect: Any) -> "Optional[dict[str, Any]]":
        """Hash a new code or serialize an updated wrapper to the stored JSON shape.

        Args:
            value: A plaintext code, an updated :class:`HashedOneTimeCode`, or None.
            dialect: The SQLAlchemy dialect.

        Returns:
            The JSON-serializable state dict, or None.
        """
        if value is None:
            return None
        if isinstance(value, HashedOneTimeCode):
            return {
                "hash": value.hash_string,
                "expires_at": value.expires_at,
                "used_at": value.used_at,
                "attempts": value.attempts,
            }
        expires_at = _now() + self.ttl_seconds if self.ttl_seconds is not None else None
        return {
            "hash": str(self.backend.hash(value)),
            "expires_at": expires_at,
            "used_at": None,
            "attempts": 0,
        }

    def process_result_value(self, value: Any, dialect: Any) -> "Optional[HashedOneTimeCode]":
        """Wrap the stored JSON state in a :class:`HashedOneTimeCode`.

        Args:
            value: The stored JSON object, or None.
            dialect: The SQLAlchemy dialect.

        Returns:
            A HashedOneTimeCode over the stored state, or None.
        """
        if value is None:
            return None
        if isinstance(value, (bytes, str)):
            value = decode_json(value)
        return HashedOneTimeCode(
            value["hash"],
            self.backend,
            expires_at=value.get("expires_at"),
            used_at=value.get("used_at"),
            attempts=value.get("attempts", 0),
            max_attempts=self.max_attempts,
        )
