# Demo Video Recording System Design

**Date:** 2026-01-28
**Status:** Approved

## Overview

A system for recording, managing, and updating demo videos with:
- Isolated demo tournament data with reset endpoints
- Invoke tasks that run Playwright headless in Docker
- Manual GitHub workflow with caching
- Claude Code documentation for proactive demo updates

## 1. Demo Test Data

### New Tournaments

Created during `inv db.populate.all`:

| Tournament | Key | Purpose | Players |
|------------|-----|---------|---------|
| Demo HeroDraft Tournament | `demo_herodraft` | Hero draft videos | 2 teams with captains (Real Tournament users) |
| Demo Captain Draft Tournament | `demo_captaindraft` | Shuffle/Snake videos | 16 players (Real Tournament users), no teams |

### Reset API Endpoints

```
POST /api/tests/demo/demo_herodraft/reset/
POST /api/tests/demo/demo_captaindraft/reset/
```

| Key | What it resets |
|-----|----------------|
| `demo_herodraft` | HeroDraft state → `waiting_for_captains`, clear rounds/events |
| `demo_captaindraft` | Draft state → `pending`, clear all team assignments, reset captain selections |

### Population Changes

- Fetch Discord avatars for Real Tournament users during population
- Disable Discord avatar Celery worker in test environment
- Create `create_demo_tournaments()` in `backend/tests/populate.py`

## 2. Invoke Tasks

### Updated ns_demo Collection

| Command | Action |
|---------|--------|
| `inv demo.herodraft` | Reset `demo_herodraft` → run in frontend container (headless) |
| `inv demo.shuffle` | Reset `demo_captaindraft` → run shuffle demo in container |
| `inv demo.snake` | Reset `demo_captaindraft` → run snake demo in container |
| `inv demo.all` | Reset all → run all demos in parallel (3 workers) |
| `inv demo.gifs` | Convert videos to GIFs |
| `inv demo.clean` | Clean output directories |

### Execution Flow

```
inv demo.herodraft
    ├─► POST /api/tests/demo/demo_herodraft/reset/
    ├─► docker exec frontend npx playwright test \
    │       --config=playwright.demo.config.ts \
    │       --grep "herodraft" --headless
    └─► Copy videos to docs/assets/videos/
```

### Parallel Execution

```
inv demo.all
    ├─► Reset demo_herodraft (API call)
    ├─► Reset demo_captaindraft (API call)
    └─► docker exec frontend npx playwright test \
            --config=playwright.demo.config.ts \
            --workers=3 --headless
```

## 3. GitHub Workflow

### File: `.github/workflows/record-demos.yml`

**Trigger:** Manual (`workflow_dispatch`)

**Inputs:**
- `demo`: choice (all, herodraft, shuffle, snake)
- `create_pr`: boolean (default: true)

**Caching:** Reuses all caches from `playwright.yml`:
- Poetry dependencies (`poetry-${{ runner.os }}-${{ hashFiles('poetry.lock') }}`)
- Node modules (`node-modules-${{ runner.os }}-${{ hashFiles('...') }}`)
- Playwright browsers (`playwright-${{ runner.os }}-${{ version }}`)
- Docker layers (`buildx-${{ runner.os }}-${{ hashFiles('...') }}`)

**Output:** Creates PR with updated videos or commits directly to main.

### Workflow Steps

1. Checkout code
2. Setup Python, Node.js, Poetry (with caching)
3. Install dependencies (cache-aware)
4. Setup Playwright browsers (with caching)
5. Build Docker images (with layer caching)
6. Populate test database
7. Start test services
8. Wait for services to be ready
9. Record selected demo(s)
10. Convert to GIFs
11. Create PR or commit directly
12. Cleanup

## 4. Claude Code Documentation

### Files

- `docs/ai/demo/index.md` - Full guidelines
- `.claude/CLAUDE.md` - Reference to guidelines

### Trigger Mappings

After editing UI components, Claude runs demo recording automatically:

| Path Pattern | Command |
|--------------|---------|
| `frontend/app/components/herodraft/**` | `inv demo.herodraft` |
| `frontend/app/components/draft/**` | `inv demo.shuffle` + `inv demo.snake` |
| `frontend/app/components/bracket/**` | `inv demo.herodraft` |

### Behavior

Claude should **run the demo recording** (not just remind the user) when visual changes are made to these components.

## 5. Backend Changes

### Celery Worker Guard

```python
# In Discord avatar fetch task
if settings.TEST_ENVIRONMENT:
    logger.info("Skipping Discord avatar fetch in test environment")
    return
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `backend/tests/populate.py` | Add `create_demo_tournaments()`, fetch Discord avatars |
| `backend/tests/test_demo.py` | Add reset endpoints for demo tournaments |
| `backend/tests/urls.py` | Register demo reset endpoints |
| `backend/app/tasks.py` | Add test environment guard for avatar fetch |
| `scripts/tests.py` | Update demo tasks to use Docker + reset |
| `.github/workflows/record-demos.yml` | New workflow file |
| `docs/ai/demo/index.md` | New documentation |
| `.claude/CLAUDE.md` | Add reference to demo docs |

## Implementation Order

1. **Backend:** Demo tournament data + reset endpoints
2. **Backend:** Celery worker test environment guard
3. **Invoke:** Update demo tasks for Docker execution + reset
4. **Workflow:** Create GitHub Actions workflow
5. **Docs:** Create Claude documentation + update CLAUDE.md
6. **Test:** Run full demo recording to verify
