# Agent Coordination Guide

Comprehensive guide for the Advanced Alchemy agent system, covering agent responsibilities, workflow patterns, MCP tool usage, and workspace management.

## Agent Responsibilities Matrix

| Responsibility | Planner | Expert | Testing | Docs & Vision |
|----------------|---------|--------|---------|---------------|
| **Research** | ✅ Primary | ✅ Implementation details | ✅ Test patterns | ✅ Doc standards |
| **Planning** | ✅ Primary | ❌ | ❌ | ❌ |
| **Implementation** | ❌ | ✅ Primary | ✅ Tests only | ❌ |
| **Testing** | ❌ | ✅ Verify own code | ✅ Primary | ✅ Run quality gate |
| **Documentation** | ✅ PRD/tasks | ✅ Code comments | ✅ Test docs | ✅ Primary |
| **Quality Gate** | ❌ | ❌ | ❌ | ✅ Primary |
| **Cleanup** | ❌ | ❌ | ❌ | ✅ MANDATORY |
| **Multi-Model Consensus** | ✅ Primary | ✅ Complex decisions | ❌ | ❌ |
| **Workspace Management** | ✅ Create | ✅ Update | ✅ Update | ✅ Archive & Clean |

## Workflow Phases

### Phase 1: Planning (`/plan`)

**Agent:** Planner
**Purpose:** Research-grounded planning and workspace creation

**Steps:**

1. Research guides, Context7, WebSearch
2. Create structured plan with zen.planner
3. Get consensus on complex decisions (zen.consensus)
4. Create workspace in `requirements/{requirement}/`
5. Write PRD, tasks, research, recovery docs

**Output:**

```
requirements/{requirement-slug}/
├── prd.md          # Product Requirements Document
├── tasks.md        # Implementation checklist
├── research/       # Research findings
│   └── plan.md    # Detailed plan
├── tmp/            # Temporary files
└── recovery.md     # Session resume guide
```

**Hand off to:** Expert agent for implementation

### Phase 2: Implementation (`/implement`)

**Agent:** Expert
**Purpose:** Write clean, type-safe, cross-database code

**Steps:**

1. Read workspace (prd.md, tasks.md, research/plan.md)
2. Research implementation details (guides, Context7)
3. Implement following AGENTS.md standards
4. Run targeted tests with markers
5. Update workspace (tasks.md, recovery.md)

**Tools Used:**

- zen.debug (systematic debugging)
- zen.thinkdeep (complex decisions)
- zen.analyze (code analysis)
- Context7 (library docs)

**Output:**

- Production code in advanced_alchemy/
- Updated workspace files

**Hand off to:** Testing agent for comprehensive tests

### Phase 3: Testing (`/test`)

**Agent:** Testing
**Purpose:** Create comprehensive unit and integration tests

**Steps:**

1. Read implementation
2. Consult testing guide
3. Create unit tests (tests/unit/)
4. Create integration tests (tests/integration/)
5. Test all 8+ database backends with markers
6. Test edge cases
7. Verify coverage (80%+ repositories/services, 90%+ core)
8. Update workspace

**Output:**

- Unit tests in tests/unit/
- Integration tests in tests/integration/
- Updated workspace files

**Hand off to:** Docs & Vision for documentation and quality gate

### Phase 4: Review (`/review`)

**Agent:** Docs & Vision
**Purpose:** Documentation, quality gate, and MANDATORY cleanup

**3 Sequential Phases:**

1. **Documentation:**
   - Update docs/guides/
   - Update Sphinx API reference (RST)
   - Add changelog entry
   - Build docs locally

2. **Quality Gate (MANDATORY):**
   - Run `make lint` (must pass)
   - Check type hints are stringified
   - Verify async/sync autogeneration worked
   - Run full test suite (must pass)
   - Verify PRD acceptance criteria
   - **BLOCKS if quality gate fails**

3. **Cleanup (MANDATORY):**
   - Remove all tmp/ directories
   - Archive requirement to requirements/archive/
   - Keep only last 3 active requirements
   - Archive planning reports

**Output:**

