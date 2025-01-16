from __future__ import annotations

import asyncio
import contextlib
import os
import re
import subprocess
import sys
import timeit
from collections.abc import Awaitable, Generator
from pathlib import Path
from types import TracebackType
from typing import Any, AsyncGenerator, Callable, Iterable, Union

import asyncmy
import asyncpg
import oracledb
import psycopg
import pyodbc
import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import spanner
from oracledb.exceptions import DatabaseError, OperationalError
from pytest_databases.helpers import simple_string_hash

from tests.helpers import maybe_async


async def wait_until_responsive(
    check: Callable[..., Union[bool, Awaitable[bool]]],  # noqa: UP007
    timeout: float,
    pause: float,
    **kwargs: Any,
) -> int:
    """Wait until a service is responsive.

    Args:
        check: Coroutine, return truthy value when waiting should stop.
        timeout: Maximum seconds to wait.
        pause: Seconds to wait between calls to `check`.
        **kwargs: Given as kwargs to `check`.
    """
    ref = timeit.default_timer()
    now = ref
    while (now - ref) < timeout:  # sourcery skip
        if await maybe_async(check(**kwargs)):
            return 1
        await asyncio.sleep(pause)
        now = timeit.default_timer()

    msg = "Timeout reached while waiting on service!"
    raise RuntimeError(msg)


TRUE_VALUES = {"True", "true", "1", "yes", "Y", "T"}
SKIP_DOCKER_COMPOSE: bool = os.environ.get("SKIP_DOCKER_COMPOSE", "False") in TRUE_VALUES
USE_LEGACY_DOCKER_COMPOSE: bool = os.environ.get("USE_LEGACY_DOCKER_COMPOSE", "False") in TRUE_VALUES
COMPOSE_PROJECT_NAME: str = f"advanced-alchemy-{simple_string_hash(__file__)}"


