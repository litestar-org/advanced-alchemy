"""Unit tests for statement filters, relationship filtering, and cache keys."""

from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import Column, ColumnElement, ForeignKey, Integer, String, Table, create_engine, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, with_loader_criteria

from advanced_alchemy.filters import (
    CollectionFilter,
    ComparisonFilter,
    MultiFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    RelationshipFilter,
    SearchFilter,
)
from advanced_alchemy.repository._util import _build_cache_key


class FilterUnitBase(DeclarativeBase):
    """Isolated declarative base for filter unit tests."""


post_tag_link = Table(
    "filter_unit_post_tag",
    FilterUnitBase.metadata,
    Column("post_id", ForeignKey("filter_unit_post.id"), primary_key=True),
    Column("tag_id", ForeignKey("filter_unit_tag.id"), primary_key=True),
)


class UnitAuthor(FilterUnitBase):
    """Author model for filter unit tests."""

    __tablename__ = "filter_unit_author"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    posts: Mapped[list[UnitPost]] = relationship(back_populates="author")


class UnitTag(FilterUnitBase):
    """Tag model for filter unit tests."""

    __tablename__ = "filter_unit_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    deleted_at: Mapped[Optional[int]] = mapped_column(Integer, default=None, nullable=True)


class UnitPost(FilterUnitBase):
    """Post model for filter unit tests."""

    __tablename__ = "filter_unit_post"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    author_id: Mapped[int] = mapped_column(ForeignKey("filter_unit_author.id"))
    author: Mapped[UnitAuthor] = relationship(back_populates="posts")
    tags: Mapped[list[UnitTag]] = relationship(secondary=post_tag_link)


class UnitCategory(FilterUnitBase):
    """Self-referential category model for filter unit tests."""

    __tablename__ = "filter_unit_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("filter_unit_category.id"), nullable=True)
    parent: Mapped[Optional[UnitCategory]] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[UnitCategory]] = relationship(back_populates="parent")


class UnitPerson(FilterUnitBase):
    """Joined-table inheritance base model."""

    __tablename__ = "filter_unit_person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    __mapper_args__ = {"polymorphic_on": "kind", "polymorphic_identity": "person"}


class UnitEngineer(UnitPerson):
    """Joined-table inheritance child model."""

    __tablename__ = "filter_unit_engineer"

    id: Mapped[int] = mapped_column(ForeignKey("filter_unit_person.id"), primary_key=True)
    level: Mapped[int] = mapped_column(Integer)
    gadgets: Mapped[list[UnitGadget]] = relationship(back_populates="owner")
    __mapper_args__ = {"polymorphic_identity": "engineer"}


class UnitGadget(FilterUnitBase):
    """Related model owned by a JTI subclass."""

    __tablename__ = "filter_unit_gadget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(50))
    owner_id: Mapped[int] = mapped_column(ForeignKey("filter_unit_engineer.id"))
    owner: Mapped[UnitEngineer] = relationship(back_populates="gadgets")


class UnitCompositeParent(FilterUnitBase):
    """Parent model for composite primary key validation tests."""

    __tablename__ = "filter_unit_comp_parent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    items: Mapped[list[UnitCompositeChild]] = relationship(back_populates="parent")


