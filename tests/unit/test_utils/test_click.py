import builtins
import importlib
import sys
import types

import click as base_click
import pytest


def _reload_utils_click(monkeypatch: "pytest.MonkeyPatch", variant: str) -> types.ModuleType:
    """Reload the compatibility module with a given rich-click variant.

    variant:
        - "none": simulate no rich-click installed
        - "old": rich-click without aliases support
        - "new": rich-click with aliases support
    """

    monkeypatch.syspath_prepend("")  # ensure reload works with patched imports

    for mod in ("advanced_alchemy.utils.cli_tools", "rich_click"):
        sys.modules.pop(mod, None)

    if variant == "none":
        real_import = builtins.__import__

        def blocking_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "rich_click":
                raise ImportError("rich_click not available")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", blocking_import)

    else:
        # Build a lightweight fake rich_click module that exposes all base click attributes
        class _RichGroupBase(base_click.Group):
            pass

        if variant == "new":

            def _rich_group_init(self, *args, aliases=None, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.aliases = tuple(aliases or ())
                _RichGroupBase.__init__(self, *args, **kwargs)

        else:

            def _rich_group_init(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                _RichGroupBase.__init__(self, *args, **kwargs)

        FakeRichGroup = type("FakeRichGroup", (_RichGroupBase,), {"__init__": _rich_group_init})

        # Create a module-like object that also inherits base_click's attributes
        class FakeRichClickModule(types.ModuleType):
            """Fake rich_click module for testing."""

            RichGroup = FakeRichGroup

            def __getattr__(self, name: str) -> object:
                # Delegate to base click for any attribute not defined here
                return getattr(base_click, name)

        fake_rich_click = FakeRichClickModule("rich_click")

        monkeypatch.setitem(sys.modules, "rich_click", fake_rich_click)

    return importlib.import_module("advanced_alchemy.utils.cli_tools")


def _build_alias_group(mod: types.ModuleType, aliases: "tuple[str, ...]" = ("db",)) -> base_click.Group:
    @mod.group(name="database", aliases=aliases)
    def database_group() -> None: ...

    @mod.command(name="status", aliases=("st",))
    def status_cmd() -> None: ...

    database_group.add_command(status_cmd)
    return database_group  # type: ignore[return-value,no-any-return]


def test_plain_click_alias_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_utils_click(monkeypatch, "none")

    group = _build_alias_group(mod)

    ctx = base_click.Context(group)
    cmd = group.get_command(ctx, "st")

    assert isinstance(group, mod.AliasedGroup)
    assert cmd is group.get_command(ctx, "status")


def test_plain_click_resolve_command_returns_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_utils_click(monkeypatch, "none")
    group = _build_alias_group(mod)
    ctx = base_click.Context(group)

    cmd_name, cmd, remaining = group.resolve_command(ctx, ["st"])  # type: ignore[arg-type]
    assert cmd_name == "status"
    assert cmd is not None
    assert remaining == []


def test_old_rich_click_uses_aliased_group(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_utils_click(monkeypatch, "old")
    group = _build_alias_group(mod)
    assert not mod._RICH_CLICK_ALIASES_SUPPORTED
    assert isinstance(group, mod.AliasedGroup)


def test_new_rich_click_prefers_rich_group(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_utils_click(monkeypatch, "new")

    @mod.group(name="database", aliases=("db",))
    def grp() -> None: ...

    assert mod._RICH_CLICK_AVAILABLE
    assert mod._RICH_CLICK_ALIASES_SUPPORTED
    assert grp.__class__.__name__.startswith("FakeRichGroup")


def test_command_wrapper_stores_aliases_on_plain_click(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_utils_click(monkeypatch, "none")

    @mod.command(name="ping", aliases=("p",))
    def ping() -> None: ...

    assert getattr(ping, "aliases", ()) == ("p",)


def test_parent_group_resolves_child_aliases_plain_click(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parent group (like Litestar CLI) should resolve aliases of child groups.

    This tests the scenario where a child group with aliases is added to a parent
    group that was created with plain click (not our wrapper). The global patch
    should make the parent group alias-aware.
    """
    mod = _reload_utils_click(monkeypatch, "none")

    # Create a parent group using base click (simulating Litestar's main CLI)
    @base_click.group(name="main")
    def parent_group() -> None:
        pass

    # Create child group with aliases (simulating database_group)
    @mod.group(name="database", aliases=("db",))
    def child_group() -> None:
        pass

    # Add child to parent (this is what Litestar does)
    parent_group.add_command(child_group)

    # Parent should resolve "db" to "database"
    ctx = base_click.Context(parent_group)
    resolved = parent_group.get_command(ctx, "db")

    assert resolved is not None
    assert resolved.name == "database"


def test_parent_group_resolves_child_aliases_old_rich_click(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parent group resolves aliases with old rich-click (< 1.9.0)."""
    mod = _reload_utils_click(monkeypatch, "old")

    # Create a parent group using base click
    @base_click.group(name="main")
    def parent_group() -> None:
        pass

    # Create child group with aliases
    @mod.group(name="database", aliases=("db",))
    def child_group() -> None:
        pass

    parent_group.add_command(child_group)

    ctx = base_click.Context(parent_group)
    resolved = parent_group.get_command(ctx, "db")

    assert resolved is not None
    assert resolved.name == "database"
