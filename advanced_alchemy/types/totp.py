"""TOTP shared-secret column type with pyotp-backed helpers."""

from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.encrypted_string import EncryptedString, EncryptionBackend, FernetBackend
from advanced_alchemy.typing import PYOTP_INSTALLED

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

__all__ = ("TOTPProvider", "TOTPSecret", "generate_totp_secret")


def generate_totp_secret(length: int = 32) -> str:
    """Generate a new random base32 TOTP secret.

    Args:
        length: Number of base32 characters. Defaults to 32.

    Raises:
        MissingDependencyError: If the ``pyotp`` package is not installed.

    Returns:
        A base32-encoded secret suitable for an authenticator app.
    """
    if not PYOTP_INSTALLED:
        raise MissingDependencyError(package="pyotp")
    import pyotp

    return pyotp.random_base32(length=length)


class TOTPProvider:
    """Read-side wrapper exposing pyotp operations over a decrypted secret.

    The secret must be a valid base32 string. pyotp decodes it lazily, so a malformed
    secret raises :exc:`binascii.Error` on the first call that decodes it (``now``/``verify``).
    """

    __slots__ = ("_digest", "_digits", "_interval", "_issuer", "_secret")

    def __init__(
        self,
        secret: str,
        *,
        digits: int = 6,
        interval: int = 30,
        digest: "Optional[Any]" = None,
        issuer: "Optional[str]" = None,
    ) -> None:
        """Initialize the provider.

        Args:
            secret: The decrypted base32 secret.
            digits: Number of digits in generated codes. Defaults to 6.
            interval: Time step in seconds. Defaults to 30.
            digest: Hash algorithm passed to pyotp (None selects SHA1).
            issuer: Default issuer used for provisioning URIs.

        Raises:
            MissingDependencyError: If the ``pyotp`` package is not installed.
        """
        if not PYOTP_INSTALLED:
            raise MissingDependencyError(package="pyotp")
        self._secret = secret
        self._digits = digits
        self._interval = interval
        self._digest = digest
        self._issuer = issuer

    @property
    def secret(self) -> str:
        """The decrypted base32 secret."""
        return self._secret

    def _totp(self) -> Any:
        import pyotp

        return pyotp.TOTP(
            self._secret,
            digits=self._digits,
            digest=self._digest,
            interval=self._interval,
            issuer=self._issuer,
        )

    def now(self) -> str:
        """Return the current TOTP code.

        Returns:
            The zero-padded code for the current time step.
        """
        return cast("str", self._totp().now())

    def verify(self, code: str, valid_window: int = 1) -> bool:
        """Verify a code, tolerating ``valid_window`` ticks of clock drift each way.

        Args:
            code: The candidate code.
            valid_window: Number of time steps of drift accepted on each side. Defaults to 1.

        Returns:
            True if the code is valid within the window, False otherwise.
        """
        return cast("bool", self._totp().verify(code, valid_window=valid_window))

    def provisioning_uri(self, name: "Optional[str]" = None, issuer_name: "Optional[str]" = None) -> str:
        """Return an ``otpauth://`` provisioning URI for QR enrollment.

        Args:
            name: The account name (e.g. the user's email).
            issuer_name: The issuer label; falls back to the type's configured issuer.

        Returns:
            The provisioning URI string.
        """
        return cast("str", self._totp().provisioning_uri(name=name, issuer_name=issuer_name or self._issuer))


class TOTPSecret(EncryptedString):
    """Stores a TOTP shared secret encrypted at rest, returning a :class:`TOTPProvider` on read.

    Storage is identical to :class:`EncryptedString`; the read side wraps the decrypted secret
    in a :class:`TOTPProvider` so callers can generate and verify codes. Requires ``pyotp``.
    """

    cache_ok = True

    def __init__(
        self,
        key: "Union[str, bytes, Callable[[], Union[str, bytes]]]",
        backend: "type[EncryptionBackend]" = FernetBackend,
        digits: int = 6,
        interval: int = 30,
        digest: "Optional[Any]" = None,
        issuer: "Optional[str]" = None,
        length: "Optional[int]" = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the TOTPSecret type.

        Args:
            key: The encryption key (str/bytes or a callable returning one). Required: unlike
                :class:`EncryptedString`, this new type has no deprecated random default.
            backend: The encryption backend class. Defaults to FernetBackend.
            digits: Number of digits in generated codes. Defaults to 6.
            interval: Time step in seconds. Defaults to 30.
            digest: Hash algorithm passed to pyotp (None selects SHA1).
            issuer: Default issuer used for provisioning URIs.
            length: The unencrypted string length (documentation only).
            **kwargs: Additional arguments passed to the underlying String type.

        Raises:
            MissingDependencyError: If the ``pyotp`` package is not installed.
        """
        if not PYOTP_INSTALLED:
            raise MissingDependencyError(package="pyotp")
        super().__init__(key=key, backend=backend, length=length, **kwargs)
        self.digits = digits
        self.interval = interval
        self.digest = digest
        self.issuer = issuer

    def __repr__(self) -> str:
        """Return a reconstructable representation including the TOTP parameters.

        Overrides :class:`EncryptedString` so Alembic autogenerate reconstructs the type with
        its configured ``digits``/``interval``/``digest``/``issuer`` rather than the defaults.
        """
        key_repr = self.key.__name__ if callable(self.key) else repr(self.key)
        return (
            f"{type(self).__name__}(key={key_repr}, backend={self.backend.__class__.__name__}, "
            f"digits={self.digits}, interval={self.interval}, digest={self.digest!r}, "
            f"issuer={self.issuer!r}, length={self.length})"
        )

    def process_bind_param(self, value: Any, dialect: "Dialect") -> "Union[str, None]":
        """Accept a raw secret string or a :class:`TOTPProvider`, then encrypt as usual.

        Args:
            value: The secret string or a TOTPProvider.
            dialect: The SQLAlchemy dialect.

        Returns:
            The encrypted secret, or None.
        """
        if isinstance(value, TOTPProvider):
            value = value.secret
        return super().process_bind_param(value, dialect)

    def process_result_value(self, value: Any, dialect: "Dialect") -> "Optional[TOTPProvider]":  # type: ignore[override]
        """Decrypt the stored secret and wrap it in a :class:`TOTPProvider`.

        Args:
            value: The stored encrypted value.
            dialect: The SQLAlchemy dialect.

        Returns:
            A TOTPProvider over the decrypted secret, or None.
        """
        decrypted = super().process_result_value(value, dialect)
        if decrypted is None:
            return None
        return TOTPProvider(
            decrypted,
            digits=self.digits,
            interval=self.interval,
            digest=self.digest,
            issuer=self.issuer,
        )
