"""Cursor pagination configuration: resolved settings, query names, and FilterSet cursor mode."""

import datetime as dt
from collections.abc import Iterator
from typing import Any, Optional

import pytest
from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from advanced_alchemy.config import SQLAlchemySyncConfig
from advanced_alchemy.exceptions import ImproperConfigurationError, InvalidCursorError
from advanced_alchemy.filters import CursorFilter, CursorKey, FilterSet, LimitOffsetFilter, OrderByFilter
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.utils.dependencies import (
    FilterConfig,
    resolve_cursor_defaults,
    resolve_cursor_settings,
    resolve_filter_aliases,
)


class ConfigBase(DeclarativeBase):
    pass


class Team(ConfigBase):
    __tablename__ = "cursor_config_team"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class Player(ConfigBase):
    __tablename__ = "cursor_config_player"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    goals: Mapped[int]
    joined: Mapped[Optional[dt.date]]
    team_id: Mapped[int] = mapped_column(ForeignKey(Team.id))
    team: Mapped[Team] = relationship()


class Players(FilterSet[Player]):
    filter_fields = {"goals": {"ge"}}
    sort_fields = ("name", "goals", "joined")
    config = {"pagination_type": "cursor", "pagination_size": 3, "pagination_max_size": 5, "sort_nulls": "last"}


class SignedPlayers(FilterSet[Player]):
    sort_fields = ("goals",)
    config = {"pagination_type": "cursor", "pagination_size": 4, "pagination_cursor_secret": "s3cret"}


class PlayerRepository(SQLAlchemySyncRepository[Player]):
    pass


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    ConfigBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Team(id=1, name="a"), Team(id=2, name="b")])
        db.add_all(
            Player(
                id=i,
                name=f"p{i % 4}",
                goals=i % 5,
                joined=None if i % 3 == 0 else dt.date(2020, 1, i),
                team_id=1 + i % 2,
            )
            for i in range(1, 15)
        )
        db.commit()
        yield db
    engine.dispose()


BASE: FilterConfig = {"pagination_type": "cursor", "sort_field": "created_at", "sort_order": "desc"}


def test_settings_resolve_defaults_and_allowlist() -> None:
    settings = resolve_cursor_settings({**BASE, "sort_fields": ["name", "created_at"], "sort_nulls": "first"})

    assert settings.allowed_fields == frozenset({"name", "created_at"})
    assert settings.default_field == "created_at"
    assert settings.default_order == "desc"
    assert settings.nulls == "first"
    assert settings.secret is None
    assert settings.encrypted is None


def test_build_maps_default_ordering_to_cursor_keys() -> None:
    cursor_filter = resolve_cursor_settings(BASE).build(cursor=None, page_size=10)

    assert cursor_filter.keys == (CursorKey("created_at", "desc"),)
    assert cursor_filter.limit == 10


def test_build_parses_requested_ordering() -> None:
    settings = resolve_cursor_settings({**BASE, "sort_fields": ["name", "created_at"]})

    single = settings.build(cursor=None, page_size=5, order_by="name", sort_order="asc")
    multi = settings.build(cursor=None, page_size=5, order_by=["-created_at", "name"])

    assert single.keys == (CursorKey("name", "asc"),)
    assert multi.keys == (CursorKey("created_at", "desc"), CursorKey("name", "asc"))


def test_build_rejects_fields_outside_the_allowlist() -> None:
    settings = resolve_cursor_settings({**BASE, "sort_fields": ["name"]})

    with pytest.raises(ValueError, match="Invalid sort field 'password_hash'"):
        settings.build(cursor=None, page_size=5, order_by="password_hash")


def test_without_sort_configuration_pages_by_primary_key() -> None:
    settings = resolve_cursor_settings({"pagination_type": "cursor"})

    assert settings.build(cursor=None, page_size=5).keys == ()
    with pytest.raises(ValueError, match="Invalid sort field"):
        settings.build(cursor=None, page_size=5, order_by="name")


def test_build_rejects_invalid_tokens_as_value_errors() -> None:
    settings = resolve_cursor_settings(BASE)

    with pytest.raises(InvalidCursorError):
        settings.build(cursor="garbage!", page_size=5)
    assert issubclass(InvalidCursorError, ValueError)


