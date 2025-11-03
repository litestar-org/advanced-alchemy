# Testing Guide

This document outlines the testing standards for the `advanced-alchemy` project.

## Framework

- **Pytest**: The testing framework used for all tests.

## Standards

- **Function-based Tests**: All tests must be function-based. Class-based tests are not permitted.
- **90%+ Coverage**: All new code must have at least 90% test coverage.
- **Parallel Execution**: Tests must be able to run in parallel using `pytest-xdist` (`pytest -n auto`).
- **N+1 Detection**: Tests for database operations that retrieve lists of objects must include checks for N+1 query regressions.
- **Concurrency**: Tests for code that modifies shared state must include checks for race conditions and other concurrency issues.

## Running Tests

- `make test`: Run all tests.
- `make coverage`: Run tests with a coverage report.