class UnitCompositeChild(FilterUnitBase):
    """Child model with a composite primary key."""

    __tablename__ = "filter_unit_comp_child"

    parent_id: Mapped[int] = mapped_column(ForeignKey("filter_unit_comp_parent.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent: Mapped[UnitCompositeParent] = relationship(back_populates="items")


@pytest.fixture
def unit_session() -> Session:
    """Create a populated SQLite in-memory session for unit filter queries."""
    engine = create_engine("sqlite:///:memory:")
    FilterUnitBase.metadata.create_all(engine)
    with Session(engine) as session:
        ada = UnitAuthor(name="Ada Lovelace")
        grace = UnitAuthor(name="Grace Hopper")
        tag_py = UnitTag(name="python")
        tag_sql = UnitTag(name="sqlalchemy")
        tag_old = UnitTag(name="retired", deleted_at=1)

        post_1 = UnitPost(title="Notes on Engine", author=ada, tags=[tag_py, tag_sql])
        post_2 = UnitPost(title="Compiler Alchemy", author=grace, tags=[tag_sql, tag_old])
        post_3 = UnitPost(title="Untagged Draft", author=grace, tags=[])

        root = UnitCategory(name="Root")
        sub = UnitCategory(name="Sub", parent=root)
        other = UnitCategory(name="Other")
        leaf = UnitCategory(name="Leaf", parent=other)

        eng_1 = UnitEngineer(name="Ada", level=5, gadgets=[UnitGadget(label="Scope")])
        eng_2 = UnitEngineer(name="Bob", level=2, gadgets=[UnitGadget(label="Meter")])

        session.add_all(
            [ada, grace, tag_py, tag_sql, tag_old, post_1, post_2, post_3, root, sub, other, leaf, eng_1, eng_2]
        )
        session.commit()
        return session


@pytest.mark.parametrize(
    ("search_filter", "expected_titles"),
    [
        (SearchFilter(UnitPost.title, "Alchemy"), ["Compiler Alchemy"]),
        (SearchFilter({UnitPost.title}, "engine", ignore_case=True), ["Notes on Engine"]),
        (NotInSearchFilter(UnitPost.title, "Alchemy"), ["Notes on Engine", "Untagged Draft"]),
    ],
)
def test_search_filter_with_instrumented_attribute(
    unit_session: Session,
    search_filter: SearchFilter,
    expected_titles: list[str],
) -> None:
    """SearchFilter and NotInSearchFilter accept InstrumentedAttribute references."""
    stmt = search_filter.append_to_statement(select(UnitPost), UnitPost)
    titles = sorted(row.title for row in unit_session.scalars(stmt).all())
    assert titles == expected_titles


def test_comparison_filter_iendswith(unit_session: Session) -> None:
    """ComparisonFilter iendswith matches suffix case-insensitively."""
    stmt = ComparisonFilter("title", "iendswith", "alchemy").append_to_statement(select(UnitPost), UnitPost)
    assert [row.title for row in unit_session.scalars(stmt).all()] == ["Compiler Alchemy"]

    non_match = ComparisonFilter("title", "iendswith", "Compiler").append_to_statement(select(UnitPost), UnitPost)
    assert unit_session.scalars(non_match).all() == []


def test_collection_and_not_in_collection_relationship_parity(unit_session: Session) -> None:
    """CollectionFilter and NotInCollectionFilter handle relationships symmetrically."""
    tag_py = unit_session.scalars(select(UnitTag).where(UnitTag.name == "python")).one()

    in_stmt = CollectionFilter(UnitPost.tags, [tag_py.id]).append_to_statement(select(UnitPost), UnitPost)
    assert [row.title for row in unit_session.scalars(in_stmt).all()] == ["Notes on Engine"]

    empty_stmt = CollectionFilter(UnitPost.tags, []).append_to_statement(select(UnitPost), UnitPost)
    assert unit_session.scalars(empty_stmt).all() == []

    not_in_stmt = NotInCollectionFilter(UnitPost.tags, [tag_py.id]).append_to_statement(select(UnitPost), UnitPost)
    assert sorted(row.title for row in unit_session.scalars(not_in_stmt).all()) == [
        "Compiler Alchemy",
        "Untagged Draft",
    ]

    empty_not_in_stmt = NotInCollectionFilter(UnitPost.tags, []).append_to_statement(select(UnitPost), UnitPost)
    assert len(unit_session.scalars(empty_not_in_stmt).all()) == 3


@pytest.mark.parametrize("filter_cls", [CollectionFilter, NotInCollectionFilter])
def test_collection_filter_relationship_composite_pk_raises(filter_cls: type[CollectionFilter[int]]) -> None:
    """Relationship targets with composite primary keys raise ValueError."""
    with pytest.raises(ValueError, match="composite primary keys"):
        filter_cls(field_name="items", values=[1]).append_to_statement(
            select(UnitCompositeParent),
            UnitCompositeParent,
        )


def test_relationship_filter_self_referential_retains_inner_from(unit_session: Session) -> None:
    """Self-referential RelationshipFilter aliases the inner FROM table cleanly."""
    stmt_attr = RelationshipFilter(
        UnitCategory.children,
        [ComparisonFilter(UnitCategory.name, "eq", "Sub")],
    ).append_to_statement(select(UnitCategory), UnitCategory)
    sql = str(stmt_attr.compile(dialect=sqlite.dialect()))
    assert "FROM filter_unit_category AS filter_unit_category_1" in sql
    assert [row.name for row in unit_session.scalars(stmt_attr).all()] == ["Root"]

    stmt_expr = RelationshipFilter(
        UnitCategory.children,
        [UnitCategory.name == "Leaf"],
    ).append_to_statement(select(UnitCategory), UnitCategory)
    assert [row.name for row in unit_session.scalars(stmt_expr).all()] == ["Other"]


def test_relationship_filter_multihop_jti_and_loader_criteria(unit_session: Session) -> None:
    """Multi-hop, JTI, and loader criteria subqueries compile and filter accurately."""
    multi_hop_stmt = RelationshipFilter(
        (UnitAuthor.posts, UnitPost.tags),
        [ComparisonFilter(UnitTag.name, "eq", "python")],
    ).append_to_statement(select(UnitAuthor), UnitAuthor)
    assert [row.name for row in unit_session.scalars(multi_hop_stmt).all()] == ["Ada Lovelace"]

    negated_stmt = RelationshipFilter(UnitPost.tags, negate=True).append_to_statement(select(UnitPost), UnitPost)
    assert [row.title for row in unit_session.scalars(negated_stmt).all()] == ["Untagged Draft"]

    jti_stmt = RelationshipFilter(
        UnitEngineer.gadgets,
        [UnitGadget.label == "Scope"],
    ).append_to_statement(select(UnitEngineer), UnitEngineer)
    compiled_sql = str(jti_stmt.compile())
    assert "EXISTS" in compiled_sql
    assert [row.name for row in unit_session.scalars(jti_stmt).all()] == ["Ada"]

    def _tag_is_active(cls: type[UnitTag]) -> ColumnElement[bool]:
        return cls.deleted_at.is_(None)

    criteria_stmt = select(UnitPost).options(with_loader_criteria(UnitTag, _tag_is_active, include_aliases=True))
    filtered_stmt = RelationshipFilter(UnitPost.tags, [UnitTag.name == "retired"]).append_to_statement(
        criteria_stmt,
        UnitPost,
    )
    assert unit_session.scalars(filtered_stmt).all() == []


def test_relationship_filter_validation_errors() -> None:
    """RelationshipFilter validates empty paths, unrelated owners, and invalid identifiers."""
    with pytest.raises(ValueError, match="at least one relationship hop"):
        RelationshipFilter((), []).append_to_statement(select(UnitPost), UnitPost)

    with pytest.raises(ValueError, match="does not belong to model"):
        RelationshipFilter(UnitAuthor.posts, []).append_to_statement(select(UnitPost), UnitPost)

    with pytest.raises(ValueError, match="Invalid relationship name"):
        RelationshipFilter("tags; DROP TABLE", []).append_to_statement(select(UnitPost), UnitPost)


def test_multifilter_relationship_allowlist_and_depth_guards() -> None:
    """MultiFilter validates relationship names against allowed_relationships and max_relationship_depth."""
    disallowed = MultiFilter(
        filters={"and_": [{"type": "relationship", "relationship": "author", "filters": []}]},
        allowed_relationships={"tags"},
    )
    with pytest.raises(ValueError, match="not permitted"):
        disallowed.append_to_statement(select(UnitPost), UnitPost)

    too_deep = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "relationship",
                    "relationship": "posts",
                    "filters": [{"type": "relationship", "relationship": "tags", "filters": []}],
                }
            ]
        },
        max_relationship_depth=1,
    )
    with pytest.raises(ValueError, match="exceeds maximum allowed depth"):
        too_deep.append_to_statement(select(UnitAuthor), UnitAuthor)

    allowed = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "relationship",
                    "relationship": "tags",
                    "filters": [{"type": "collection", "field_name": "name", "values": ["python"]}],
                }
            ]
        },
        allowed_relationships={"tags"},
        max_relationship_depth=2,
    )
    stmt = allowed.append_to_statement(select(UnitPost), UnitPost)
    assert "EXISTS" in str(stmt.compile(dialect=sqlite.dialect()))