- Complete documentation
- Clean workspace
- Archived requirement
- Work ready for PR/commit

## Agent Invocation Patterns

### Planner Invoking Consensus

For complex architectural decisions:

```python
Task(
    subagent_type="general-purpose",
    description="Get multi-model consensus on repository pattern",
    prompt="""
Use zen.consensus to get multi-model agreement:

Question: Should we add native vector search support to repositories?

Models to consult:
- gemini-2.5-pro (neutral stance)
- openai/gpt-5 (neutral stance)

Include relevant files for context:
- advanced_alchemy/repository/_async.py
- advanced_alchemy/service/_async.py

Write consensus findings to requirements/{requirement}/research/consensus.md
"""
)
```

### Expert Invoking Debugging

For systematic debugging:

```python
Task(
    subagent_type="general-purpose",
    description="Debug Oracle connection pool issue",
    prompt="""
Use zen.debug for systematic debugging:

Problem: Oracle connection pool exhaustion with asyncio

Use zen.debug to:
1. State hypothesis about root cause
2. Investigate code paths
3. Check for leaked connections
4. Verify pool configuration
5. Test fix

Write findings to requirements/{requirement}/tmp/debug-{issue}.md
"""
)
```

### Testing Invoking Test Generation

Testing agent is usually NOT invoked by other agents - it's invoked directly via `/test` command.

### Docs & Vision Blocking on Quality Gate

Quality gate BLOCKS completion if standards not met:

```markdown
❌ QUALITY GATE FAILED

Issues found:
- 3 files with `from __future__ import annotations`
- 2 files editing _sync.py instead of _async.py
- make lint has 5 errors

⚠️ WORK NOT COMPLETE
Do NOT proceed to cleanup phase.
Fix issues above and re-run quality gate.
```

## MCP Tools Matrix

### Tool: zen.planner

**Who uses:** Planner agent
**Purpose:** Structured, multi-step planning
**When:** Creating detailed implementation plans

**Example:**

```python
mcp__zen__planner(
    step="Plan repository filter enhancements for all 8 databases",
    step_number=1,
    total_steps=6,
    next_step_required=True
)
```

### Tool: zen.consensus

**Who uses:** Planner, Expert
**Purpose:** Multi-model decision verification
**When:** Complex architectural decisions, significant API changes

**Example:**

```python
mcp__zen__consensus(
    step="Evaluate: Add native async context manager support to repositories",
    models=[
        {"model": "gemini-2.5-pro", "stance": "neutral"},
        {"model": "openai/gpt-5", "stance": "neutral"}
    ],
    relevant_files=["advanced_alchemy/repository/_async.py"],
    next_step_required=False
)
```

### Tool: zen.debug

**Who uses:** Expert
**Purpose:** Systematic debugging workflow
**When:** Complex bugs, mysterious errors, performance issues

**Example:**

```python
mcp__zen__debug(
    step="Investigate N+1 query pattern in service layer",
    step_number=1,
    total_steps=5,
    hypothesis="Service not using selectinload for relationships",
    findings="Found 3 service methods missing eager loading",
    confidence="high",
    next_step_required=True
)
```

### Tool: zen.thinkdeep

**Who uses:** Expert
**Purpose:** Deep analysis for complex decisions
**When:** Architecture decisions, complex refactoring

**Example:**

```python
mcp__zen__thinkdeep(
    step="Analyze adding native JSONB support across all databases",
    step_number=1,
    total_steps=4,
    hypothesis="Can use dialect-specific JSON types with fallback",
    findings="PostgreSQL has JSONB, others have JSON or TEXT",
    focus_areas=["architecture", "performance"],
    confidence="high",
    next_step_required=True
)
```

### Tool: zen.analyze

**Who uses:** Expert, Docs & Vision
**Purpose:** Code analysis (architecture, performance, security, quality)
**When:** Code review, performance optimization, quality gate

**Example:**

```python
mcp__zen__analyze(
    step="Analyze repository layer for performance bottlenecks",
    step_number=1,
    total_steps=3,
    analysis_type="performance",
    findings="Found N+1 queries in relationship loading",
    confidence="high",
    next_step_required=True
)
```

