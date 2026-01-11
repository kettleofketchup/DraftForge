# Logging Cleanup and CI Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clean up noisy startup warnings and fix GitHub CI caching to reduce build times.

**Architecture:** Convert print statements to logging, configure Python warnings filter for cacheops, and fix GitHub Actions cache keys so dependencies don't re-download every run.

**Tech Stack:** Python logging, Python warnings module, GitHub Actions cache

---

## Task 1: Add warnings filter for cacheops Redis warning

**Files:**
- Modify: `backend/backend/settings.py:24-29`

**Step 1: Add warnings import and filter after the logging import**

Find this code at line 24:
```python
import logging

from paths import DEV_DB_PATH, PROD_DB_PATH, TEST_DB_PATH

log = logging.getLogger(__name__)
```

Replace with:
```python
import logging
import warnings

from paths import DEV_DB_PATH, PROD_DB_PATH, TEST_DB_PATH

# Show cacheops Redis connection warning only once (not on every import)
warnings.filterwarnings("once", message=r".*cacheops cache is unreachable.*")

log = logging.getLogger(__name__)
```

**Step 2: Remove duplicate logging import**

Find this at line 73:
```python
import logging
```

Delete this line (it's a duplicate).

**Step 3: Test the change**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && DISABLE_CACHE=true python -c "from backend.backend import settings; from backend.backend import settings"`

Expected: No errors, warning filter applied

**Step 4: Commit**

```bash
git add backend/backend/settings.py
git commit -m "fix: show cacheops warning only once and remove duplicate import"
```

---

## Task 2: Configure logging to reduce DEBUG noise

**Files:**
- Modify: `backend/backend/settings.py:88-91`

**Step 1: Replace basic logging config with configurable version**

Find this code at lines 88-91:
```python
DEBUG = env_bool("DEBUG")

if DEBUG or TEST:
    logging.basicConfig(level=logging.DEBUG)
```

Replace with:
```python
DEBUG = env_bool("DEBUG")

# Configure logging - default to INFO, allow override via LOG_LEVEL env var
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)

# Quiet down noisy loggers unless explicitly debugging
if _log_level != "DEBUG":
    logging.getLogger("app.models").setLevel(logging.INFO)
    logging.getLogger("app.functions.tournament").setLevel(logging.INFO)
```

**Step 2: Test the change**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && DISABLE_CACHE=true python -c "from backend.backend import settings; print('Log level configured')"`

Expected: "Log level configured" with no DEBUG spam

**Step 3: Test with explicit DEBUG level**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && DISABLE_CACHE=true LOG_LEVEL=DEBUG python -c "from backend.backend import settings; print('DEBUG enabled')"`

Expected: Should still work, DEBUG level active

**Step 4: Commit**

```bash
git add backend/backend/settings.py
git commit -m "fix: configure logging with LOG_LEVEL env var, default to INFO"
```

---

## Task 3: Convert print statements to logging in tournament_config.py

**Files:**
- Modify: `backend/tests/helpers/tournament_config.py:372-384`

**Step 1: Replace print statements with logger calls**

Find this code at lines 371-384:
```python
    if existing.exists() and not force:
        print("Test tournaments exist. Use force=True to recreate.")
        return list(existing)

    if force:
        existing.delete()

    created = []
    for config in TEST_TOURNAMENTS:
        tournament = config.create()
        created.append(tournament)
        print(f"Created: {tournament.name} (key: {config.key})")

    print(f"\nCreated {len(created)} test tournaments")
```

Replace with:
```python
    if existing.exists() and not force:
        log.info("Test tournaments exist. Use force=True to recreate.")
        return list(existing)

    if force:
        existing.delete()

    created = []
    for config in TEST_TOURNAMENTS:
        tournament = config.create()
        created.append(tournament)
        log.info(f"Created: {tournament.name} (key: {config.key})")

    log.info(f"Created {len(created)} test tournaments")
```

**Step 2: Test the change**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && DISABLE_CACHE=true python -c "from tests.helpers.tournament_config import populate_test_tournaments; print('Import OK')"`

Expected: "Import OK" with no errors

