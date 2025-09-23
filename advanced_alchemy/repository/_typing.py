"""Repository typing utilities for optional dependency support.

Provides stubs and detection functions for numpy arrays to support
pgvector and other array-based types when numpy is not installed.
"""

from typing import Any

# Always define stub functions for type checking and fallback behavior


def is_numpy_array_stub(value: Any) -> bool:  # pragma: no cover
    """Check if value has numpy array-like characteristics (fallback implementation).

    When numpy is not installed, this checks for basic array-like attributes
    that indicate the value might be an array that needs special comparison handling.

    Args:
        value: Value to check.

    Returns:
        bool: True if value appears to be array-like.
    """
    return hasattr(value, "__array__") and hasattr(value, "dtype")  # pragma: no cover


def arrays_equal_stub(a: Any, b: Any) -> bool:
    """Fallback array equality comparison when numpy is not installed.

    When numpy is not available, we can't properly compare arrays,
    so we default to considering them different to trigger updates.
    This ensures safety but may cause unnecessary updates.

    Args:
        a: First value to compare.
        b: Second value to compare.

    Returns:
        bool: Always False when numpy is not available.
    """
    _, _ = a, b  # Unused parameters
    return False


# Try to import real numpy implementation at runtime
try:
    import numpy as np  # type: ignore[import-not-found,unused-ignore] # pyright: ignore[reportMissingImports]

    def is_numpy_array_real(value: Any) -> bool:
        """Check if value is a numpy array.

        Args:
            value: Value to check.

        Returns:
            bool: True if value is a numpy ndarray.
        """
        return isinstance(value, np.ndarray)  # pyright: ignore

    def arrays_equal_real(a: Any, b: Any) -> bool:
        """Compare numpy arrays for equality.

        Uses numpy.array_equal for proper array comparison.

        Args:
            a: First array to compare.
            b: Second array to compare.

        Returns:
            bool: True if arrays are equal.
        """
        return bool(np.array_equal(a, b))  # pyright: ignore

    is_numpy_array = is_numpy_array_real
    arrays_equal = arrays_equal_real
    NUMPY_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]

except ImportError:  # pragma: no cover
    is_numpy_array = is_numpy_array_stub
    arrays_equal = arrays_equal_stub
    NUMPY_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]


__all__ = (
    "NUMPY_INSTALLED",
    "arrays_equal",
    "arrays_equal_stub",
    "is_numpy_array",
    "is_numpy_array_stub",
)
