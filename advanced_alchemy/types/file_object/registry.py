from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, overload

from advanced_alchemy._serialization import decode_json, encode_json
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.utils.module_loader import import_string
from advanced_alchemy.utils.singleton import SingletonMeta

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.base import StorageBackend

DEFAULT_BACKEND = (
    "advanced_alchemy.types.file_object.backends.obstore.ObstoreBackend"
    if find_spec("obstore")
    else "advanced_alchemy.types.file_object.backends.fsspec.FSSpecBackend"
)


class StorageRegistry(metaclass=SingletonMeta):
    """A provider for creating and managing threaded portals."""

    def __init__(
        self,
        json_serializer: "Callable[[Any], str]" = encode_json,
        json_deserializer: Callable[[Union[str, bytes]], Any] = decode_json,
        default_backend: "Union[str, type[StorageBackend]]" = DEFAULT_BACKEND,
    ) -> None:
        """Initialize the PortalProvider."""
        self._registry: dict[str, StorageBackend] = {}
        self.json_serializer = json_serializer
        self.json_deserializer = json_deserializer
        self.default_backend: str = (
            DEFAULT_BACKEND if isinstance(default_backend, str) else default_backend.__qualname__
        )

    def set_default_backend(self, default_backend: "Union[str, type[StorageBackend]]") -> None:
        """Set the default storage backend.

        Args:
            default_backend: The default storage backend
        """
        self.default_backend = default_backend if isinstance(default_backend, str) else default_backend.__qualname__

    def is_registered(self, key: str) -> bool:
        """Check if a storage backend is registered in the registry.

        Args:
            key: The key of the storage backend

        Returns:
            bool: True if the storage backend is registered, False otherwise.
        """
        return key in self._registry

    def get_backend(self, key: str) -> "StorageBackend":
        """Retrieve a configured storage backend from the registry.

        Returns:
            StorageBackend: The storage backend associaStorageBackendiven key.

        Raises:
            ImproperConfigurationError: If no storage backend is registered with the given key.
        """
        try:
            return self._registry[key]
        except KeyError as e:
            msg = f'No storage backend registered with key "{key}"'
            raise ImproperConfigurationError(msg) from e

    @overload
    def register_backend(self, value: "str") -> None: ...
    @overload
    def register_backend(self, value: "str", key: None = None) -> None: ...
    @overload
    def register_backend(self, value: "str", key: str) -> None: ...
    @overload
    def register_backend(self, value: "StorageBackend", key: None = None) -> None: ...
    @overload
    def register_backend(self, value: "StorageBackend", key: str) -> None: ...
    def register_backend(self, value: "Union[StorageBackend, str]", key: "Optional[str]" = None) -> None:
        """Register a new storage backend in the registry.

        Args:
            value: The storage backend to register.
            key: The key to register the storage backend with.

        Raises:
            ImproperConfigurationError: If a string value is provided without a key.
        """
        if isinstance(value, str):
            if key is None:
                msg = "key is required when registering a string value"
                raise ImproperConfigurationError(msg)
            self._registry[key] = import_string(self.default_backend)(fs=value, key=key)
        else:
            if key is not None:
                msg = "key is not allowed when registering a StorageBackend"
                raise ImproperConfigurationError(msg)
            self._registry[value.key] = value

    def unregister_backend(self, key: str) -> None:
        """Unregister a storage backend from the registry."""
        if key in self._registry:
            del self._registry[key]

    def clear_backends(self) -> None:
        """Clear the registry."""
        self._registry.clear()

    def registered_backends(self) -> list[str]:
        """Return a list of all registered keys."""
        return list(self._registry.keys())


storages = StorageRegistry()
