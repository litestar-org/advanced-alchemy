import contextlib
from collections.abc import Generator

import pytest
from google.cloud import spanner  # pyright: ignore
from pytest import MonkeyPatch
from pytest_databases.docker.cockroachdb import CockroachDBService
from pytest_databases.docker.mssql import MSSQLService
from pytest_databases.docker.mysql import MySQLService
from pytest_databases.docker.oracle import OracleService
from pytest_databases.docker.postgres import PostgresService
from pytest_databases.docker.spanner import SpannerService

pytest_plugins = [
    "pytest_databases.docker",
    "pytest_databases.docker.minio",
    "pytest_databases.docker.mysql",
    "pytest_databases.docker.oracle",
    "pytest_databases.docker.postgres",
    "pytest_databases.docker.spanner",
    "pytest_databases.docker.cockroachdb",
    "pytest_databases.docker.mssql",
    "pytest_databases.docker.bigquery",
]


@pytest.fixture(scope="session")
def monkeypatch_session() -> Generator[MonkeyPatch, None, None]:
    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="session")
def cockroachdb_psycopg_url(cockroachdb_service: CockroachDBService) -> str:
    """Use the running cockroachdb service to return a URL for connecting."""
    # Uses psycopg (sync) driver by default for CockroachDB in SQLAlchemy
    opts = (
        "&".join(f"{k}={v}" for k, v in cockroachdb_service.driver_opts.items())
        if cockroachdb_service.driver_opts
        else ""
    )
    dsn = "cockroachdb+psycopg://{user}@{host}:{port}/{database}?{opts}"
    return dsn.format(
        user="root",
        host=cockroachdb_service.host,
        database="defaultdb",
        port=cockroachdb_service.port,
        opts=opts,
    )


@pytest.fixture(scope="session")
def cockroachdb_asyncpg_url(cockroachdb_service: CockroachDBService) -> str:
    """Use the running cockroachdb service to return a URL for connecting."""
    # Uses asyncpg driver for CockroachDB async
    opts = (
        "&".join(f"{k}={v}" for k, v in cockroachdb_service.driver_opts.items())
        if cockroachdb_service.driver_opts
        else ""
    )
    dsn = "cockroachdb+asyncpg://{user}@{host}:{port}/{database}"
    return dsn.format(
        user="root",
        host=cockroachdb_service.host,
        database="defaultdb",
        port=cockroachdb_service.port,
        opts=opts,
    )


@pytest.fixture(scope="session")
def mssql_pyodbc_url(mssql_service: MSSQLService) -> str:
    """Use the running mssql service to return a URL for connecting using pyodbc."""
    # Uses pyodbc driver (sync)
    host = mssql_service.host
    port = mssql_service.port
    user = mssql_service.user
    password = mssql_service.password
    database = mssql_service.database  # Often 'master' by default if not specified
    # Note: Driver name might need adjustment based on environment
    driver = "ODBC Driver 18 for SQL Server".replace(" ", "+")  # or 17
    return f"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver={driver}&encrypt=no&TrustServerCertificate=yes"


@pytest.fixture(scope="session")
def mssql_aioodbc_url(mssql_service: MSSQLService) -> str:
    """Use the running mssql service to return a URL for connecting using aioodbc."""
    # Uses aioodbc driver (async)
    host = mssql_service.host
    port = mssql_service.port
    user = mssql_service.user
    password = mssql_service.password
    database = mssql_service.database  # Often 'master' by default if not specified
    driver = "ODBC Driver 18 for SQL Server".replace(" ", "+")  # or 17
    # Note: Ensure correct DSN format for aioodbc if different from pyodbc
    return f"mssql+aioodbc://{user}:{password}@{host}:{port}/{database}?driver={driver}&encrypt=no&TrustServerCertificate=yes"


@pytest.fixture(scope="session")
def mysql_asyncmy_url(mysql_service: MySQLService) -> str:
    """Use the running mysql service to return a URL for connecting using asyncmy."""
    # Uses asyncmy driver (async)
    dsn = "mysql+asyncmy://{user}:{password}@{host}:{port}/{database}"
    return dsn.format(
        user=mysql_service.user,
        password=mysql_service.password,
        host=mysql_service.host,
        port=mysql_service.port,
        database=mysql_service.db,
    )


