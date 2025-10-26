Invoke the Docs & Vision agent for quality gate, documentation, and cleanup.

**What this does:**
- Validates all acceptance criteria met
- Updates Sphinx documentation (RST)
- Creates/updates guides in docs/guides/
- Adds changelog entry
- Cleans workspace and archives requirement

**Usage:**
```
/review vector-search-support
```

**Or for current active requirement:**
```
/review
```

**The Docs & Vision agent will:**

### Phase 1: Quality Gate
1. Read PRD acceptance criteria
2. Verify all tasks complete
3. Check test results
4. Validate:
   - ✅ Feature works across all 8+ database backends
   - ✅ Async and sync both functional
   - ✅ Framework integrations updated
   - ✅ Backward compatible
   - ✅ Performance acceptable
   - ✅ Type hints follow Python 3.9+ style
   - ✅ SQLAlchemy 2.0 syntax used
   - ✅ Tests use pytest markers
5. Request fixes if criteria not met

### Phase 2: Documentation
1. Update Sphinx reference docs (RST format):
   - API documentation with auto-generated signatures
   - Code examples with auto-pytabs for async/sync
   - Cross-references with paramlinks
2. Create/update guide in `docs/guides/patterns/`:
   - Overview and when to use
   - Basic usage (async & sync)
   - Database-specific notes (PostgreSQL, Oracle, MySQL, SQLite, etc.)
   - Framework integration (Litestar, FastAPI, Flask, Sanic, Starlette)
   - Advanced patterns
   - Performance considerations
   - Testing examples
   - Troubleshooting
3. Validate documentation builds:
   ```bash
   make docs  # Build docs
   make docs-linkcheck  # Validate links
   ```

**Note:** Changelog entries are auto-generated from GitHub issues. NEVER manually add changelog entries.

### Phase 3: Cleanup
1. Clean tmp/ directories:
   ```bash
   find requirements/{slug}/tmp -type f -delete
   ```
2. Archive completed requirement:
   ```bash
   mv requirements/{slug} requirements/archive/
   ```
3. Update requirements/README.md with completion note

### Phase 4: Summary
Generate completion report with:
- ✅ Acceptance criteria status
- 📚 Documentation links
- 🧪 Test coverage statistics
- 📦 Modified files
- 🎯 Next steps

**Documentation Tools Used:**
- Sphinx + Shibuya theme
- sphinx-design (cards, tabs, grids)
- sphinx-copybutton (copy code blocks)
- sphinxcontrib-mermaid (diagrams)
- auto-pytabs (async/sync code tabs)
- sphinx-paramlinks (parameter cross-references)

**After review:**
Feature is complete and ready for PR/release!
