# Requirements Workspace

This directory contains structured workspaces for implementing Advanced Alchemy features and bug fixes using the multi-agent development system.

## Quick Start

### Planning a New Feature

```bash
# Use /plan command to create workspace
/plan add native vector search support for PostgreSQL and Oracle

# Creates requirements/vector-search/ with:
# - prd.md (Product Requirements Document)
# - tasks.md (Implementation checklist)
# - recovery.md (Session resume guide)
# - research/ (Planning findings)
# - tmp/ (Temporary files)
```

### Implementing

```bash
# Use /implement command to build feature
/implement vector-search

# Expert agent:
# - Reads PRD and tasks
# - Implements code following AGENTS.md standards
# - Runs targeted tests with markers
# - Updates workspace
```

### Testing

```bash
# Use /test command to create comprehensive tests
/test vector-search

# Testing agent:
# - Creates unit and integration tests
# - Tests all 8+ database backends with markers
# - Covers edge cases
# - Updates workspace
```

### Review & Completion

```bash
# Use /review command for quality gate and cleanup
/review vector-search

# Docs & Vision agent:
# - Phase 1: Documentation (Sphinx, guides, changelog)
# - Phase 2: Quality gate (lint, tests, standards)
# - Phase 3: Cleanup (archive, remove tmp/)
```

## Workspace Structure

### Active Requirements

Keep up to 3 active requirements in the root of this directory:

```
requirements/
├── theme-color-alignment/  # Active requirement (Week 1 Priority: CRITICAL UX)
│   ├── prd.md              # Product Requirements Document
│   ├── tasks.md            # Task checklist (100+ tasks, 9 phases)
│   ├── recovery.md         # Resume instructions
│   ├── progress.md         # Running log of changes
│   ├── research/           # Research findings
│   │   └── .gitkeep
│   └── tmp/                # Temporary files (cleaned on review)
│       └── .gitkeep
├── alembic-cli-alignment/  # Active requirement (Week 1 Priority: HIGHEST)
│   ├── prd.md              # Product Requirements Document
│   ├── tasks.md            # Task checklist (69 tasks, 8 phases)
│   ├── recovery.md         # Resume instructions
│   ├── progress.md         # Running log of changes
│   ├── research/           # Research findings
│   │   └── .gitkeep
│   └── tmp/                # Temporary files (cleaned on review)
│       └── .gitkeep
├── updated-at-timestamp-fix/  # Bug fix (Week 1 Priority)
│   ├── prd.md              # Product Requirements Document
│   ├── tasks.md            # Task checklist (100+ tasks, 6 phases)
│   ├── recovery.md         # Resume instructions
│   ├── progress.md         # Running log of changes
│   ├── research/           # Research findings
│   │   └── .gitkeep
│   └── tmp/                # Temporary files (cleaned on review)
│       └── .gitkeep
└── vector-search/          # Example active requirement
```

### Archived Requirements

Completed requirements are archived by Docs & Vision agent:

```
requirements/archive/
├── full-text-search/        # Completed 2025-10-09
├── jsonb-support/           # Completed 2025-10-08
└── connection-pool-fix/     # Completed 2025-10-07
```

## File Descriptions

### prd.md (Product Requirements Document)

Comprehensive specification created by Planner agent:

- Feature overview and goals
- Database-specific considerations (all 8+ backends)
- Framework integration requirements (Litestar, FastAPI, Flask, Sanic, Starlette)
- Async/sync considerations (unasyncd workflow)
- Testing strategy
- Acceptance criteria

### tasks.md (Task Checklist)

Phase-by-phase task breakdown:

- [ ] Phase 1: Research
- [ ] Phase 2: Core Implementation
- [ ] Phase 3: Framework Integration
- [ ] Phase 4: Testing
- [ ] Phase 5: Documentation

Updated by all agents as work progresses.

### recovery.md (Session Resume Guide)

Enables resuming work across conversations:

- Current status
- Last updated date
- Files modified
- Next steps for each agent
- Context for resuming work

### progress.md (Running Log)

Append-only log of all changes:

- Date and time of each session
- Agent name and actions taken
- Decisions made with rationale
- Files modified
- Next steps

### research/ (Research Findings)

Research outputs from Planner and Expert:

- `plan.md` - Detailed implementation plan
- `database-patterns.md` - Database-specific notes
- `framework-integration.md` - Framework patterns
- `consensus.md` - Multi-model consensus findings

### tmp/ (Temporary Files)

Working files that are cleaned up on review:

- Debug logs
- Planning notes
- Scratch work
- Experimental code

