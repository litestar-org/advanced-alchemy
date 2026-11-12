"""Compatibility utilities for Click and Rich-Click.

This module provides a small compatibility layer so CLI code can opt into
alias support without depending on Rich-Click 1.9+ being installed. When
Rich-Click with alias support is available it is used; otherwise a local
``AliasedGroup`` implementation mimics the behaviour for plain Click (or
older Rich-Click versions).

Usage:
    from advanced_alchemy.utils.cli_tools import click, group, command

    @group(name="database", aliases=["db"])
    def database_group():
        ...
"""

import inspect
import re
from collections.abc import Iterable
from typing import Any, Callable, ClassVar, Final, Optional

from typing_extensions import ParamSpec

_rich_click_available = False
_rich_click_aliases_supported = False
_rich_group_cls: "Optional[type[click.Group]]" = None

try:
    import rich_click as click
    from rich_click import RichGroup

    _rich_group_init_params = inspect.signature(RichGroup.__init__).parameters
    _rich_click_available = True
    _rich_click_aliases_supported = "aliases" in _rich_group_init_params
    _rich_group_cls = RichGroup
except ImportError:
    import click  # type: ignore[no-redef]

_RICH_CLICK_AVAILABLE: Final[bool] = _rich_click_available
_RICH_CLICK_ALIASES_SUPPORTED: Final[bool] = _rich_click_aliases_supported

__all__ = [
    "BYTE_SIZE",
    "AliasedGroup",
    "click",
    "command",
    "group",
]

P = ParamSpec("P")
_base_click_group: "type[click.Group]" = click.Group


def _supports_aliases_param(cls: type[Any]) -> bool:
    """Return True when the provided class ``__init__`` accepts ``aliases``."""

    try:
        return "aliases" in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return False