class DockerServiceRegistry(contextlib.AbstractContextManager):
    def __init__(
        self,
        worker_id: str,
        compose_project_name: str = COMPOSE_PROJECT_NAME,
        before_start: Iterable[Callable[[], Any]] | None = None,
    ) -> None:
        self._running_services: set[str] = set()
        self.docker_ip = self._get_docker_ip()
        self._base_command = ["docker-compose"] if USE_LEGACY_DOCKER_COMPOSE else ["docker", "compose"]
        self._compose_files: list[str] = []
        self._base_command.extend(
            [
                f"--project-name=advanced_alchemy-{worker_id}",
            ],
        )
        self._before_start = list(before_start) if before_start else []

    def __exit__(
        self,
        /,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> None:
        self.down()

    @staticmethod
    def _get_docker_ip() -> str:
        docker_host = os.environ.get("DOCKER_HOST", "").strip()
        if not docker_host or docker_host.startswith("unix://"):
            return "127.0.0.1"

        if match := re.match(r"^tcp://(.+?):\d+$", docker_host):
            return match[1]

        msg = f'Invalid value for DOCKER_HOST: "{docker_host}".'
        raise ValueError(msg)

    def run_command(self, *args: str) -> None:
        command = [*self._base_command, *self._compose_files, *args]
        subprocess.run(command, check=True, capture_output=True)

    async def start(
        self,
        name: str,
        docker_compose_files: list[Path] = [Path(__file__).parent / "docker-compose.yml"],
        *,
        check: Callable[..., Union[bool, Awaitable[bool]]],  # noqa: UP007
        timeout: float = 30,
        pause: float = 0.1,
        **kwargs: Any,
    ) -> None:
        for before_start in self._before_start:
            before_start()

        if SKIP_DOCKER_COMPOSE:
            self._running_services.add(name)
        if name not in self._running_services:
            self._compose_files = [f"--file={compose_file}" for compose_file in docker_compose_files]
            self.run_command("up", "--force-recreate", "-d", name)
            self._running_services.add(name)

        _ = await wait_until_responsive(
            check=check,
            timeout=timeout,
            pause=pause,
            host=self.docker_ip,
            **kwargs,
        )

    def stop(self, name: str) -> None:
        self.run_command("down", "--volumes", "-t", "10", name)

    def down(self) -> None:
        if not SKIP_DOCKER_COMPOSE:
            self.run_command("down", "-t", "10", "--volumes")


@pytest.fixture(scope="session")
def docker_services(worker_id: str) -> Generator[DockerServiceRegistry, None, None]:
    if os.getenv("GITHUB_ACTIONS") == "true" and sys.platform != "linux":
        pytest.skip("Docker not available on this platform")

    registry = DockerServiceRegistry(worker_id)
    try:
        yield registry
    finally:
        registry.down()


@pytest.fixture(scope="session")
def docker_ip(docker_services: DockerServiceRegistry) -> Generator[str, None, None]:
    yield docker_services.docker_ip


async def mysql_responsive(host: str) -> bool:
    try:
        conn = await asyncmy.connect(
            host=host,
            port=3360,
            user="app",
            database="db",
            password="super-secret",
        )
        async with conn.cursor() as cursor:
            await cursor.execute("select 1 as is_available")
            resp = await cursor.fetchone()
        return resp[0] == 1  # type: ignore
    except asyncmy.errors.OperationalError:  # pyright: ignore[reportAttributeAccessIssue]
        return False


@pytest.fixture()
async def mysql_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("mysql", timeout=45, pause=1, check=mysql_responsive)
    yield


async def postgres_responsive(host: str) -> bool:
    try:
        conn = await asyncpg.connect(
            host=host,
            port=5423,
            user="postgres",
            database="postgres",
            password="super-secret",
        )
    except (ConnectionError, asyncpg.CannotConnectNowError):
        return False

    try:
        return (await conn.fetchrow("SELECT 1"))[0] == 1  # type: ignore
    finally:
        await conn.close()


@pytest.fixture()
async def postgres_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("postgres", check=postgres_responsive)
    yield


async def postgres14_responsive(host: str) -> bool:
    try:
        conn = await asyncpg.connect(
            host=host,
            port=5424,
            user="postgres",
            database="postgres",
            password="super-secret",
        )
    except (ConnectionError, asyncpg.CannotConnectNowError):
        return False

    try:
        return (await conn.fetchrow("SELECT 1"))[0] == 1  # type: ignore
    finally:
        await conn.close()


@pytest.fixture()
async def postgres14_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("postgres", check=postgres_responsive)
    yield


def oracle23c_responsive(host: str) -> bool:
    try:
        conn = oracledb.connect(
            host=host,
            port=1513,
            user="app",
            service_name="FREEPDB1",
            password="super-secret",
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dual")
            resp = cursor.fetchone()
        return resp[0] == 1  # type: ignore
    except (OperationalError, DatabaseError, Exception):
        return False


@pytest.fixture()
async def oracle23c_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("oracle23c", check=oracle23c_responsive, timeout=120)
    yield


def oracle18c_responsive(host: str) -> bool:
    try:
        conn = oracledb.connect(
            host=host,
            port=1512,
            user="app",
            service_name="xepdb1",
            password="super-secret",
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dual")
            resp = cursor.fetchone()
        return resp[0] == 1  # type: ignore
    except (OperationalError, DatabaseError, Exception):
        return False


@pytest.fixture()
async def oracle18c_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("oracle18c", check=oracle18c_responsive, timeout=120)
    yield


def spanner_responsive(host: str) -> bool:
    try:
        os.environ["SPANNER_EMULATOR_HOST"] = "localhost:9010"
        os.environ["GOOGLE_CLOUD_PROJECT"] = "emulator-test-project"
        spanner_client = spanner.Client(project="emulator-test-project", credentials=AnonymousCredentials())  # type: ignore[no-untyped-call]
        instance = spanner_client.instance("test-instance")
        with contextlib.suppress(Exception):
            instance.create()

        database = instance.database("test-database")
        with contextlib.suppress(Exception):
            database.create()

        with database.snapshot() as snapshot:
            resp = next(iter(snapshot.execute_sql("SELECT 1")))
        return resp[0] == 1  # type: ignore
    except Exception:
        return False


@pytest.fixture()
async def spanner_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    os.environ["SPANNER_EMULATOR_HOST"] = "localhost:9010"
    await docker_services.start("spanner", timeout=60, check=spanner_responsive)
    yield


async def mssql_responsive(host: str) -> bool:
    await asyncio.sleep(1)
    try:
        port = 1344
        user = "sa"
        database = "master"
        conn = pyodbc.connect(
            connstring=f"encrypt=no; TrustServerCertificate=yes; driver={{ODBC Driver 18 for SQL Server}}; server={host},{port}; database={database}; UID={user}; PWD=Super-secret1",
            timeout=2,
        )
        with conn.cursor() as cursor:
            cursor.execute("select 1 as is_available")
            resp = cursor.fetchone()
            return resp[0] == 1  # type: ignore
    except Exception:
        return False


@pytest.fixture()
async def mssql_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("mssql", timeout=60, pause=1, check=mssql_responsive)
    yield


async def cockroachdb_responsive(host: str) -> bool:
    try:
        with psycopg.connect("postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable") as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1 as is_available")
                resp = cursor.fetchone()
                return resp[0] == 1  # type: ignore
    except Exception:
        return False


@pytest.fixture()
async def cockroachdb_service(docker_services: DockerServiceRegistry) -> AsyncGenerator[None, None]:
    await docker_services.start("cockroachdb", timeout=60, pause=1, check=cockroachdb_responsive)
    yield
