from pathlib import Path

from rich import get_console
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, Session, sessionmaker

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.utils.fixtures import open_fixture

here = Path(__file__).parent
console = get_console()


class USState(UUIDBase):
    # you can optionally override the generated table name by manually setting it.
    __tablename__ = "us_state_lookup"
    abbreviation: Mapped[str]
    name: Mapped[str]


class USStateRepository(SQLAlchemySyncRepository[USState]):
    """US State repository."""

    model_type = USState


engine = create_engine(
    "duckdb:///:memory:",
    future=True,
)
session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)


def run_script() -> None:
    """Load data from a fixture."""

    # Initializes the database.
    with engine.begin() as conn:
        USState.metadata.create_all(conn)

    with session_factory() as db_session:
        # 1) Load the JSON data into the US States table.
        repo = USStateRepository(session=db_session)
        fixture = open_fixture(here, USStateRepository.model_type.__tablename__)
        objs = repo.add_many([USStateRepository.model_type(**raw_obj) for raw_obj in fixture])
        db_session.commit()
        console.print(f"Created {len(objs)} new objects.")

        # 2) Select paginated data and total row count.
        created_objs, total_objs = repo.list_and_count(LimitOffset(limit=10, offset=0))
        console.print(f"Selected {len(created_objs)} records out of a total of {total_objs}.")

        # 3) Let's remove the batch of records selected.
        deleted_objs = repo.delete_many([new_obj.id for new_obj in created_objs])
        console.print(f"Removed {len(deleted_objs)} records out of a total of {total_objs}.")

        # 4) Let's count the remaining rows
        remaining_count = repo.count()
        console.print(f"Found {remaining_count} remaining records after delete.")


if __name__ == "__main__":
    run_script()
