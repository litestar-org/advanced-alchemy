"""One-time-code column type (hashed, single-use).

Stores a transient one-time code (email/SMS OTP) as a hash, reusing the
password-hash backends. Expiry, single-use invalidation, and attempt
throttling are the responsibility of the caller at the model/service layer
(for example an ``expires_at`` column plus deleting the code after a
successful verification); this type only hashes and verifies.
"""

from typing import Any

from advanced_alchemy.types.password_hash.base import HashedPassword, PasswordHash

__all__ = ("HashedOneTimeCode", "OneTimeCode")


class HashedOneTimeCode(HashedPassword):
    """Read-side wrapper for a hashed one-time code.

    Inherits :meth:`~advanced_alchemy.types.password_hash.base.HashedPassword.verify` and
    :meth:`~advanced_alchemy.types.password_hash.base.HashedPassword.verify_and_update`.
    Verification is single-use by convention: the caller should invalidate the stored code
    after a successful verify.
    """


class OneTimeCode(PasswordHash):
    """Stores a transient one-time code as a hash, returning :class:`HashedOneTimeCode` on read.

    Mechanically identical to :class:`~advanced_alchemy.types.password_hash.base.PasswordHash`;
    provided for intent and to return a one-time-code-specific wrapper. Requires an explicit
    backend. Expiry, single-use enforcement, and attempt throttling are model/service-layer
    concerns, not handled by this type.
    """

    cache_ok = True

    def process_result_value(self, value: Any, dialect: Any) -> "Any":
        """Wrap the stored hash in a :class:`HashedOneTimeCode`.

        Args:
            value: The stored hash value.
            dialect: The SQLAlchemy dialect.

        Returns:
            A HashedOneTimeCode over the stored hash, or None.
        """
        if value is None:
            return value
        return HashedOneTimeCode(str(value), self.backend)