def test_build_cache_key_relationship_filter_handling() -> None:
    """Cache keys are deterministic for StatementFilter trees and None when raw expressions are nested."""
    key_a = _build_cache_key(
        model_name="UnitPost",
        version_token="v1",
        method="list",
        filters=[RelationshipFilter(UnitPost.tags, [ComparisonFilter(UnitTag.name, "eq", "python")])],
        kwargs={},
        order_by=None,
        execution_options={},
        uniquify=False,
    )
    key_b = _build_cache_key(
        model_name="UnitPost",
        version_token="v1",
        method="list",
        filters=[RelationshipFilter(UnitPost.tags, [ComparisonFilter(UnitTag.name, "eq", "python")])],
        kwargs={},
        order_by=None,
        execution_options={},
        uniquify=False,
    )
    key_other = _build_cache_key(
        model_name="UnitPost",
        version_token="v1",
        method="list",
        filters=[RelationshipFilter(UnitPost.tags, [ComparisonFilter(UnitTag.name, "eq", "rust")])],
        kwargs={},
        order_by=None,
        execution_options={},
        uniquify=False,
    )
    assert key_a is not None
    assert key_a == key_b
    assert key_a != key_other

    raw_key = _build_cache_key(
        model_name="UnitPost",
        version_token="v1",
        method="list",
        filters=[RelationshipFilter(UnitPost.tags, [UnitTag.name == "python"])],
        kwargs={},
        order_by=None,
        execution_options={},
        uniquify=False,
    )
    assert raw_key is None
