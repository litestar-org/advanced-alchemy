from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.exc import SQLAlchemyError

from advanced_alchemy.exceptions import IntegrityError, RepositoryError

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute

    from advanced_alchemy.base import ModelProtocol
    from advanced_alchemy.repository.typing import ModelT


@contextmanager
def wrap_sqlalchemy_exception() -> Any:
    """Do something within context to raise a `RepositoryError` chained
    from an original `SQLAlchemyError`.

        >>> try:
        ...     with wrap_sqlalchemy_exception():
        ...         raise SQLAlchemyError("Original Exception")
        ... except RepositoryError as exc:
        ...     print(f"caught repository exception from {type(exc.__context__)}")
        ...
        caught repository exception from <class 'sqlalchemy.exc.SQLAlchemyError'>
    """
    try:
        yield
    except SQLAlchemyIntegrityError as exc:
        raise IntegrityError from exc
    except SQLAlchemyError as exc:
        msg = f"An exception occurred: {exc}"
        raise RepositoryError(msg) from exc
    except AttributeError as exc:
        raise RepositoryError from exc


def get_instrumented_attr(model: type[ModelProtocol], key: str | InstrumentedAttribute) -> InstrumentedAttribute:
    if isinstance(key, str):
        return cast("InstrumentedAttribute", getattr(model, key))
    return key


def model_from_dict(model: ModelT, **kwargs: Any) -> ModelT:
    """Return ORM Object from Dictionary."""
    data = {
        column_name: kwargs[column_name]
        for column_name in model.__mapper__.columns.keys()  # noqa: SIM118
        if column_name in kwargs
    }
    return model(**data)  # type: ignore  # noqa: PGH003