### Tool: Context7

**Who uses:** All agents
**Purpose:** Get up-to-date library documentation
**When:** Need current API reference for libraries (asyncpg, oracledb, Litestar, etc.)

**Example:**

```python
# Step 1: Resolve library ID
mcp__context7__resolve-library-id(libraryName="asyncpg")

# Step 2: Get docs
mcp__context7__get-library-docs(
    context7CompatibleLibraryID="/MagicStack/asyncpg",
    topic="connection pooling"
)
```

### Tool: WebSearch

**Who uses:** All agents
**Purpose:** Research current best practices (2025+)
**When:** Need recent best practices, database-specific patterns

**Example:**

```python
WebSearch(query="SQLAlchemy 2.0 upsert patterns PostgreSQL Oracle 2025")
```

## Workspace Management

### Structure

```
requirements/
├── {requirement-1}/      # Active requirement
│   ├── prd.md
│   ├── tasks.md
│   ├── recovery.md
│   ├── research/
│   │   └── plan.md
│   └── tmp/              # Cleaned by Docs & Vision
├── {requirement-2}/      # Active requirement
├── {requirement-3}/      # Active requirement
├── archive/              # Completed requirements
│   └── {old-requirement}/
└── README.md
```

### Cleanup Protocol (MANDATORY)

**When:** After every `/review` (Docs & Vision agent)

**Steps:**

1. Remove all tmp/ directories:

   ```bash
   find requirements/*/tmp -type d -exec rm -rf {} +
   ```

2. Archive completed requirement:

   ```bash
   mv requirements/{requirement} requirements/archive/{requirement}
   ```

3. Keep only last 3 active requirements:

   ```bash
   # If more than 3 active, move oldest to archive
   ```

**This is MANDATORY - never skip cleanup.**

### Session Continuity

To resume work across sessions/context resets:

```python
# 1. List active requirements
Glob("requirements/*/prd.md")

# 2. Read recovery.md to understand status
Read("requirements/{requirement}/recovery.md")

# 3. Check task progress
Read("requirements/{requirement}/tasks.md")

# 4. Review PRD for full context
Read("requirements/{requirement}/prd.md")

# 5. Review planning details
Read("requirements/{requirement}/research/plan.md")
```

## Code Quality Standards

All agents MUST enforce AGENTS.md standards:

### ✅ ALWAYS DO

- **Type hints:** Stringified in library code: `def foo(user: "User"):`
- **SQLAlchemy 2.0:** `select()`, `Mapped[]`, `mapped_column()`
- **Service layer:** Service wraps repository, never bypass
- **Edit async files:** ONLY edit `_async.py`, sync auto-generated
- **Test with markers:** `@pytest.mark.asyncpg`, `@pytest.mark.oracle18c`
- **Error messages:** lowercase, no periods, include context
- **Function-based tests:** `def test_something():`
- **Cross-database compatibility:** Test all 8+ backends

### ❌ NEVER DO

- **Future annotations:** `from __future__ import annotations` in library code
- **Edit sync files:** `_sync.py` auto-generated, don't touch
- **Bypass repository:** Don't use session directly in service
- **Modern union syntax:** Use `Optional[T]`, not `T | None` in library code
- **SQLAlchemy 1.x:** No `.query()`, use `select()`
- **Skip database:** Must work on all 8+ backends
- **Class-based tests:** `class TestSomething:`
- **Full test runs:** Use markers to avoid 20+ minute runs

## Guides Reference

All agents should consult guides before implementing:

### Framework Integration Guides

```
docs/guides/framework-integration/
├── litestar.md          # Primary framework
├── fastapi.md
├── flask.md
├── sanic.md
└── starlette.md
```

### Database Backend Guides

```
docs/guides/database-backends/
├── postgresql.md
├── oracle.md
├── mysql.md
├── sqlite.md
├── mssql.md
├── cockroachdb.md
├── spanner.md
└── duckdb.md
```

### Pattern Guides

```
docs/guides/patterns/
├── repository-service.md    # Core architecture
├── type-hints.md
├── error-handling.md
├── async-sync.md
├── base-models.md
├── filtering.md
└── bulk-operations.md
```

