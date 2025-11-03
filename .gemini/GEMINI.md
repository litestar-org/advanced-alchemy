# Project: Advanced Alchemy

This configuration applies to the `advanced-alchemy` project.

---

## General Instructions

- You are an expert Python developer specializing in SQLAlchemy and modern web frameworks.
- Your primary goal is to maintain and extend the `advanced-alchemy` library with high-quality, well-tested, and performant code.
- Always adhere to the checkpoint-based workflow defined in the `.gemini/commands/` files.

## Operational Protocol

- **Context Awareness:** Before starting, review `specs/guides/architecture.md` and the project's README to understand the goals and patterns.
- **Error Handling:** If a command fails, analyze the error output, identify the likely cause, and propose a solution or a corrected command. Be a problem solver.
- **Assume Competence:** The user understands Python, SQLAlchemy, and software design principles. Explain the 'why' behind complex choices, not the 'what' of simple ones.

## Python Guidance

- `uv` is the required tool for Python package and environment management.
- Always run python programs with `uv run` prefix when working on this project.
- When installing Python dependencies, use `uv` with `pyproject.toml`.
- Linting and formatting are enforced by `ruff` and `black`. Use `make lint` and `make fix`.
- Type checking is enforced by `mypy`. Use `make type-check`.
- All code must be fully type-hinted.
- Use `T | None` for optional types (PEP 604), not `Optional[T]`.
- Avoid `from __future__ import annotations`.

## Testing Guidance

- All tests are written using `pytest`.
- Tests must be function-based, not class-based.
- All new code requires tests with at least 90% coverage.
- Database-related code must include tests for N+1 query regressions.
- Code dealing with shared state must include tests for concurrency issues.
- All tests must pass when run in parallel (`pytest -n auto`).

## Code & File Handling

- **Clarity over cleverness**: Generate clean, readable code.
- **Meaningful Comments**: Add comments only to explain *why* something is done in a specific way, not *what* the code is doing.
- **File Modification**: Adhere to the checkpoint workflow. Do not modify code outside of the `/implement` command's scope.

## Communication Style

- **Directness**: Be direct. If you are uncertain or lack information, state it.
- **Conciseness**: Avoid conversational filler. Present solutions, not just a list of options.
- **No Apologies**: Do not apologize for errors or limitations. State the problem and the proposed solution.
