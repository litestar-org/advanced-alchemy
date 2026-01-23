# Tasks: Refactor Listeners

## Analysis & Research
- [x] Analyze current `_listeners.py` structure [6459ec4a]
- [x] Research SQLAlchemy 2.0 listener scoping [6459ec4a]

## Implementation - Phase 1: Core Refactoring
- [x] Refactor `_inspect_attribute_changes` into `FileObjectInspector` class/utilities [6459ec4a]
    - [x] Extract single file handling [6459ec4a]
    - [x] Extract list mutation handling [6459ec4a]
    - [x] Extract list replacement handling [6459ec4a]
- [x] Create Listener Classes [6459ec4a]
    - [x] `BaseFileObjectListener` (Shared `before_flush`) [6459ec4a]
    - [x] `SyncFileObjectListener` (Sync `after_commit`/`rollback`) [6459ec4a]
    - [x] `AsyncFileObjectListener` (Async `after_commit`/`rollback`) [6459ec4a]
    - [x] Repeat for `CacheInvalidationListener` [6459ec4a]

## Implementation - Phase 2: Configuration Updates
- [x] Update `advanced_alchemy/config/asyncio.py` [c2e0d599]
    - [x] Remove `set_async_context` [c2e0d599]
    - [x] Register `AsyncFileObjectListener` in `create_session_maker` [c2e0d599]
- [x] Update `advanced_alchemy/config/sync.py` [c2e0d599]
    - [x] Remove `set_async_context` [c2e0d599]
    - [x] Register `SyncFileObjectListener` in `create_session_maker` [c2e0d599]

## Implementation - Phase 3: Cleanup & Compatibility
- [x] Update `setup_file_object_listeners` to use new classes (global fallback) [6459ec4a]
- [x] Remove `_is_async_context` and helper functions (Restored for compat but deprecated) [6459ec4a]
- [x] Ensure `_active_file_operations` are managed correctly [6459ec4a]

## Verification
- [x] Run all tests `make test` [passed]
- [ ] Verify `make coverage` for `_listeners.py`
