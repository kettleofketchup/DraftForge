# Logging Cleanup and CI Optimization Design

**Date:** 2026-01-11
**Branch:** feature/bracket-match-linking (or new branch)

## Overview

Two related improvements:
1. Clean up noisy startup warnings by unifying output under Python's logging system
2. Fix GitHub Cypress workflow caching to reduce CI run times

## Part 1: Logging Cleanup

### Problem

Startup output is cluttered with:
- Print statements like `Created: Draft Not Started (key: draft_not_started)`
- DEBUG-level logs like `DEBUG:root:Building draft rounds with style: snake`
- Repeated Redis/cacheops warnings when Redis isn't reachable

### Solution

1. **Convert print statements to logging** in `backend/tests/helpers/tournament_config.py`:
   - `print(f"Created: {tournament.name}...")` → `logger.info(...)`
   - `print(f"\nCreated {len(created)} test tournaments")` → `logger.info(...)`

2. **Configure logging levels** in `backend/backend/settings.py`:
   - Keep DEBUG level available for development
   - Set specific noisy loggers to INFO by default
   - Add `LOG_LEVEL` environment variable for override

3. **Show Redis warning once** using Python's warning filter:
   ```python
   import warnings
   warnings.filterwarnings('once', message='.*cacheops cache is unreachable.*')
   ```

## Part 2: GitHub Workflow Cache Fixes

### Problem

The Cypress workflow re-downloads dependencies every run because:
- Docker buildx cache key uses `github.sha` (changes every commit)
- `npm install` runs even when node_modules could be cached
- `poetry install` runs even when .venv could be cached

### Solution

1. **Fix Docker buildx cache key**:
   ```yaml
   # Before (never hits)
   key: buildx-${{ runner.os }}-${{ github.sha }}

   # After (hits when Dockerfiles unchanged)
   key: buildx-${{ runner.os }}-${{ hashFiles('docker/**/Dockerfile*', 'backend/requirements*.txt', 'frontend/package-lock.json') }}
   ```

2. **Cache node_modules directly**:
   ```yaml
   - name: Cache node_modules
     id: node-cache
     uses: actions/cache@v3
     with:
       path: frontend/node_modules
       key: node-modules-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}
   ```

3. **Conditional npm install**:
   ```yaml
   - name: Install frontend dependencies
     if: steps.node-cache.outputs.cache-hit != 'true'
     run: cd frontend && npm install
   ```

4. **Conditional poetry install**:
   ```yaml
   - name: Install Python dependencies
     if: steps.poetry-cache.outputs.cache-hit != 'true'
     run: poetry install --no-interaction --no-ansi
   ```

## Files to Modify

| File | Changes |
|------|---------|
| `backend/backend/settings.py` | Add warning filter, configure logger levels, add `LOG_LEVEL` env var |
| `backend/tests/helpers/tournament_config.py` | Convert prints to `logger.info()` |
| `.github/workflows/cypress.yml` | Fix cache keys, add node_modules cache, conditional installs |

## Cache Key Strategy

| Cache | Key Based On |
|-------|--------------|
| Poetry venv | `poetry.lock` hash (already correct) |
| node_modules | `package-lock.json` hash |
| Cypress binary | `package-lock.json` hash (already correct) |
| Docker layers | Dockerfiles + requirements.txt + package-lock.json hashes |

## Testing

**Logging changes:**
- Run `inv db.populate.all` locally
- Verify cleaner output without DEBUG spam
- Verify Redis warning appears only once

**Workflow changes:**
- Push a commit, note CI time
- Push another commit without changing dependencies
- Second run should be noticeably faster (cache hits)
