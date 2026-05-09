"""Bootstrap-level tests for the FilterSet facade machinery.

Covers the primitives introduced in Phase 3.1:

* ``UNSET`` sentinel — distinct from ``None``, falsy, singleton.
* ``FieldSpec`` — frozen dataclass; rejects mutation.
* ``BaseFieldFilter`` — ABC contract; lookup-set validation at construction.
* ``FilterValidationError`` — aggregates per-field coercion errors.

Concrete field filter behavior (``StringFilter``, ``NumberFilter``, …) is
covered separately in ``test_field_filters.py``.
"""

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from sqlalchemy import Column, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.exceptions import (
    AdvancedAlchemyError,
    FilterValidationError,
    ImproperConfigurationError,
)
from advanced_alchemy.filters import UNSET, BaseFieldFilter, FieldSpec

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Union

    from advanced_alchemy.filters._base import StatementFilter


class _Base(DeclarativeBase):
    pass


class _Thing(_Base):
    __tablename__ = "_thing_for_filterset_bootstrap"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class _ConcreteFilter(BaseFieldFilter):
    """Minimal concrete BaseFieldFilter for ABC contract testing."""

    supported_lookups: ClassVar[frozenset[str]] = frozenset({"exact", "in"})
    default_lookup: ClassVar[str] = "exact"

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        return raw

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        raise NotImplementedError


class TestUnsetSentinel:
    def test_unset_is_distinct_from_none(self) -> None:
        assert UNSET is not None

    def test_unset_is_falsy(self) -> None:
        assert not UNSET
        assert bool(UNSET) is False

    def test_unset_is_singleton(self) -> None:
        assert UNSET is UNSET
        assert type(UNSET)() is UNSET

    def test_unset_repr(self) -> None:
        assert repr(UNSET) == "UNSET"


class TestFilterValidationError:
    def test_inherits_from_advanced_alchemy_error(self) -> None:
        exc = FilterValidationError({"name": "bad value"})
        assert isinstance(exc, AdvancedAlchemyError)

    def test_carries_per_field_error_map(self) -> None:
        exc = FilterValidationError({"name": "must be str", "age": "must be int"})
        assert exc.errors == {"name": "must be str", "age": "must be int"}

    def test_errors_dict_is_a_copy(self) -> None:
        original = {"name": "bad"}
        exc = FilterValidationError(original)
        original["name"] = "changed"
        assert exc.errors == {"name": "bad"}

    def test_message_contains_each_field_error(self) -> None:
        exc = FilterValidationError({"name": "must be str", "age": "must be int"})
        rendered = str(exc)
        assert "name: must be str" in rendered
        assert "age: must be int" in rendered

    def test_empty_errors_allowed(self) -> None:
        exc = FilterValidationError({})
        assert exc.errors == {}


class TestFieldSpec:
    def test_is_frozen(self) -> None:
        spec = FieldSpec(
            path=("id",),
            column=cast("Column[Any]", _Thing.__table__.c.id),
            filter=_ConcreteFilter(),
        )
        with pytest.raises(FrozenInstanceError):
            spec.path = ("other",)  # type: ignore[misc]

    def test_carries_path_column_filter(self) -> None:
        flt = _ConcreteFilter()
        column = cast("Column[Any]", _Thing.__table__.c.id)
        spec = FieldSpec(path=("id",), column=column, filter=flt)
        assert spec.path == ("id",)
        assert spec.column is column
        assert spec.filter is flt

    def test_path_must_be_tuple(self) -> None:
        spec = FieldSpec(
            path=("a", "b"),
            column=cast("Column[Any]", _Thing.__table__.c.id),
            filter=_ConcreteFilter(),
        )
        assert isinstance(spec.path, tuple)


class TestBaseFieldFilterContract:
    def test_cannot_instantiate_abstract_base(self) -> None:
        with pytest.raises(TypeError):
            BaseFieldFilter()  # type: ignore[abstract]

    def test_default_lookups_uses_supported_set(self) -> None:
        flt = _ConcreteFilter()
        assert flt.lookups == frozenset({"exact", "in"})

    def test_explicit_lookups_subset_accepted(self) -> None:
        flt = _ConcreteFilter(lookups=["exact"])
        assert flt.lookups == frozenset({"exact"})

    def test_unsupported_lookup_raises_improper_config(self) -> None:
        with pytest.raises(ImproperConfigurationError) as ei:
            _ConcreteFilter(lookups=["startswith"])
        assert "startswith" in str(ei.value)

    def test_empty_lookups_raises_improper_config(self) -> None:
        with pytest.raises(ImproperConfigurationError):
            _ConcreteFilter(lookups=[])

    def test_default_value_defaults_to_unset(self) -> None:
        flt = _ConcreteFilter()
        assert flt.default_value is UNSET

    def test_default_value_can_be_provided(self) -> None:
        flt = _ConcreteFilter(default="hello")
        assert flt.default_value == "hello"

    def test_default_value_none_distinct_from_unset(self) -> None:
        flt = _ConcreteFilter(default=None)
        assert flt.default_value is None
        assert flt.default_value is not UNSET


class TestPackageReExports:
    def test_baseFieldFilter_importable_from_package(self) -> None:
        from advanced_alchemy.filters import BaseFieldFilter as Reexport

        assert Reexport is BaseFieldFilter

    def test_field_spec_importable_from_package(self) -> None:
        from advanced_alchemy.filters import FieldSpec as Reexport

        assert Reexport is FieldSpec

    def test_unset_importable_from_package(self) -> None:
        from advanced_alchemy.filters import UNSET as Reexport

        assert Reexport is UNSET