**IMPORTANT**: All tmp/ directories are deleted during `/review` cleanup phase.

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────┐
│  1. PLANNING (/plan)                                        │
│  Agent: Planner                                             │
│  Output: requirements/{slug}/ with PRD, tasks, recovery     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  2. IMPLEMENTATION (/implement)                             │
│  Agent: Expert                                              │
│  Output: Code in advanced_alchemy/, updated workspace       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  3. TESTING (/test)                                         │
│  Agent: Testing                                             │
│  Output: Tests in tests/, updated workspace                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  4. REVIEW (/review)                                        │
│  Agent: Docs & Vision                                       │
│  Phase 1: Documentation (Sphinx, guides, changelog)         │
│  Phase 2: Quality gate (must pass!)                         │
│  Phase 3: Cleanup (archive, remove tmp/)                    │
│  Output: Documented, tested, archived feature               │
└─────────────────────────────────────────────────────────────┘
```

## Resuming Work

If context is lost or conversation resets:

```bash
# 1. Find active requirements
ls -la requirements/

# 2. Read recovery guide for each
cat requirements/*/recovery.md

# 3. Check task progress
cat requirements/{slug}/tasks.md

# 4. Review PRD for context
cat requirements/{slug}/prd.md

# 5. Resume from last checkpoint
# recovery.md has clear next steps for the appropriate agent
```

## Cleanup Protocol

**Docs & Vision agent MUST clean up after every `/review`:**

1. **Remove all tmp/ directories:**

   ```bash
   find requirements/*/tmp -type d -exec rm -rf {} +
   ```

2. **Archive completed requirement:**

   ```bash
   mv requirements/{requirement} requirements/archive/{requirement}
   echo "Archived on $(date)" > requirements/archive/{requirement}/ARCHIVED.txt
   ```

3. **Keep only last 3 active requirements:**
   - If more than 3 active, archive oldest

## Best Practices

### For All Agents

- **Always update workspace files** - Keep recovery.md and tasks.md current
- **Use descriptive slugs** - `vector-search` not `feature1`
- **Document as you go** - Don't wait until the end
- **Test incrementally** - Verify as you build

### For Planner

- **Research first** - Consult guides, Context7, WebSearch
- **Be comprehensive** - Cover all 8+ databases and 5 frameworks
- **Clear acceptance criteria** - Explicit success metrics
- **Detailed recovery guide** - Enable easy handoff

### For Expert

- **Read the plan** - Don't skip PRD and research/plan.md
- **Follow AGENTS.md** - Stringified type hints, edit _async.py only, etc.
- **Test with markers** - Avoid 20+ minute test runs
- **Update recovery.md** - Document progress for Testing agent

### For Testing

- **Test all backends** - Use pytest markers for all 8+ databases
- **Function-based tests** - No class-based tests
- **Edge cases** - Empty, None, errors, concurrency, bulk operations
- **Update recovery.md** - Document completion for Docs & Vision

### For Docs & Vision

- **Don't skip quality gate** - BLOCK if standards not met
- **MANDATORY cleanup** - Always archive and clean tmp/
- **Complete documentation** - Sphinx, guides, changelog
- **Final verification** - One last `make lint && make test`

## Active Requirements

<!-- Updated by agents after /review -->

Currently active requirements:

1. **theme-color-alignment** (Priority: CRITICAL UX - Week 1)
   - Status: Phase 1 Complete ✅, Ready for Phase 2
   - Issue: #554
   - Branch: docs/theme-color-alignment
   - PR Title: docs: align code block and UI themes with Advanced Alchemy branding
   - Goal: Fix unreadable code blocks in light mode, align with brand colors
   - Estimated: 10-14 days (2 weeks)
   - Next: Expert agent to research Shibuya theme and test accessible-pygments

2. **alembic-cli-alignment** (Priority: HIGHEST - Week 1)
   - Status: Phase 1 Complete ✅, Ready for Phase 2
   - Issue: #566
   - Goal: Complete Alembic 1.16.5 API parity (9 commands + 1 fix)
   - Estimated: 12.5 days (2.5 weeks)
   - Next: Expert agent to fix stamp command options

3. **updated-at-timestamp-fix** (Priority: HIGH - Week 1)
   - Status: Phase 1 In Progress (4/13 tasks)
   - Issue: #549
   - Goal: Fix `updated_at` not updating on record modifications
   - Root Cause: Faulty `has_changes()` check in listener
   - Estimated: 2-3 days
   - Next: Reproduce bug and git bisect to find regression commit

## Recent Completions

<!-- Updated by Docs & Vision agent after archiving -->

Recent archived requirements:

- _None yet_ (This is a fresh workspace!)

## See Also

- [.claude/AGENTS.md](../.claude/AGENTS.md) - Full agent coordination guide
- [AGENTS.md](../AGENTS.md) - Code quality standards and patterns
- [docs/guides/](../docs/guides/) - Implementation guides
- [.claude/agents/](../.claude/agents/) - Agent definitions
- [.claude/commands/](../.claude/commands/) - Slash command definitions
