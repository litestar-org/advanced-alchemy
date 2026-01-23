# PRD: Refactor Listeners

## 1. Introduction

This specification outlines the refactoring of `advanced_alchemy/_listeners.py` to address technical debt, improve code quality, and align with SQLAlchemy 2.0 best practices. The goal is to enhance the robustness of event listener handling, particularly regarding asynchronous context management, without introducing breaking changes.

## 2. Problem Statement

The current implementation of event listeners (`FileObjectListener`, `CacheInvalidationListener`) relies on:
1.  **Global State**: Listeners are registered globally on the `Session` class, requiring runtime checks (`session.info`) to selectively enable/disable them.
2.  **Fragile Context Management**: A global `contextvars.ContextVar` (`_is_async_context`) is manually toggled in configuration classes to inform listeners whether to behave asynchronously. This is error-prone and implicit.
3.  **Complex Logic**: The `_inspect_attribute_changes` function is monolithic and difficult to maintain.
4.  **Implicit Dependencies**: The listeners rely on imported modules inside methods to avoid circular imports or runtime errors, which obscures dependencies.

## 3. Goals & Non-Goals

### Goals
- **Decouple Listeners**: Move from global `Session` listeners to `sessionmaker`-scoped listeners where possible.
- **Remove Implicit Context**: Eliminate `set_async_context` and `is_async_context` in favor of explicit Sync/Async listener implementations.
- **Refactor Inspection Logic**: Break down `_inspect_attribute_changes` into a testable, single-responsibility component.
- **Maintain Compatibility**: Ensure existing `setup_file_object_listeners` and `setup_cache_listeners` functions continue to work for manual setups.
- **Type Safety**: Improve typing around event payloads.

### Non-Goals
- Changing the public API of `FileObject` or `CacheManager`.
- altering the behavior of how files are saved/deleted (logic remains, structure changes).

## 4. Proposed Architecture

### 4.1. Split Listeners
Instead of a single `FileObjectListener` checking `is_async_context()`, we will define:
- `FileObjectListenerProtocol`: A common interface/mixin for shared logic (inspection).
- `SyncFileObjectListener`: Implements `after_commit`/`after_rollback` using synchronous execution.
- `AsyncFileObjectListener`: Implements `after_commit`/`after_rollback` using `asyncio.create_task`.

### 4.2. SessionFactory Registration
The `SQLAlchemyAsyncConfig` and `SQLAlchemySyncConfig` classes will be updated to register the appropriate listener instance directly on the `sessionmaker` (or `async_sessionmaker`) they produce.

```python
# advanced_alchemy/config/asyncio.py
def create_session_maker(self) -> Callable[[], AsyncSession]:
    maker = ...
    event.listen(maker, "after_commit", AsyncFileObjectListener.after_commit)
    return maker
```

### 4.3. Logic Extraction
The `_inspect_attribute_changes` function will be refactored into a `FileObjectInspector` class or a set of focused utility functions:
- `detect_single_file_changes(instance, attr)`
- `detect_list_mutation_changes(instance, attr)`
- `detect_list_replacement_changes(instance, attr)`

### 4.4. Backward Compatibility
The global functions `setup_file_object_listeners` and `setup_cache_listeners` will be retained. They will:
1.  Register the *Global* variant of the listeners (which might need to retain some runtime checking or default to a "safe" mode) OR
2.  Accept an optional `bind` or `sessionmaker` argument to allow manual scoping.

## 5. Implementation Details

### 5.1. `advanced_alchemy/_listeners.py`
- **Remove**: `_active_file_operations`, `_active_cache_operations` global sets (move to instance attributes if possible, or keep module-level but managed better).
- **Remove**: `set_async_context`, `reset_async_context`, `is_async_context`, `_is_async_context`.
- **Create**:
    - `BaseFileObjectListener`: Contains `before_flush`.
    - `SyncFileObjectListener(BaseFileObjectListener)`
    - `AsyncFileObjectListener(BaseFileObjectListener)`
    - `BaseCacheListener`, `SyncCacheListener`, `AsyncCacheListener`.

### 5.2. `advanced_alchemy/config/*.py`
- Remove calls to `set_async_context`.
- In `create_session_maker`, instantiate and register the appropriate listener.

## 6. Acceptance Criteria

1.  **No functionality loss**: File uploads, deletions, and cache invalidations work exactly as before in both Sync and Async modes.
2.  **No global context vars**: `_is_async_context` is removed.
3.  **Scoped Listeners**: Listeners are attached to the `sessionmaker` created by configs, not the global `Session` class (unless manually setup).
4.  **Tests Pass**: All existing tests (integration, unit) pass.
5.  **Clean Code**: `_inspect_attribute_changes` complexity is reduced (Cyclomatic complexity < 10 preferred).
6.  **Coverage**: 90%+ coverage on `_listeners.py`.

## 7. Migration Guide
No changes required for users using `SQLAlchemyAsyncConfig` / `SQLAlchemySyncConfig`.
Users manually setting up sessions should use the new `register_listeners(sessionmaker)` API or continue using `setup_file_object_listeners()` (which will be marked as legacy/global).
