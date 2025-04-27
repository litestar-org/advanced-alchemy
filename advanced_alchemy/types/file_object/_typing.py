"""Internal typing helpers for file_object, handling optional Pydantic integration."""

from typing import Any, Protocol, TypeVar, runtime_checkable

# Define a generic type variable for CoreSchema placeholder if needed
CoreSchemaT = TypeVar("CoreSchemaT")

try:
    # Attempt to import real Pydantic components
    from pydantic import GetCoreSchemaHandler  # pyright: ignore
    from pydantic_core import core_schema  # pyright: ignore

    PYDANTIC_INSTALLED = True

except ImportError:
    PYDANTIC_INSTALLED = False  # pyright: ignore

    @runtime_checkable
    class GetCoreSchemaHandler(Protocol):  # type: ignore[no-redef]
        """Placeholder for Pydantic's GetCoreSchemaHandler."""

        def __call__(self, source_type: Any) -> Any: ...

        def __getattr__(self, item: str) -> Any:  # Allow arbitrary attribute access
            return Any

    # Define a placeholder for core_schema module
    class CoreSchemaModulePlaceholder:
        """Placeholder for pydantic_core.core_schema module."""

        # Define placeholder types/functions used in FileObject.__get_pydantic_core_schema__
        CoreSchema = Any  # Placeholder for the CoreSchema type itself

        def __getattr__(self, name: str) -> Any:
            """Return a dummy function/type for any requested attribute."""

            def dummy_schema_func(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
                return Any

            return dummy_schema_func

    core_schema = CoreSchemaModulePlaceholder()  # type: ignore[assignment]

__all__ = ("GetCoreSchemaHandler", "core_schema")