def test_build_carries_secret_ttl_and_encryption() -> None:
    settings = resolve_cursor_settings(
        {
            **BASE,
            "pagination_cursor_secret": "k",
            "pagination_cursor_ttl": dt.timedelta(minutes=5),
            "pagination_cursor_encrypted": True,
        }
    )

    cursor_filter = settings.build(cursor=None, page_size=5)

    assert settings.secret == b"k"
    assert cursor_filter.encrypted is True
    assert cursor_filter.ttl == dt.timedelta(minutes=5)


@pytest.mark.parametrize(
    ("config", "match"),
    [
        ({"sort_fields": ["team.name"]}, "relationship sort paths"),
        ({"sort_field": "team.name"}, "relationship sort paths"),
        ({"pagination_cursor_secret": ""}, "must not be empty"),
        ({"pagination_cursor_ttl": 0}, "positive finite duration"),
        ({"pagination_cursor_ttl": "60"}, "positive finite duration"),
    ],
)
def test_invalid_cursor_configuration_is_rejected(config: dict[str, Any], match: str) -> None:
    with pytest.raises(ImproperConfigurationError, match=match):
        resolve_cursor_settings({"pagination_type": "cursor", **config}, Player)  # type: ignore[typeddict-item]


@pytest.fixture
def no_environment_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)


@pytest.mark.usefixtures("no_environment_secret")
def test_token_options_prefer_the_filter_configuration_then_application_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = resolve_cursor_defaults(
        [
            SQLAlchemySyncConfig(connection_string="sqlite://"),
            SQLAlchemySyncConfig(
                connection_string="sqlite://",
                pagination_cursor_secret="app-secret",
                pagination_cursor_ttl=60,
                pagination_cursor_encrypted=True,
            ),
        ]
    )
    unset = resolve_cursor_settings(BASE)
    configured = resolve_cursor_settings(
        {
            **BASE,
            "pagination_cursor_secret": "route-secret",
            "pagination_cursor_ttl": 5,
            "pagination_cursor_encrypted": False,
        }
    )

    assert unset.token_options() == (None, None, False)
    assert unset.token_options(defaults) == (b"app-secret", 60, True)
    assert configured.token_options(defaults) == (b"route-secret", 5, False)

    monkeypatch.setenv("SECRET_KEY", "fallback-secret")
    assert unset.token_options() == (b"fallback-secret", None, False)
    monkeypatch.setenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET", "environment-secret")
    assert unset.token_options() == (b"environment-secret", None, False)
    assert unset.token_options(defaults)[0] == b"app-secret"


@pytest.mark.usefixtures("no_environment_secret")
@pytest.mark.parametrize("config", [{}, {"pagination_cursor_encrypted": True}])
def test_token_options_without_a_secret_are_rejected_when_one_is_needed(config: dict[str, Any]) -> None:
    settings = resolve_cursor_settings({**BASE, **config})  # type: ignore[typeddict-item]

    with pytest.raises(ImproperConfigurationError, match="ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET"):
        settings.token_options(require_secret=not config)


@pytest.mark.parametrize(
    ("options", "match"),
    [
        ([{"pagination_cursor_secret": ""}], "must not be empty"),
        ([{"pagination_cursor_ttl": 0}], "positive finite duration"),
        (
            [{"pagination_cursor_secret": "one"}, {"pagination_cursor_secret": "two"}],
            "different pagination_cursor_secret",
        ),
        ([{"pagination_cursor_ttl": 60}, {"pagination_cursor_ttl": 30}], "different pagination_cursor_ttl"),
    ],
)
def test_invalid_application_defaults_are_rejected(options: list[dict[str, Any]], match: str) -> None:
    configs = [SQLAlchemySyncConfig(connection_string="sqlite://", **option) for option in options]

    with pytest.raises(ImproperConfigurationError, match=match):
        resolve_cursor_defaults(configs)