### Testing Guide

```
docs/guides/testing/
├── testing.md
├── integration.md
└── conventions.md
```

### Quick Reference

```
docs/guides/quick-reference/
├── quick-reference.md
├── litestar-playbook.md
├── fastapi-playbook.md
└── sqlalchemy-2-migration.md
```

## Recovery Patterns

### After Context Reset

```python
# 1. Find active work
active_requirements = Glob("requirements/*/prd.md")

# 2. For each active requirement, check status
for req_prd in active_requirements:
    req_dir = req_prd.parent
    recovery = Read(f"{req_dir}/recovery.md")
    # Shows: Status, Last updated, Next steps

# 3. Resume from most recent
Read("{most_recent_requirement}/recovery.md")  # Clear next steps
Read("{most_recent_requirement}/tasks.md")      # See what's done
```

### After Session Timeout

Same as context reset - recovery.md has all needed info.

### After Cleanup

If requirement archived:

```python
# Find in archive
Glob("requirements/archive/*/prd.md")

# Can still read archived requirements
Read("requirements/archive/{requirement}/recovery.md")
```

## Command Workflow

### Full Feature Development

```bash
# 1. Plan
/plan add full-text search support across all databases

# Creates: requirements/full-text-search/

# 2. Implement
/implement

# Modifies code, updates workspace

# 3. Test
/test

# Creates tests, verifies passing on all backends

# 4. Review (3 phases: docs → quality gate → cleanup)
/review

# Phase 1: Documentation
# Phase 2: Quality gate (must pass)
# Phase 3: Cleanup (mandatory)

# Result: requirements/full-text-search/ → requirements/archive/full-text-search/
```

### Bug Fix Workflow

```bash
# 1. Plan (optional for simple bugs)
/plan fix Oracle connection pool exhaustion

# 2. Debug and implement
/implement

# Expert uses zen.debug for systematic investigation

# 3. Test
/test

# Add regression test

# 4. Review
/review

# Quality gate + cleanup
```

## Best Practices

### For Planner

1. **Always research first** - guides, Context7, WebSearch
2. **Use zen.planner** for complex work
3. **Get consensus** on significant decisions
4. **Consider all 8+ databases** in PRD
5. **Consider all 5 frameworks** (Litestar, FastAPI, Flask, Sanic, Starlette)
6. **Create complete workspace** - don't skip files
7. **Write clear recovery.md** - enable easy resume

### For Expert

1. **Read the plan first** - don't guess
2. **Consult guides** - patterns, frameworks, databases
3. **Use zen tools** for complex work (debug, thinkdeep, analyze)
4. **Follow AGENTS.md** ruthlessly
5. **Edit ONLY _async.py** - never edit _sync.py
6. **Test with markers** - avoid 20+ minute test runs
7. **Update workspace** continuously
8. **Test as you go** - don't wait for Testing agent
9. **Check all 8+ databases** - compatibility is critical

### For Testing

1. **Consult testing guide** before creating tests
2. **Function-based tests** always (no classes)
3. **Mark appropriately** - `@pytest.mark.asyncpg`, `@pytest.mark.oracle18c`, etc.
4. **Test all 8+ backends** - use markers
5. **Test edge cases** - empty, None, errors, concurrency, bulk operations
6. **Verify coverage** - 80%+ repositories/services, 90%+ core
7. **All tests must pass** before handoff
8. **Use fixture naming** - `sample_user`, `users_batch`

### For Docs & Vision

1. **Phase 1 (Docs)** - Comprehensive and clear
2. **Use Sphinx + Shibuya** - full documentation stack
3. **Phase 2 (Quality Gate)** - BLOCK if standards not met
4. **Check stringified type hints** - no `from __future__ import annotations`
5. **Verify async/sync autogen** - _sync.py auto-generated
6. **Phase 3 (Cleanup)** - MANDATORY, never skip
7. **Archive systematically** - maintain clean workspace
8. **Final verification** - one last `make lint && make test`

## Troubleshooting

### Quality Gate Failing

