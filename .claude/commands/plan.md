Invoke the Planner agent to create a comprehensive requirement workspace.

**What this does:**
- Creates `requirements/{feature-slug}/` directory structure
- Writes detailed PRD with database and framework considerations
- Creates actionable task list
- Generates recovery guide for resuming work
- Identifies research questions for Expert

**Usage:**
```
/plan Add vector search support for PostgreSQL and Oracle
```

**The Planner will:**
1. Analyze the requirement and existing codebase patterns
2. Create workspace: `requirements/vector-search-support/`
3. Write comprehensive PRD covering:
   - All 8+ database backends
   - Framework integrations (Litestar, FastAPI, Flask, Sanic, Starlette)
   - Async/sync considerations (unasyncd workflow)
   - Testing strategy with pytest markers
   - Documentation requirements
4. Create task breakdown by phase
5. Write recovery guide for any agent to resume

**Output Structure:**
```
requirements/vector-search-support/
├── prd.md          # Product Requirements Document
├── tasks.md        # Phase-by-phase task checklist
├── recovery.md     # Recovery guide for resuming work
├── progress.md     # Running log (created by agents)
├── research/       # Expert research findings
└── tmp/            # Temporary files (cleaned by Docs & Vision)
```

**After planning, run:**
- `/implement` to build the feature
- Or invoke Expert agent directly for implementation
