import re
from pathlib import Path

PYPI_BANNER = '<img src="https://raw.githubusercontent.com/litestar-org/branding/main/assets/projects/advanced-alchemy/banners/banner-inline-light.png" alt="Advanced Alchemy" width="560" />'


def generate_pypi_readme() -> None:
    """Generate the PyPI README from the root README.md with stripped trailing whitespace."""
    source = Path("README.md").read_text(encoding="utf-8")
    output = re.sub(r"<!-- github-banner-start -->[\w\W]*?<!-- github-banner-end -->", PYPI_BANNER, source, count=1)
    output = re.sub(r"<!-- github-banner-start -->[\w\W]*?<!-- github-banner-end -->", "", output)
    output = re.sub(r"<!-- contributors-start -->[\w\W]*?<!-- contributors-end -->", "", output)
    output = re.sub(r"<!-- ALL-CONTRIBUTORS-BADGE:START[\w\W]*?<!-- ALL-CONTRIBUTORS-BADGE:END -->", "", output)

    output = "\n".join(line.rstrip() for line in output.strip().splitlines()) + "\n"
    Path("docs/PYPI_README.md").write_text(output, encoding="utf-8")


if __name__ == "__main__":
    generate_pypi_readme()
