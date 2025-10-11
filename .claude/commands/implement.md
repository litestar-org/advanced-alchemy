Invoke the Expert agent to implement features based on the PRD.

**What this does:**
- Reads PRD and tasks from `requirements/{slug}/`
- Researches implementation patterns
- Implements repositories, services, models, migrations
- Updates framework integrations
- Tracks progress in workspace

**Usage:**
```
/implement vector-search-support
```

**Or for new work without existing plan:**
```
/implement
```

**The Expert will:**
1. Read PRD, tasks, and recovery guide
2. Consult AGENTS.md for standards
3. Research similar patterns in codebase
4. Get library docs via Context7 as needed
5. Implement following strict quality rules:
   - Stringified type hints (NO `from __future__ import annotations` in library code)
   - SQLAlchemy 2.0 syntax only
   - Edit ONLY `_async.py` files (sync auto-generated)
   - Service wraps repository (never bypass)
   - Test with pytest markers (avoid 20+ min full runs)
6. Update workspace (tasks.md, recovery.md, progress.md)
7. Hand off to Testing agent when complete

**Quality Standards Enforced:**
- ✅ Python 3.9+ type hints (stringified)
- ✅ SQLAlchemy 2.0 (`select()`, `Mapped[]`, `mapped_column()`)
- ✅ Multi-database compatibility (8+ backends)
- ✅ Framework integration patterns from fullstack-spa & dma
- ✅ Error messages: lowercase, no periods, include context

**After implementation, run:**
- `/test` to create comprehensive tests
- Or invoke Testing agent directly