class AliasedGroup(click.Group):
    """Click group that understands command aliases.

    The implementation mirrors Rich-Click's alias handling so that plain
    Click environments can keep working when ``aliases`` are supplied.
    """

    def __init__(
        self,
        *args: Any,
        aliases: Optional[Iterable[str]] = None,
        **kwargs: Any,
    ) -> None:
        aliases_iterable = aliases or ()
        super().__init__(*args, **kwargs)
        self.aliases = tuple(aliases_iterable)
        self._alias_mapping: dict[str, str] = {}

    def add_command(
        self,
        cmd: click.Command,
        name: Optional[str] = None,
        aliases: Optional[Iterable[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().add_command(cmd, name, **kwargs)
        command_name = name or cmd.name
        if command_name is None:
            return

        all_aliases: tuple[str, ...] = tuple(aliases or ()) + tuple(getattr(cmd, "aliases", ()) or ())
        for alias in all_aliases:
            self._alias_mapping[alias] = command_name
        self._alias_mapping.pop(command_name, None)

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        resolved_name = self._alias_mapping.get(cmd_name, cmd_name)
        return super().get_command(ctx, resolved_name)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[Optional[str], Optional[click.Command], list[str]]:
        cmd_name, cmd, remaining_args = super().resolve_command(ctx, args)
        if cmd is None:
            return cmd_name, cmd, remaining_args
        canonical_name = cmd.name or cmd_name
        return canonical_name, cmd, remaining_args


class _ByteSizeParamType(click.ParamType):
    """Click parameter type for byte sizes such as ``1048576``, ``512K``, ``50M``, or ``2GiB``.

    The number is a whole number of bytes, optionally followed by ``K``, ``M``, or ``G``
    (1024-based) and an optional ``B`` or ``iB``, or by a bare ``B``. Matching is
    case-insensitive and surrounding whitespace is ignored.
    """

    __slots__ = ()

    name = "size"
    _pattern: "ClassVar[re.Pattern[str]]" = re.compile(
        r"(?P<number>[0-9]+)(?:(?P<unit>[kmg])(?:i?b)?|b)?",
        re.IGNORECASE,
    )
    _multipliers: "ClassVar[dict[str, int]]" = {"k": 1024, "m": 1024**2, "g": 1024**3}

    def convert(self, value: Any, param: "Optional[click.Parameter]", ctx: "Optional[click.Context]") -> int:
        """Return the size in bytes.

        Args:
            value: Raw CLI option value.
            param: Click parameter associated with the option, if any.
            ctx: Active Click context, if any.

        Returns:
            Parsed positive integer byte count.

        Raises:
            click.BadParameter: If ``value`` does not match the size grammar or is below 1 byte.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            size = value
        else:
            match = self._pattern.fullmatch(str(value).strip())
            if match is None:
                msg = (
                    f"{value!r} is not a valid size; use a whole number of bytes with an optional "
                    "K, M, or G suffix, for example 1048576, 512K, 50M, or 2GiB."
                )
                self.fail(msg, param, ctx)
            unit = match.group("unit")
            multiplier = self._multipliers[unit.lower()] if unit else 1
            size = int(match.group("number")) * multiplier

        if size < 1:
            msg = f"{value!r} is not a valid size; the size must be at least 1 byte."
            self.fail(msg, param, ctx)
        return size


BYTE_SIZE: "Final[_ByteSizeParamType]" = _ByteSizeParamType()


def _patch_group_class_for_aliases(group_cls: type[click.Group]) -> None:
    """Patch a click.Group subclass to support aliases if not already supported.

    This ensures parent groups (which we don't control) can resolve
    aliases of child groups that were created with aliases.

    Args:
        group_cls: The group class to patch (e.g., click.Group, RichGroup).
    """
    if _supports_aliases_param(group_cls):
        return

    if getattr(group_cls, "_aa_alias_patched", False):
        return

    _original_add_command = group_cls.add_command
    _original_get_command = group_cls.get_command

    def _patched_add_command(
        self: click.Group,
        cmd: click.Command,
        name: Optional[str] = None,
        aliases: Optional[Iterable[str]] = None,
        **kwargs: Any,
    ) -> None:
        _original_add_command(self, cmd, name, **kwargs)
        if not hasattr(self, "_alias_mapping"):
            self._alias_mapping = {}  # type: ignore[attr-defined]
        command_name = name or cmd.name
        if command_name:
            all_aliases = tuple(aliases or ()) + tuple(getattr(cmd, "aliases", ()) or ())
            for alias in all_aliases:
                self._alias_mapping[alias] = command_name  # type: ignore[attr-defined]
            self._alias_mapping.pop(command_name, None)  # type: ignore[attr-defined]

    def _patched_get_command(
        self: click.Group,
        ctx: click.Context,
        cmd_name: str,
    ) -> Optional[click.Command]:
        alias_mapping: dict[str, str] = getattr(self, "_alias_mapping", {})
        resolved_name: str = alias_mapping.get(cmd_name, cmd_name)
        return _original_get_command(self, ctx, resolved_name)

    group_cls.add_command = _patched_add_command  # type: ignore[method-assign]
    group_cls.get_command = _patched_get_command  # type: ignore[method-assign]
    group_cls._aa_alias_patched = True  # type: ignore[attr-defined]  # noqa: SLF001


def _patch_click_group_for_aliases() -> None:
    """Patch click.Group (and RichGroup if present) to support aliases.

    This function patches the base click.Group class so that ANY group
    (including parent groups we don't control like Litestar's main CLI)
    can properly resolve aliases of child commands/groups.
    """
    _patch_group_class_for_aliases(_base_click_group)

    if _RICH_CLICK_AVAILABLE and not _RICH_CLICK_ALIASES_SUPPORTED and _rich_group_cls is not None:
        _patch_group_class_for_aliases(_rich_group_cls)


_patch_click_group_for_aliases()


def _alias_enabled_group_class(cls: Optional[type[click.Group]], aliases: Optional[Iterable[str]]) -> type[click.Group]:
    """Choose a group class that can accept ``aliases`` safely."""

    base_cls: type[click.Group]
    if cls is not None:
        base_cls = cls
    elif _RICH_CLICK_ALIASES_SUPPORTED and _rich_group_cls is not None:
        base_cls = _rich_group_cls
    else:
        base_cls = AliasedGroup

    if aliases is None or _supports_aliases_param(base_cls):
        return base_cls

    class AliasedCustomGroup(AliasedGroup, base_cls):  # type: ignore[valid-type,misc]
        """Hybrid group that adds alias handling to a custom group class."""

    AliasedCustomGroup.__name__ = f"Aliased{base_cls.__name__}"
    return AliasedCustomGroup


def group(
    name: Optional[str] = None,
    cls: Optional[type[click.Group]] = None,
    **attrs: Any,
) -> Callable[[Callable[P, Any]], click.Group]:
    """Wrapper around ``click.group`` with alias support."""

    aliases = attrs.get("aliases")
    group_cls = _alias_enabled_group_class(cls, aliases)
    return click.group(name=name, cls=group_cls, **attrs)


def command(
    name: Optional[str] = None,
    cls: Optional[type[click.Command]] = None,
    **attrs: Any,
) -> Callable[[Callable[P, Any]], click.Command]:
    """Wrapper around ``click.command`` that preserves aliases on plain Click."""

    target_cls = cls or click.Command
    aliases = attrs.pop("aliases", None)

    if aliases and not _supports_aliases_param(target_cls):

        def decorator(func: Callable[P, Any]) -> click.Command:
            cmd = click.command(name=name, cls=target_cls, **attrs)(func)
            cmd.aliases = tuple(aliases)  # type: ignore[attr-defined]
            return cmd

        return decorator

    return click.command(name=name, cls=target_cls, **attrs)