def test_configurations_that_agree_share_application_defaults() -> None:
    configs = [
        SQLAlchemySyncConfig(
            connection_string="sqlite://", pagination_cursor_secret="shared", pagination_cursor_ttl=60
        ),
        SQLAlchemySyncConfig(
            connection_string="sqlite://",
            pagination_cursor_secret=b"shared",
            pagination_cursor_ttl=dt.timedelta(minutes=1),
        ),
    ]

    defaults = resolve_cursor_defaults(configs)

    assert (defaults.secret, defaults.encrypted) == (b"shared", None)


def test_filterset_cursor_options_are_validated_with_its_parameters() -> None:
    class Misconfigured(FilterSet[Player]):
        config = {"pagination_type": "cursor", "pagination_cursor_ttl": 0}

    with pytest.raises(ImproperConfigurationError, match="positive finite duration"):
        Misconfigured.parameter_specs()


@pytest.mark.parametrize(
    ("generator", "prefix", "expected"),
    [
        (None, None, {"cursor": "cursor", "page_size": "pageSize"}),
        ("snake_case", None, {"cursor": "cursor", "page_size": "page_size"}),
        ("camel_case", "players", {"cursor": "playersCursor", "page_size": "playersPageSize"}),
        (lambda name: f"q_{name}", None, {"cursor": "q_cursor", "page_size": "q_page_size"}),
    ],
)
def test_cursor_query_names_follow_alias_settings(
    generator: Any, prefix: Optional[str], expected: dict[str, str]
) -> None:
    config: FilterConfig = {"pagination_type": "cursor"}
    if generator is not None:
        config["alias_generator"] = generator

    aliases = resolve_filter_aliases(config, prefix=prefix)

    assert {name: aliases[name] for name in expected} == expected
    assert "current_page" not in aliases


def test_limit_offset_query_names_are_unchanged() -> None:
    aliases = resolve_filter_aliases({"pagination_type": "limit_offset"})

    assert aliases == {"current_page": "currentPage", "page_size": "pageSize"}


def test_filterset_cursor_mode_builds_a_single_cursor_filter() -> None:
    filters = Players(goals__ge=1, orderBy=["-goals", "name"]).to_statement_filters()

    cursor_filters = [f for f in filters if isinstance(f, CursorFilter)]
    assert len(cursor_filters) == 1
    assert not any(isinstance(f, (OrderByFilter, LimitOffsetFilter)) for f in filters)
    assert cursor_filters[0].keys == (CursorKey("goals", "desc", "last"), CursorKey("name", "asc", "last"))
    assert cursor_filters[0].limit == 3


def test_filterset_walk_through_repository(session: Session) -> None:
    repo = PlayerRepository(session=session)
    seen: list[int] = []
    cursor: Optional[str] = None
    while True:
        query = Players(goals__ge=1, orderBy="joined", pageSize=4, cursor=cursor)
        rows = repo.get_many(query)
        page = next(f for f in query.to_statement_filters() if isinstance(f, CursorFilter)).build_page(
            rows, model=Player
        )
        seen.extend(p.id for p in page.items)
        if not page.has_next:
            break
        cursor = page.next_cursor

    players = [p for p in repo.get_many() if p.goals >= 1]
    expected = sorted(players, key=lambda p: (p.joined is None, p.joined or dt.date.min, p.id))
    assert seen == [p.id for p in expected]


def test_filterset_signed_tokens_round_trip(session: Session) -> None:
    repo = PlayerRepository(session=session)
    first = SignedPlayers()
    page = next(f for f in first.to_statement_filters() if isinstance(f, CursorFilter)).build_page(
        repo.get_many(first), model=Player
    )

    assert page.next_cursor is not None and "." in page.next_cursor
    assert repo.get_many(SignedPlayers(cursor=page.next_cursor))
    with pytest.raises(InvalidCursorError):
        SignedPlayers(cursor=page.next_cursor.split(".")[0])


@pytest.mark.parametrize(
    ("values", "match"),
    [
        ({"pageSize": 6}, "exceeds maximum allowed size 5"),
        ({"pageSize": 0}, "positive integers"),
        ({"orderBy": "team__name"}, "Invalid sort field"),
        ({"cursor": "not-a-token!"}, "malformed"),
    ],
)
def test_filterset_cursor_mode_validates_request_values(values: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Players(**values)
