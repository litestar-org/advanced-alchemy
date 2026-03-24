import asyncio
import contextlib
import datetime
import os
import pathlib
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from typing import Optional

import click
import httpx
import msgspec

_polar = "[Polar.sh](https://polar.sh/litestar-org)"
_open_collective = "[OpenCollective](https://opencollective.com/litestar)"
_github_sponsors = "[GitHub Sponsors](https://github.com/sponsors/litestar-org/)"
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
_DEFAULT_HTTP_TIMEOUT = httpx.Timeout(timeout=10.0, connect=10.0, read=30.0)
_MAX_HTTP_RETRIES = 3


class PullRequest(msgspec.Struct, kw_only=True):
    title: str
    number: int
    body: str
    created_at: str
    user: "RepoUser"
    merge_commit_sha: Optional[str] = None


class Comp(msgspec.Struct):
    sha: str

    class _Commit(msgspec.Struct):
        message: str
        url: str

    commit: _Commit


class RepoUser(msgspec.Struct):
    login: str
    id: int
    type: str


@dataclass
class PRInfo:
    url: str
    title: str
    clean_title: str
    cc_type: str
    number: int
    closes: list[int]
    created_at: datetime.datetime
    description: str
    user: RepoUser


@dataclass
class ReleaseInfo:
    base: str
    release_tag: str
    version: str
    pull_requests: dict[str, list[PRInfo]]
    first_time_prs: list[PRInfo]

    @property
    def compare_url(self) -> str:
        return f"https://github.com/litestar-org/advanced-alchemy/compare/{self.base}...{self.release_tag}"


def _pr_number_from_commit_message(message: str) -> Optional[int]:
    # this is an ugly hack, but it appears to actually be the most reliably way to
    # extract the most "reliable" way to extract the info we want from GH ¯\_(ツ)_/¯
    message_head = message.split("\n\n", maxsplit=1)[0]
    match = re.search(r"\(#(\d+)\)$", message_head) or re.search(r"Merge pull request #(\d+)", message_head)
    if not match:
        print(f"Could not find PR number in {message_head}")  # noqa: T201
    return int(match[1]) if match else None