@pytest.fixture(scope="session")
def oracle18c_url(oracle_18c_service: OracleService) -> str:
    """Use the running oracle service to return a URL for connecting using oracledb."""
    # Uses python-oracledb driver (supports sync and async)
    # Determine service name - adjust default 'FREEPDB1' if necessary for your setup

    dsn = "oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service_name}"
    return dsn.format(
        user=oracle_18c_service.user,
        password=oracle_18c_service.password,
        host=oracle_18c_service.host,
        port=oracle_18c_service.port,
        service_name=oracle_18c_service.service_name,
    )


@pytest.fixture(scope="session")
def oracle23ai_url(oracle_23ai_service: OracleService) -> str:
    """Use the running oracle service to return a URL for connecting using oracledb."""
    # Uses python-oracledb driver (supports sync and async)
    # Determine service name - adjust default 'FREEPDB1' if necessary for your setup

    dsn = "oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service_name}"
    return dsn.format(
        user=oracle_23ai_service.user,
        password=oracle_23ai_service.password,
        host=oracle_23ai_service.host,
        port=oracle_23ai_service.port,
        service_name=oracle_23ai_service.service_name,
    )


@pytest.fixture(scope="session")
def postgres14_asyncpg_url(postgres14_service: PostgresService) -> str:
    """Use the running postgres service to return a URL for connecting using asyncpg."""
    # Uses asyncpg driver (async)
    dsn = "postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
    return dsn.format(
        user=postgres14_service.user,
        password=postgres14_service.password,
        host=postgres14_service.host,
        port=postgres14_service.port,
        database=postgres14_service.database,
    )


@pytest.fixture(scope="session")
def postgres_asyncpg_url(postgres_service: PostgresService) -> str:
    """Use the running postgres service to return a URL for connecting using asyncpg."""
    # Uses asyncpg driver (async)
    dsn = "postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
    return dsn.format(
        user=postgres_service.user,
        password=postgres_service.password,
        host=postgres_service.host,
        port=postgres_service.port,
        database=postgres_service.database,
    )


@pytest.fixture(scope="session")
def postgres14_psycopg_url(postgres14_service: PostgresService) -> str:
    """Use the running postgres service to return a URL for connecting using psycopg."""
    # Uses psycopg driver (sync)
    dsn = "postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
    return dsn.format(
        user=postgres14_service.user,
        password=postgres14_service.password,
        host=postgres14_service.host,
        port=postgres14_service.port,
        database=postgres14_service.database,
    )


@pytest.fixture(scope="session")
def postgres_psycopg_url(postgres_service: PostgresService) -> str:
    """Use the running postgres service to return a URL for connecting using psycopg."""
    # Uses psycopg driver (sync)
    dsn = "postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
    return dsn.format(
        user=postgres_service.user,
        password=postgres_service.password,
        host=postgres_service.host,
        port=postgres_service.port,
        database=postgres_service.database,
    )


@pytest.fixture(scope="session")
def spanner_url(
    spanner_service: SpannerService, monkeypatch_session: MonkeyPatch, spanner_connection: spanner.Client
) -> str:
    """Use the running spanner service to return a URL for connecting using spanner."""
    monkeypatch_session.setenv("SPANNER_EMULATOR_HOST", f"{spanner_service.host}:{spanner_service.port}")
    monkeypatch_session.setenv("GOOGLE_CLOUD_PROJECT", spanner_service.project)
    instance = spanner_connection.instance(spanner_service.instance_name)  # pyright: ignore
    with contextlib.suppress(Exception):
        instance.create()

    database = instance.database(spanner_service.database_name)  # pyright: ignore
    with contextlib.suppress(Exception):
        database.create()

    with database.snapshot() as snapshot:  # pyright: ignore
        resp = next(iter(snapshot.execute_sql("SELECT 1")))  # pyright: ignore
    assert resp[0] == 1
    dsn = f"spanner+spanner:///projects/{spanner_service.project}/instances/{spanner_service.instance_name}/databases/{spanner_service.database_name}"
    return dsn.format(
        project=spanner_service.project, instance=spanner_service.instance_name, database=spanner_service.database_name
    )
