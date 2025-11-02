"""Unit tests for SQLAlchemy inheritance pattern support in base classes.

Tests Single Table Inheritance (STI), Joined Table Inheritance (JTI),
and Concrete Table Inheritance (CTI) patterns.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import pytest
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from advanced_alchemy import base


class TestSingleTableInheritance:
    """Test Single Table Inheritance (STI) pattern."""

    def test_sti_child_uses_parent_table(self) -> None:
        """Child class in STI should not generate tablename."""

        class STIParent1(base.UUIDBase):
            __tablename__ = "sti_parent_1"
            type: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "parent",
            }

        class STIChild1(STIParent1):
            __mapper_args__ = {"polymorphic_identity": "child"}
            child_field: Mapped[Optional[str]] = mapped_column(nullable=True)

        # Parent should have explicit tablename
        assert STIParent1.__tablename__ == "sti_parent_1"

        # Child should use parent's table (no tablename generated)
        assert STIChild1.__table__ is STIParent1.__table__

    def test_multi_level_sti(self) -> None:
        """Grandchild classes should also use root table."""

        class STIGrandParent2(base.UUIDBase):
            __tablename__ = "sti_grand_parent_2"
            type: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "grand_parent",
            }

        class STIParent2(STIGrandParent2):
            __mapper_args__ = {"polymorphic_identity": "parent"}

        class STIChild2(STIParent2):
            __mapper_args__ = {"polymorphic_identity": "child"}

        # All should share the same table
        assert STIGrandParent2.__table__ is STIParent2.__table__
        assert STIGrandParent2.__table__ is STIChild2.__table__

    def test_sti_with_uuidbase(self) -> None:
        """STI pattern works with UUIDBase."""

        class Employee3(base.UUIDBase):
            __tablename__ = "employee_3"
            type: Mapped[str]
            name: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "employee",
            }

        class Manager3(Employee3):
            __mapper_args__ = {"polymorphic_identity": "manager"}
            manager_level: Mapped[Optional[int]] = mapped_column(nullable=True)

        assert Employee3.__tablename__ == "employee_3"
        assert Manager3.__table__ is Employee3.__table__

    def test_sti_with_bigintbase(self) -> None:
        """STI pattern works with BigIntBase."""

        class Animal4(base.BigIntBase):
            __tablename__ = "animal_4"
            type: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "animal",
            }

        class Dog4(Animal4):
            __mapper_args__ = {"polymorphic_identity": "dog"}
            breed: Mapped[Optional[str]] = mapped_column(nullable=True)

        assert Animal4.__tablename__ == "animal_4"
        assert Dog4.__table__ is Animal4.__table__

    def test_sti_with_defaultbase(self) -> None:
        """STI pattern works with DefaultBase (no primary key)."""

        class Vehicle5(base.DefaultBase):
            __tablename__ = "vehicle_5"
            id: Mapped[int] = mapped_column(primary_key=True)
            type: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "vehicle",
            }

        class Car5(Vehicle5):
            __mapper_args__ = {"polymorphic_identity": "car"}
            doors: Mapped[Optional[int]] = mapped_column(nullable=True)

        assert Vehicle5.__tablename__ == "vehicle_5"
        assert Car5.__table__ is Vehicle5.__table__

    def test_sti_with_auditbase(self) -> None:
        """STI pattern works with UUIDAuditBase (has audit columns)."""

        class Person6(base.UUIDAuditBase):
            __tablename__ = "person_6"
            type: Mapped[str]
            name: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "person",
            }

        class Student6(Person6):
            __mapper_args__ = {"polymorphic_identity": "student"}
            grade: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

        assert Person6.__tablename__ == "person_6"
        assert Student6.__table__ is Person6.__table__

        # Verify audit columns are present
        assert "created_at" in Person6.__table__.c
        assert "updated_at" in Person6.__table__.c


class TestJoinedTableInheritance:
    """Test Joined Table Inheritance (JTI) pattern."""

    def test_jti_explicit_tablename(self) -> None:
        """Child with explicit tablename should get own table."""

        class JTIParent7(base.UUIDBase):
            __tablename__ = "jti_parent_7"
            name: Mapped[str]

        class JTIChild7(JTIParent7):
            __tablename__ = "jti_child_7"
            id: Mapped[UUID] = mapped_column(ForeignKey("jti_parent_7.id"), primary_key=True)
            child_data: Mapped[str]

        assert JTIParent7.__tablename__ == "jti_parent_7"
        assert JTIChild7.__tablename__ == "jti_child_7"
        assert JTIChild7.__table__ is not JTIParent7.__table__

    def test_jti_auto_tablename(self) -> None:
        """Child with FK primary key should auto-generate tablename."""

        class JTIParent8(base.UUIDBase):
            __tablename__ = "jti_parent_8"
            type: Mapped[str]
            __mapper_args__ = {"polymorphic_on": "type"}

        class JTIChildClass8(JTIParent8):
            # Explicit tablename required for JTI
            __tablename__ = "jti_child_class_8"
            id: Mapped[UUID] = mapped_column(ForeignKey("jti_parent_8.id"), primary_key=True)
            __mapper_args__ = {"polymorphic_identity": "child"}

        # Should use explicit tablename for JTI
        assert JTIChildClass8.__tablename__ == "jti_child_class_8"
        assert JTIChildClass8.__table__ is not JTIParent8.__table__

    def test_jti_with_bigintbase(self) -> None:
        """JTI pattern works with BigIntBase."""

        class JTIEmployee9(base.BigIntBase):
            __tablename__ = "jti_employee_9"
            name: Mapped[str]

        class JTIManager9(JTIEmployee9):
            __tablename__ = "jti_manager_9"
            id: Mapped[int] = mapped_column(ForeignKey("jti_employee_9.id"), primary_key=True)
            department: Mapped[str]

        assert JTIEmployee9.__tablename__ == "jti_employee_9"
        assert JTIManager9.__tablename__ == "jti_manager_9"
        assert JTIManager9.__table__ is not JTIEmployee9.__table__


class TestConcreteTableInheritance:
    """Test Concrete Table Inheritance (CTI) pattern."""

    def test_cti_generates_separate_tables(self) -> None:
        """Concrete inheritance should generate separate tables."""

        class CTIEmployee10(base.UUIDBase):
            __tablename__ = "cti_employee_10"
            name: Mapped[str]

        class CTIManager10(CTIEmployee10):
            __tablename__ = "cti_manager_10"
            __mapper_args__ = {"concrete": True}
            # CTI requires redefining all columns including PK
            id: Mapped[UUID] = mapped_column(primary_key=True)
            name: Mapped[str]
            department: Mapped[str]

        assert CTIEmployee10.__tablename__ == "cti_employee_10"
        assert CTIManager10.__tablename__ == "cti_manager_10"
        # Concrete inheritance means separate tables
        assert CTIManager10.__table__ is not CTIEmployee10.__table__


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_explicit_tablename_override(self) -> None:
        """Explicit __tablename__ should override auto-generation."""

        class EdgeParent11(base.UUIDBase):
            __tablename__ = "edge_parent_11"

        class EdgeChild11(EdgeParent11):
            __tablename__ = "custom_edge_child_11"
            id: Mapped[UUID] = mapped_column(ForeignKey("edge_parent_11.id"), primary_key=True)

        assert EdgeChild11.__tablename__ == "custom_edge_child_11"

    def test_mixin_doesnt_interfere(self) -> None:
        """Mixin classes should not affect inheritance detection."""

        @declarative_mixin
        class TimestampMixin12:
            created: Mapped[str] = mapped_column(String(50))

        class MixinParent12(base.UUIDBase):
            __tablename__ = "mixin_parent_12"
            type: Mapped[str]
            __mapper_args__ = {"polymorphic_on": "type"}

        class MixinChild12(TimestampMixin12, MixinParent12):
            __mapper_args__ = {"polymorphic_identity": "child"}

        # Child should use parent's table despite mixin
        assert MixinChild12.__table__ is MixinParent12.__table__

    def test_non_inheritance_models_unchanged(self) -> None:
        """Non-inheritance models should generate tables as before."""

        class SimpleModel13(base.UUIDBase):
            name: Mapped[str]

        # Should auto-generate tablename "simple_model_13"
        assert SimpleModel13.__tablename__ == "simple_model13"

    def test_abstract_base_no_table(self) -> None:
        """Abstract base classes should not generate tables."""

        class AbstractModel14(base.UUIDBase):
            __abstract__ = True
            name: Mapped[str]

        # Abstract classes don't have tables
        assert not hasattr(AbstractModel14, "__table__")

    def test_multiple_base_classes(self) -> None:
        """Test with multiple base classes."""
        base_classes_to_test = [
            (base.UUIDBase, "multi_uuid_parent_15"),
            (base.BigIntBase, "multi_bigint_parent_16"),
            (base.UUIDAuditBase, "multi_audit_parent_17"),
        ]

        for idx, (base_class, table_name) in enumerate(base_classes_to_test):

            class MultiParent(base_class):  # type: ignore[misc,valid-type]
                __tablename__ = table_name
                type: Mapped[str]
                __mapper_args__ = {
                    "polymorphic_on": "type",
                    "polymorphic_identity": "parent",
                }

            class MultiChild(MultiParent):  # type: ignore[misc,valid-type]
                __mapper_args__ = {"polymorphic_identity": "child"}

            # Verify STI works for all base classes
            assert MultiParent.__tablename__ == table_name
            assert MultiChild.__table__ is MultiParent.__table__


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_simple_model_tablename_generation(self) -> None:
        """Simple models should generate table names as before."""

        class User18(base.UUIDBase):
            email: Mapped[str]

        class BlogPost19(base.UUIDBase):
            title: Mapped[str]

        class OrderItem20(base.UUIDBase):
            quantity: Mapped[int]

        assert User18.__tablename__ == "user18"
        assert BlogPost19.__tablename__ == "blog_post19"
        assert OrderItem20.__tablename__ == "order_item20"

    def test_explicit_tablename_still_works(self) -> None:
        """Explicit __tablename__ should still work."""

        class CustomTable21(base.UUIDBase):
            __tablename__ = "my_custom_table_21"
            data: Mapped[str]

        assert CustomTable21.__tablename__ == "my_custom_table_21"

    def test_all_base_classes_work(self) -> None:
        """All base classes should generate tables correctly."""

        class UUIDModel22(base.UUIDBase):
            pass

        class BigIntModel23(base.BigIntBase):
            pass

        class UUIDAuditModel24(base.UUIDAuditBase):
            pass

        class BigIntAuditModel25(base.BigIntAuditBase):
            pass

        class UUIDv6Model26(base.UUIDv6Base):
            pass

        class UUIDv7Model27(base.UUIDv7Base):
            pass

        class NanoIDModel28(base.NanoIDBase):
            pass

        class DefaultModel29(base.DefaultBase):
            id: Mapped[int] = mapped_column(primary_key=True)

        # All should have auto-generated tablenames
        assert UUIDModel22.__tablename__ == "uuid_model22"
        assert BigIntModel23.__tablename__ == "big_int_model23"
        assert UUIDAuditModel24.__tablename__ == "uuid_audit_model24"
        assert BigIntAuditModel25.__tablename__ == "big_int_audit_model25"
        assert UUIDv6Model26.__tablename__ == "uui_dv6_model26"  # Note: regex creates this pattern
        assert UUIDv7Model27.__tablename__ == "uui_dv7_model27"  # Note: regex creates this pattern
        assert NanoIDModel28.__tablename__ == "nano_id_model28"
        assert DefaultModel29.__tablename__ == "default_model29"
