from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import time
import timeit
from collections.abc import Generator
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Iterable

import oracledb
import psycopg
import pymysql
import pyodbc
import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import spanner
from pytest_databases.helpers import simple_string_hash

from advanced_alchemy.utils.portals import PortalProvider


def wait_until_responsive(
    check: Callable[..., bool],
    timeout: float,
    pause: float,
    **kwargs: Any,
) -> None:
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
        if check(**kwargs):
            return
        time.sleep(pause)
        now = timeit.default_timer()

    msg = "Timeout reached while waiting on service!"
    raise RuntimeError(msg)


TRUE_VALUES = {"True", "true", "1", "yes", "Y", "T"}
SKIP_DOCKER_COMPOSE: bool = os.environ.get("SKIP_DOCKER_COMPOSE", "False") in TRUE_VALUES
USE_LEGACY_DOCKER_COMPOSE: bool = os.environ.get("USE_LEGACY_DOCKER_COMPOSE", "False") in TRUE_VALUES
COMPOSE_PROJECT_NAME: str = f"advanced-alchemy-{simple_string_hash(__file__)}"
async_window = PortalProvider()


class DockerServiceRegistry(AbstractContextManager["DockerServiceRegistry"]):
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

    @property
    def running_services(self) -> set[str]:
        return self._running_services

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

    def start(
        self,
        name: str,
        docker_compose_files: list[Path] = [Path(__file__).parent / "docker-compose.yml"],
        *,
        check: Callable[..., bool],
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

        wait_until_responsive(
            check=check,
            timeout=timeout,
            pause=pause,
            host=self.docker_ip,
            **kwargs,
        )

    def stop(self, name: str) -> None:
        pass

    def down(self) -> None:
        if not SKIP_DOCKER_COMPOSE:
            self.run_command("down", "-t", "10", "--volumes")


@pytest.fixture(scope="session")
def docker_services(worker_id: str) -> Generator[DockerServiceRegistry, None, None]:
    if os.getenv("GITHUB_ACTIONS") == "true" and sys.platform != "linux":
        pytest.skip("Docker not available on this platform")

    with DockerServiceRegistry(worker_id) as registry:
        yield registry


@pytest.fixture(scope="session")
def docker_ip(docker_services: DockerServiceRegistry) -> Generator[str, None, None]:
    yield docker_services.docker_ip


def mysql_responsive(host: str) -> bool:
    try:
        with pymysql.connect(
            host=host,
            port=3360,
            user="app",
            database="db",
            password="super-secret",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1 as is_available")
                resp = cursor.fetchone()
                return resp is not None and resp[0] == 1
    except Exception:
        return False


@pytest.fixture()
def mysql_service(docker_services: DockerServiceRegistry) -> None:
    docker_services.start("mysql", timeout=45, pause=1, check=mysql_responsive)


def _make_pg_connection_string(host: str, port: int, user: str, password: str, database: str) -> str:
    return f"dbname={database} user={user} host={host} port={port} password={password}"


def postgres_responsive(host: str) -> bool:
    try:
        with psycopg.connect(
            connstring=_make_pg_connection_string(host, 5423, "postgres", "super-secret", "postgres"),
        ) as conn:
            db_open = conn.execute("SELECT 1").fetchone()
            return bool(db_open is not None and db_open[0] == 1)
    except Exception:
        return False


@pytest.fixture()
def postgres_service(docker_services: DockerServiceRegistry) -> None:
    docker_services.start("postgres", check=postgres_responsive)


def postgres14_responsive(host: str) -> bool:
    try:
        with psycopg.connect(
            connstring=_make_pg_connection_string(host, 5424, "postgres", "super-secret", "postgres"),
        ) as conn:
            db_open = conn.execute("SELECT 1").fetchone()
            return bool(db_open is not None and db_open[0] == 1)
    except Exception:
        return False


@pytest.fixture()
def postgres14_service(docker_services: DockerServiceRegistry) -> None:
    docker_services.start("postgres", check=postgres_responsive)


def oracle23c_responsive(host: str) -> bool:
    try:
        with oracledb.connect(
            host=host,
            port=1513,
            user="app",
            service_name="FREEPDB1",
            password="super-secret",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dual")
                resp = cursor.fetchone()
                return resp is not None and resp[0] == 1
    except Exception:
        return False


@pytest.fixture()
def oracle23c_service(docker_services: DockerServiceRegistry, worker_id: str = "main") -> None:
    docker_services.start("oracle23c", check=oracle23c_responsive, timeout=120)


def oracle18c_responsive(host: str) -> bool:
    try:
        with oracledb.connect(
            host=host,
            port=1512,
            user="app",
            service_name="xepdb1",
            password="super-secret",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dual")
                resp = cursor.fetchone()
                return resp is not None and resp[0] == 1
    except Exception:
        return False


@pytest.fixture()
def oracle18c_service(docker_services: DockerServiceRegistry) -> None:
    docker_services.start("oracle18c", check=oracle18c_responsive, timeout=120)


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
def spanner_service(docker_services: DockerServiceRegistry) -> None:
    os.environ["SPANNER_EMULATOR_HOST"] = "localhost:9010"
    docker_services.start("spanner", timeout=60, check=spanner_responsive)


def mssql_responsive(host: str) -> bool:
    try:
        port = 1344
        user = "sa"
        database = "master"
        with pyodbc.connect(
            connstring=f"encrypt=no; TrustServerCertificate=yes; driver={{ODBC Driver 18 for SQL Server}}; server={host},{port}; database={database}; UID={user}; PWD=Super-secret1",
            timeout=2,
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1 as is_available")
                resp = cursor.fetchone()
                return resp is not None and resp[0] == 1
    except Exception:
        return False


@pytest.fixture()
def mssql_service(docker_services: DockerServiceRegistry) -> None:
    docker_services.start("mssql", timeout=60, pause=1, check=mssql_responsive)


def cockroachdb_responsive(host: str) -> bool:
    try:
        with psycopg.connect("postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable") as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1 as is_available")
                resp = cursor.fetchone()
                return resp[0] == 1  # type: ignore
    except Exception:
        return False


@pytest.fixture()
def cockroachdb_service(docker_services: DockerServiceRegistry) -> None:
    docker_services.start("cockroachdb", timeout=60, pause=1, check=cockroachdb_responsive)
