from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ClauseElement, ColumnElement, UpdateBase
from sqlalchemy.ext.compiler import compiles

if TYPE_CHECKING:
    from typing import Literal

    from sqlalchemy.sql.compiler import StrSQLCompiler


class MergeClause(ClauseElement):
    __visit_name__ = "merge_clause"

    def __init__(self, command: Literal["INSERT", "UPDATE", "DELETE"]) -> None:
        self.on_sets: dict[str, ColumnElement[Any]] = {}
        self.predicate: ColumnElement[bool] | None = None
        self.command = command

    def values(self, **kwargs: ColumnElement[Any]) -> MergeClause:
        self.on_sets = kwargs
        return self

    def where(self, expr: ColumnElement[bool]) -> MergeClause:
        self.predicate = expr
        return self


@compiles(MergeClause)  # type: ignore[no-untyped-call, misc]
def visit_merge_clause(element: MergeClause, compiler: StrSQLCompiler, **kw: Any) -> str:
    case_predicate = ""
    if element.predicate is not None:
        case_predicate = f" AND {element.predicate._compiler_dispatch(compiler, **kw)!s}"  # noqa: SLF001

    if element.command == "INSERT":
        sets, sets_tos = list(element.on_sets), list(element.on_sets.values())
        if kw.get("deterministic", False):
            sorted_on_sets = dict(sorted(element.on_sets.items(), key=lambda x: x[0]))
            sets, sets_tos = list(sorted_on_sets), list(sorted_on_sets.values())

        merge_insert = ", ".join(sets)
        values = ", ".join(e._compiler_dispatch(compiler, **kw) for e in sets_tos)  # noqa: SLF001
        return f"WHEN NOT MATCHED{case_predicate} THEN {element.command} ({merge_insert}) VALUES ({values})"

    set_list = list(element.on_sets.items())
    if kw.get("deterministic", False):
        set_list.sort(key=lambda x: x[0])

    # merge update or merge delete
    merge_action = ""
    values = ""

    if element.on_sets:
        values = ", ".join(
            f"{name} = {column._compiler_dispatch(compiler, **kw)}" for name, column in set_list  # noqa: SLF001
        )
        merge_action = f" SET {values}"

    return f"WHEN MATCHED{case_predicate} THEN {element.command}{merge_action}"


class Merge(UpdateBase):
    __visit_name__ = "merge"
    _bind = None
    inherit_cache = True

    def __init__(self, into: Any, using: Any, on: Any) -> None:
        self.into = into
        self.using = using
        self.on = on
        self.clauses: list[ClauseElement] = []

    def when_matched(self, operations: set[Literal["UPDATE", "DELETE", "INSERT"]]) -> MergeClause:
        for op in operations:
            self.clauses.append(clause := MergeClause(op))
        return clause


@compiles(Merge)  # type: ignore[no-untyped-call, misc]
def visit_merge(element: Merge, compiler: StrSQLCompiler, **kw: Any) -> str:
    clauses = " ".join(clause._compiler_dispatch(compiler, **kw) for clause in element.clauses)  # noqa: SLF001
    sql_text = f"MERGE INTO {element.into} USING {element.using} ON {element.on}"

    if clauses:
        sql_text += f" {clauses}"

    return sql_text
