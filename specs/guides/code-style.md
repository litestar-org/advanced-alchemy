# Code Style Guide

This document outlines the code style standards for the `advanced-alchemy` project.

## Formatting

- **Ruff**: Used for linting and formatting. Configuration is in `pyproject.toml`.
- **Black**: Used for code formatting, integrated into `ruff`.

## Type Hinting

- **MyPy**: Used for static type checking.
- **PEP 604**: Use `T | None` for optional types instead of `typing.Optional[T]`.
- **No `__future__` annotations**: Do not use `from __future__ import annotations`.

## Docstrings

- **Google Style**: All public functions, classes, and methods must have Google-style docstrings.

## Commands

- `make lint`: Run all linting and type checking.
- `make fix`: Automatically fix formatting issues.