**Step 3: Commit**

```bash
git add backend/tests/helpers/tournament_config.py
git commit -m "refactor: convert print statements to logging in tournament_config"
```

---

## Task 4: Fix GitHub workflow - add node_modules cache with ID

**Files:**
- Modify: `.github/workflows/cypress.yml:55-70`

**Step 1: Add ID to Poetry cache step**

Find this at lines 55-61:
```yaml
    - name: Cache Poetry dependencies
      uses: actions/cache@v3
      with:
        path: .venv
        key: poetry-${{ runner.os }}-${{ hashFiles('poetry.lock') }}
        restore-keys: |
          poetry-${{ runner.os }}-
```

Replace with:
```yaml
    - name: Cache Poetry dependencies
      id: poetry-cache
      uses: actions/cache@v3
      with:
        path: .venv
        key: poetry-${{ runner.os }}-${{ hashFiles('poetry.lock') }}
        restore-keys: |
          poetry-${{ runner.os }}-
```

**Step 2: Make poetry install conditional**

Find this at lines 63-65:
```yaml
    - name: Install Python dependencies
      run: |
        poetry install --no-interaction --no-ansi
```

Replace with:
```yaml
    - name: Install Python dependencies
      if: steps.poetry-cache.outputs.cache-hit != 'true'
      run: |
        poetry install --no-interaction --no-ansi
```

**Step 3: Add node_modules cache before npm install**

Find this at lines 67-70:
```yaml
    - name: Install frontend dependencies
      run: |
        cd frontend
        npm install
```

Replace with:
```yaml
    - name: Cache node_modules
      id: node-cache
      uses: actions/cache@v3
      with:
        path: frontend/node_modules
        key: node-modules-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}

    - name: Install frontend dependencies
      if: steps.node-cache.outputs.cache-hit != 'true'
      run: |
        cd frontend
        npm install
```

**Step 4: Commit**

```bash
git add .github/workflows/cypress.yml
git commit -m "ci: add node_modules cache and conditional installs"
```

---

## Task 5: Fix Docker buildx cache key

**Files:**
- Modify: `.github/workflows/cypress.yml:92-98`

**Step 1: Fix the buildx cache key to use file hashes instead of SHA**

Find this at lines 92-98:
```yaml
    - name: Cache Docker layers
      uses: actions/cache@v3
      with:
        path: /tmp/.buildx-cache
        key: buildx-${{ runner.os }}-${{ github.sha }}
        restore-keys: |
          buildx-${{ runner.os }}-
```

Replace with:
```yaml
    - name: Cache Docker layers
      uses: actions/cache@v3
      with:
        path: /tmp/.buildx-cache
        key: buildx-${{ runner.os }}-${{ hashFiles('backend/Dockerfile', 'frontend/Dockerfile', 'nginx/Dockerfile', 'backend/requirements.txt', 'frontend/package-lock.json') }}
        restore-keys: |
          buildx-${{ runner.os }}-
```

**Step 2: Commit**

```bash
git add .github/workflows/cypress.yml
git commit -m "ci: fix Docker cache key to use file hashes instead of commit SHA"
```

---

## Task 6: Test locally and verify cleaner output

**Step 1: Run populate command and check output**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && inv db.populate.all 2>&1 | head -50`

Expected:
- No "DEBUG:root:" spam
- Tournament creation messages should appear as "INFO:tests.helpers.tournament_config:Created: ..."
- Redis warning (if any) should appear only once

**Step 2: Verify LOG_LEVEL override works**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && LOG_LEVEL=DEBUG inv db.populate.all 2>&1 | head -20`

Expected: DEBUG messages should now appear

**Step 3: Final verification complete**

All local changes verified. CI changes will be validated on next push to main.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add cacheops warning filter | `settings.py` |
| 2 | Configure logging with LOG_LEVEL | `settings.py` |
| 3 | Convert prints to logging | `tournament_config.py` |
| 4 | Add node_modules cache, conditional installs | `cypress.yml` |
| 5 | Fix Docker cache key | `cypress.yml` |
| 6 | Test and verify | (testing only) |
