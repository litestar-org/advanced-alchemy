# Research Plan: Refactoring `_listeners.py`

## Goal
Improve code quality, remove tech debt, and align with SQLAlchemy 2.0 best practices for event listeners, specifically improving the async/sync context handling.

## Findings

1.  **Current State**:
    - Global registration of listeners on `Session`/`AsyncSession` classes.
    - Runtime checks (`_is_listener_enabled`, `is_async_context`) using `contextvars` and `session.info`.
    - Manual context switching (`set_async_context`).
    - Complex attribute inspection logic.

2.  **Best Practices (SQLAlchemy 2.0)**:
    - Listeners should ideally be scoped to the `sessionmaker` or `Engine` rather than globally, especially in libraries.
    - `AsyncSession` events are distinct but interact with underlying `Session` events.
    - Blocking I/O in listeners (even async ones) should be carefully managed (which the current code does via `create_task`).

3.  **Refactoring Strategy**:
    - **Scoping**: Move from global registration to `sessionmaker`-scoped registration. This allows different configs to have different listener behaviors without global flags.
    - **Context Handling**: Instead of `_is_async_context` ContextVar, use distinct listener classes or instances for Sync vs Async contexts.
        - `SyncFileObjectListener`: Handles synchronous commits/rollbacks.
        - `AsyncFileObjectListener`: Handles `asyncio.create_task` for commits/rollbacks.
    - **Integration**: Update `SQLAlchemyAsyncConfig` and `SQLAlchemySyncConfig` to register these listeners on the `sessionmaker` they create.
    - **Logic Simplification**: Refactor `_inspect_attribute_changes` into a cleaner, testable service or utility class (e.g., `FileChangeInspector`).
    - **Compatibility**: Retain `setup_file_object_listeners` for backward compatibility, but update its implementation to warn or use the new mechanism globally if needed.

## Architecture Change

### Old Way
```python
# Global Context
set_async_context(True)
setup_file_object_listeners() # Registers on global Session class

# Inside Listener
if is_async_context():
   asyncio.create_task(...)
```

### New Way
```python
# Config (Async)
listener = AsyncFileObjectListener()
event.listen(async_sessionmaker, "after_commit", listener.after_commit)

# Config (Sync)
listener = SyncFileObjectListener()
event.listen(sync_sessionmaker, "after_commit", listener.after_commit)
```

## Risks
- **Backward Compatibility**: Users manually setting up sessions without our Config objects might lose listeners if they relied on the global `setup_*` function and we remove it. We must keep `setup_file_object_listeners` working (globally).
- **Event Propagation**: Ensure `AsyncSession` listeners fire correctly when attached to `async_sessionmaker`.

## Verification
- Test with both `AsyncSession` and `Session`.
- Test with `sessionmaker` scoping.