class _Thing:
    def __init__(self, *, gh_token: str, base: str, release_branch: str, tag: str, version: str) -> None:
        self._gh_token = gh_token
        self._base = base
        self._new_release_tag = tag
        self._release_branch = release_branch
        self._new_release_version = version
        self._base_client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {gh_token}",
            },
            timeout=_DEFAULT_HTTP_TIMEOUT,
        )
        self._api_client = httpx.AsyncClient(
            headers={
                **self._base_client.headers,
                "X-GitHub-Api-Version": "2022-11-28",
                "Accept": "application/vnd.github+json",
            },
            base_url="https://api.github.com/repos/litestar-org/advanced-alchemy/",
            timeout=_DEFAULT_HTTP_TIMEOUT,
        )

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        last_error: Optional[BaseException] = None
        for attempt in range(_MAX_HTTP_RETRIES):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt == _MAX_HTTP_RETRIES - 1:
                    return response
                last_error = httpx.HTTPStatusError(
                    f"Retryable response status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                last_error = exc
            delay = 0.5 * (2**attempt)
            click.secho(
                f"GitHub API {method} {url} failed ({type(last_error).__name__}), retrying in {delay:.1f}s",
                fg="yellow",
            )
            await asyncio.sleep(delay)
        if last_error:
            raise last_error
        msg = f"Request {method} {url} failed without returning a response"
        raise RuntimeError(msg)

    @staticmethod
    def _get_pr_numbers_from_git_range(base: str, release_branch: str) -> list[int]:
        git_executable = shutil.which("git")
        if not git_executable:
            msg = "git executable not found"
            raise FileNotFoundError(msg)
        proc = subprocess.run(  # noqa: S603
            [git_executable, "log", "--format=%s%x00", f"{base}..{release_branch}"],
            check=True,
            capture_output=True,
            text=True,
        )
        messages = [message for message in proc.stdout.split("\x00") if message.strip()]
        pr_numbers = [number for number in (_pr_number_from_commit_message(message) for message in messages) if number]
        return list(dict.fromkeys(pr_numbers))

    async def get_closing_issues_references(self, pr_number: int) -> list[int]:
        graphql_query = """{
        repository(owner: "litestar-org", name: "advanced-alchemy") {
            pullRequest(number: %d) {
                id
                closingIssuesReferences (first: 10) {
                    edges {
                        node {
                            number
                        }
                    }
                }
            }
        }
    }"""
        query = graphql_query % (pr_number,)
        res = await self._request_with_retries(
            self._base_client,
            "POST",
            "https://api.github.com/graphql",
            json={"query": query},
        )
        if res.is_client_error:
            return []
        data = res.json()
        return [
            edge["node"]["number"]
            for edge in data["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["edges"]
        ]

    async def _get_pr_info_for_pr(self, number: int) -> Optional[PRInfo]:
        res = await self._request_with_retries(self._api_client, "GET", f"/pulls/{number}")
        if res.is_client_error:
            click.secho(
                f"Could not get PR info for {number}.  Fetch request returned a status of {res.status_code}",
                fg="yellow",
            )
            return None
        res.raise_for_status()
        data = res.json()
        if not data["body"]:
            data["body"] = ""
        if not data:
            return None
        pr = msgspec.convert(data, type=PullRequest)

        if ":" in pr.title:
            cc_prefix, clean_title = pr.title.split(":", maxsplit=1)
            cc_type = cc_prefix.split("(", maxsplit=1)[0].lower()
            clean_title = clean_title.strip()
        else:
            cc_type = "misc"
            clean_title = pr.title.strip()
        closes_issues = await self.get_closing_issues_references(pr_number=pr.number)

        return PRInfo(
            number=pr.number,
            cc_type=cc_type,
            clean_title=clean_title,
            url=f"https://github.com/litestar-org/advanced-alchemy/pull/{pr.number}",
            closes=closes_issues,
            title=pr.title,
            created_at=datetime.datetime.strptime(pr.created_at, "%Y-%m-%dT%H:%M:%S%z"),
            description=pr.body,
            user=pr.user,
        )

    async def get_prs(self) -> dict[str, list[PRInfo]]:
        pr_numbers = self._get_pr_numbers_from_git_range(self._base, self._release_branch)
        pulls = await asyncio.gather(*map(self._get_pr_info_for_pr, pr_numbers))

        prs: dict[str, list[PRInfo]] = defaultdict(list)
        for pr in pulls:
            if not pr:
                continue
            if pr.user.type != "Bot":
                prs[pr.cc_type].append(pr)
        return prs

    async def _get_first_time_contributions(self, prs: dict[str, list[PRInfo]]) -> list[PRInfo]:
        # there's probably a way to peel this information out of the GraphQL API but
        # this was easier to implement, and it works well enough ¯\_(ツ)_/¯
        # the logic is: if we don't find a commit to the main branch, dated before the
        # first commit within this release, it's the user's first contribution
        prs_by_user_login: dict[str, list[PRInfo]] = defaultdict(list)
        for pr in [p for type_prs in prs.values() for p in type_prs]:
            prs_by_user_login[pr.user.login].append(pr)

        first_prs: list[PRInfo] = []

        async def is_user_first_commit(user_login: str) -> None:
            first_pr = sorted(prs_by_user_login[user_login], key=lambda p: p.created_at)[0]
            res = await self._request_with_retries(
                self._api_client,
                "GET",
                "/commits",
                params={
                    "author": user_login,
                    "sha": "main",
                    "until": first_pr.created_at.isoformat(),
                    "per_page": 1,
                },
            )
            res.raise_for_status()

            if len(res.json()) == 0:
                first_prs.append(first_pr)

        await asyncio.gather(*map(is_user_first_commit, prs_by_user_login.keys()))

        return first_prs

    async def get_release_info(self) -> ReleaseInfo:
        prs = await self.get_prs()
        first_time_contributors = await self._get_first_time_contributions(prs)
        return ReleaseInfo(
            pull_requests=prs,
            first_time_prs=first_time_contributors,
            base=self._base,
            release_tag=self._new_release_tag,
            version=self._new_release_version,
        )

    async def create_draft_release(self, body: str, release_branch: str) -> str:
        is_prerelease = bool(re.search(r"(a|b|rc)\d+$", self._new_release_version))
        res = await self._api_client.post(
            "/releases",
            json={
                "tag_name": self._new_release_tag,
                "target_commitish": release_branch,
                "name": self._new_release_tag,
                "draft": True,
                "prerelease": is_prerelease,
                "body": body,
            },
        )
        res.raise_for_status()
        return res.json()["html_url"]  # type: ignore[no-any-return]


class GHReleaseWriter:
    def __init__(self) -> None:
        self.text = ""

    def add_line(self, line: str) -> None:
        self.text += line + "\n"

    def add_pr_descriptions(self, infos: list[PRInfo]) -> None:
        for info in infos:
            self.add_line(f"* {info.title} by @{info.user.login} in {info.url}")


class ChangelogEntryWriter:
    def __init__(self) -> None:
        self.text = ""
        self._level = 0
        self._indent = "    "
        self._cc_type_map = {"fix": "bugfix", "feat": "feature"}

    def add_line(self, line: str) -> None:
        self.text += (self._indent * self._level) + line + "\n"

    def add_change(self, pr: PRInfo) -> None:
        with self.directive(
            "change",
            arg=pr.clean_title,
            type=self._cc_type_map.get(pr.cc_type, "misc"),
            pr=str(pr.number),
            issue=", ".join(map(str, pr.closes)),
        ):
            self.add_line("")
            for line in pr.description.splitlines():
                self.add_line(line)

    @contextlib.contextmanager
    def directive(self, name: str, arg: Optional[str] = None, **options: str) -> Generator[None, None, None]:
        self.add_line(f".. {name}:: {arg or ''}")
        self._level += 1
        for key, value in options.items():
            if value:
                self.add_line(f":{key}: {value}")
        yield
        self._level -= 1
        self.add_line("")


def build_gh_release_notes(release_info: ReleaseInfo) -> str:
    # this is for the most part just recreating GitHub's autogenerated release notes
    # but with three important differences:
    # 1. PRs are sorted into categories
    # 2. The conventional commit type is stripped from the title
    # 3. It works with our release branch process. GitHub doesn't pick up (all) commits
    #    made there depending on how things were merged
    doc = GHReleaseWriter()

    # doc.add_line("## Sponsors 🌟")  # noqa: ERA001
    # doc.add_line(f"- A huge 'Thank you!' to all sponsors across {_polar}, {_open_collective} and {_github_sponsors}!")  # noqa: ERA001

    doc.add_line("## What's changed")
    if features := release_info.pull_requests.get("feat"):
        doc.add_line("\n### New features 🚀")
        doc.add_pr_descriptions(features)
    if fixes := release_info.pull_requests.get("fix"):
        doc.add_line("\n### Bugfixes 🐛")
        doc.add_pr_descriptions(fixes)
    if release_info.first_time_prs:
        doc.add_line("\n## New contributors 🎉")
        for pr in release_info.first_time_prs:
            doc.add_line(f"* @{pr.user.login} made their first contribution in {pr.url}")

    ignore_sections = {"fix", "feat", "ci", "chore"}

    if other := [pr for k, prs in release_info.pull_requests.items() if k not in ignore_sections for pr in prs]:
        doc.add_line("\n<!-- Review these: Not all of them should go into the release notes -->")
        doc.add_line("### Other changes")
        doc.add_pr_descriptions(other)

    doc.add_line("\n**Full Changelog**")
    doc.add_line(release_info.compare_url)

    return doc.text


def build_changelog_entry(release_info: ReleaseInfo, interactive: bool = False) -> str:
    doc = ChangelogEntryWriter()
    with doc.directive("changelog", release_info.version):
        doc.add_line(f":date: {datetime.datetime.now(tz=datetime.timezone.utc).date().isoformat()}")
        doc.add_line("")
        change_types = {"fix", "feat"}
        for prs in release_info.pull_requests.values():
            for pr in prs:
                cc_type = pr.cc_type
                if cc_type in change_types or (interactive and click.confirm(f"Include PR #{pr.number} {pr.title!r}?")):
                    doc.add_change(pr)
                else:
                    click.secho(f"Ignoring change with type {cc_type}", fg="yellow")

    return doc.text


def _get_gh_token() -> str:
    if gh_token := os.getenv("GH_TOKEN"):
        click.secho("Using GitHub token from env", fg="blue")
        return gh_token

    gh_executable = shutil.which("gh")
    if not gh_executable:
        click.secho("GitHub CLI not installed", fg="yellow")
    else:
        click.secho("Using GitHub CLI to obtain GitHub token", fg="blue")
        proc = subprocess.run([gh_executable, "auth", "token"], check=True, capture_output=True, text=True)  # noqa: S603
        if out := (proc.stdout or "").strip():
            return out

    click.secho("Could not find any GitHub token", fg="red")
    sys.exit(1)


def _get_latest_tag() -> str:
    click.secho("Using latest tag", fg="blue")
    return subprocess.run(  # noqa: S602
        "git tag --sort=taggerdate | tail -1",  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        shell=True,
    ).stdout.strip()


def _write_changelog_entry(changelog_entry: str) -> None:
    changelog_path = pathlib.Path("docs/changelog.rst")
    changelog_lines = changelog_path.read_text().splitlines()
    line_no = next(
        (i for i, line in enumerate(changelog_lines) if line.startswith(".. changelog::")),
        None,
    )
    if not line_no:
        msg = "Changelog start not found"
        raise ValueError(msg)

    changelog_lines[line_no:line_no] = changelog_entry.splitlines()
    changelog_path.write_text("\n".join(changelog_lines))


def update_pyproject_version(new_version: str) -> None:
    # can't use tomli-w / tomllib for this as is messes up the formatting
    pyproject = pathlib.Path("pyproject.toml")
    content = pyproject.read_text()
    content = re.sub(r'(\nversion ?= ?")\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?("\s*\n)', rf"\g<1>{new_version}\g<2>", content)
    pyproject.write_text(content)


@click.command()
@click.argument("version")
@click.option("--base", help="Previous release tag. Defaults to the latest tag")
@click.option("--branch", help="Release branch", default="main")
@click.option(
    "--gh-token",
    help="GitHub token. If not provided, read from the GH_TOKEN env variable. "
    "Alternatively, if the GitHub CLI is installed, it will be used to fetch a token",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Interactively decide which commits should be included in the release notes",
    default=False,
)
@click.option("-c", "--create-draft-release", is_flag=True, help="Create draft release on GitHub")
def cli(
    base: Optional[str],
    branch: str,
    version: str,
    gh_token: Optional[str],
    interactive: bool,
    create_draft_release: bool,
) -> None:
    if gh_token is None:
        gh_token = _get_gh_token()
    if base is None:
        base = _get_latest_tag()

    if not re.match(r"\d+\.\d+\.\d+((a|b|rc)\d+)?$", version):
        click.secho(f"Invalid version: {version!r}")
        sys.exit(1)

    new_tag = f"v{version}"

    click.secho(f"Creating release notes for tag {new_tag}, using {base} as a base", fg="cyan")

    thing = _Thing(gh_token=gh_token, base=base, release_branch=branch, tag=new_tag, version=version)
    loop = asyncio.new_event_loop()

    release_info = loop.run_until_complete(thing.get_release_info())
    gh_release_notes = build_gh_release_notes(release_info)
    changelog_entry = build_changelog_entry(release_info, interactive=interactive)

    click.secho("Writing changelog entry", fg="green")
    _write_changelog_entry(changelog_entry)

    if create_draft_release:
        click.secho("Creating draft release", fg="blue")
        release_url = loop.run_until_complete(thing.create_draft_release(body=gh_release_notes, release_branch=branch))
        click.echo(f"Draft release available at: {release_url}")
    else:
        click.echo(gh_release_notes)

    loop.close()


if __name__ == "__main__":
    cli()