```markdown
**Problem:** Quality gate keeps failing

**Solution:**
1. Check specific failure reasons
2. Fix anti-patterns (future annotations, editing _sync.py, bypassing repository)
3. Run `make fix` to auto-fix lint issues
4. Run `make lint` to regenerate _sync.py files
5. Re-run quality gate
6. DO NOT proceed to cleanup until passing
```

### Workspace Getting Cluttered

```markdown
**Problem:** requirements/ has too many folders

**Solution:**
1. Run `/review` on oldest requirements
2. Let Docs & Vision archive them
3. Manually archive if needed:
   mv requirements/{old-requirement} requirements/archive/
4. Keep only 3 active requirements
```

### Lost Context Across Sessions

```markdown
**Problem:** Can't remember what I was working on

**Solution:**
1. Read requirements/*/recovery.md for all active requirements
2. Each recovery.md has:
   - Current status
   - Last updated date
   - Next steps
3. Resume from most recent
```

### Tests Taking Too Long

```markdown
**Problem:** Full test suite takes 20+ minutes

**Solution:**
1. Use markers for targeted testing:
   - `uv run pytest -m "sqlite or aiosqlite"` (fastest)
   - `uv run pytest -m asyncpg` (PostgreSQL only)
   - `uv run pytest -m "oracle18c or oracle23ai"` (Oracle only)
2. Test specific files: `uv run pytest tests/integration/test_filters.py`
3. Only run full suite in CI or before final quality gate
```

## Documentation Standards (Full)

**CRITICAL: Documentation is technical reference material, not marketing content.**

### ✅ ALWAYS DO

- **Factual descriptions** - State what something does, not how good it is
- **Objective characteristics** - Performance metrics, compatibility lists, feature sets
- **Technical constraints** - Limitations, requirements, edge cases
- **Code examples** - Working examples with proper context
- **Error conditions** - What can go wrong and how to handle it

### ❌ NEVER DO

- **Prescriptive guidance** - "recommended", "best for", "ideal for", "should use"
- **Subjective opinions** - "better", "worse", "perfect", "excellent"
- **Marketing language** - "pros/cons", "trade-offs", persuasive comparisons
- **Emoji indicators** - ✅/❌ for recommendations (OK for code correctness examples only)
- **Use case prescription** - "Choose X when...", "Use Y for..."

### Examples

**❌ Bad (Marketing):**
```markdown
## When to Use Obstore

Obstore is **ideal** for:
- ✅ High-performance workloads
- ✅ Latency-sensitive applications

**Trade-offs:**
- ✅ Pros: 10x faster
- ❌ Cons: Fewer backends
```

**✅ Good (Technical):**
```markdown
## Obstore Backend

Rust-based storage implementation.

**Characteristics:**
- Implementation: Native Rust via PyO3 bindings
- Async support: Native async/await
- Supported backends: S3, GCS, Azure, local, memory
- Benchmarks: [link to objective performance data]
```

### Code Correctness Indicators

✅/❌ are ONLY acceptable when showing code correctness:

**✅ Acceptable:**
```markdown
# ✅ Correct - uses async context manager
async with session.begin():
    await repository.create(data)

# ❌ Wrong - missing await
async with session.begin():
    repository.create(data)  # Bug!
```

**❌ Not acceptable:**
```markdown
# ✅ Recommended approach
use_obstore_backend()

# ❌ Slower alternative
use_fsspec_backend()
```

## Summary

This agent system provides:

✅ **Structured workflow** - Plan → Implement → Test → Review
✅ **Quality enforcement** - AGENTS.md standards mandatory
✅ **Research-grounded** - Guides + Context7 + WebSearch
✅ **Session continuity** - Workspace enables resume
✅ **Cleanup protocol** - Mandatory workspace management
✅ **MCP tool integration** - zen.planner, zen.debug, zen.consensus, Context7
✅ **Multi-database support** - All 8+ backends tested
✅ **Multi-framework support** - Litestar, FastAPI, Flask, Sanic, Starlette

All agents work together to ensure high-quality, well-tested, well-documented code that works across all supported databases and frameworks.
