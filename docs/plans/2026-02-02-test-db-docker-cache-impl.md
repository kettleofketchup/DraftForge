# Test Database Docker Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a local Docker image caching system for test database that skips population when source files haven't changed.

**Architecture:** Hash relevant source files (models, migrations, populate scripts) → check if existing image has matching label → skip populate if match, otherwise rebuild. Separate commands for building (`docker::db::build`) and extracting (`db::reset-test`).

**Tech Stack:** Docker, Bash, Just command runner, GitHub Actions with extractions/setup-just

**Worktree:** `/home/kettle/git_repos/website/.worktrees/test-db-cache`

---

## Task 1: Create Hash Script

**Files:**
- Create: `scripts/hash-test-db-sources.sh`

**Step 1: Create the hash script**

```bash
#!/usr/bin/env bash
# Outputs SHA256 of all files that affect test DB content
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

find backend -type f \( \
    -path "backend/tests/populate.py" -o \
    -path "backend/tests/helpers/tournament_config.py" -o \
    -path "backend/app/management/commands/populate_*.py" -o \
    -path "backend/*/migrations/*.py" -o \
    -name "models.py" \
\) | sort | xargs cat | sha256sum | cut -d' ' -f1
```

**Step 2: Make it executable and test**

Run: `chmod +x scripts/hash-test-db-sources.sh && ./scripts/hash-test-db-sources.sh`
Expected: A 64-character SHA256 hash string

**Step 3: Commit**

```bash
git add scripts/hash-test-db-sources.sh
git commit -m "feat: add script to hash test DB source files"
```

---

## Task 2: Create Test DB Dockerfile

**Files:**
- Create: `docker/Dockerfile.test-db`

**Step 1: Create minimal Dockerfile**

```dockerfile
FROM busybox:latest
ARG CONTENT_HASH
LABEL org.draftforge.test-db.content-hash=${CONTENT_HASH}
COPY backend/test.db.sqlite3 /data/test.db.sqlite3
```

**Step 2: Commit**

```bash
git add docker/Dockerfile.test-db
git commit -m "feat: add minimal Dockerfile for test DB image"
```

---

## Task 3: Create Just Docker DB Module

**Files:**
- Create: `just/docker/db.just`
- Modify: `just/docker/mod.just`

**Step 1: Create db.just with build command**

```just
# Test database image commands
root := source_directory() / "../.."
image := "draftforge/test-db:latest"

[group('docker::db')]
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    HASH=$(./scripts/hash-test-db-sources.sh)
    EXISTING=$(docker inspect --format='{{{{.Config.Labels.org.draftforge.test-db.content-hash}}}}' {{image}} 2>/dev/null || echo "")

    if [[ "$HASH" == "$EXISTING" ]]; then
        echo "Test DB image up-to-date (hash: ${HASH:0:12}...)"
        exit 0
    fi

    echo "Hash changed, rebuilding test DB..."
    just db::populate::all
    docker build -f docker/Dockerfile.test-db \
        --build-arg CONTENT_HASH="$HASH" \
        -t {{image}} .
    echo "Built {{image}} (hash: ${HASH:0:12}...)"
```

Note: The `{{{{` is just's escape sequence for a literal `{{` in the output.

**Step 2: Add module to mod.just**

Add this line after the nginx module in `just/docker/mod.just`:

```just
mod db 'db.just'
```

**Step 3: Test the command appears**

Run: `just --list --list-submodules | grep docker::db`
Expected: Shows `docker::db::build`

**Step 4: Commit**

```bash
git add just/docker/db.just just/docker/mod.just
git commit -m "feat: add just docker::db::build command"
```

---

## Task 4: Add DB Reset Command

**Files:**
- Modify: `just/db/populate.just`

**Step 1: Add reset-test command to populate.just**

Add at the end of the file:

```just
[group('db')]
reset-test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    IMAGE="draftforge/test-db:latest"
    if ! docker image inspect "$IMAGE" &>/dev/null; then
        echo "No cached test-db image. Run 'just docker::db::build' first."
        exit 1
    fi

    echo "Extracting test database from cached image..."
    CONTAINER_NAME="test-db-extract-$$"
    docker create --name "$CONTAINER_NAME" "$IMAGE"
    docker cp "$CONTAINER_NAME:/data/test.db.sqlite3" backend/test.db.sqlite3
    docker rm "$CONTAINER_NAME"
    echo "Restored backend/test.db.sqlite3"
```

**Step 2: Test the command appears**

Run: `just --list --list-submodules | grep reset-test`
Expected: Shows `db::reset-test`

**Step 3: Commit**

```bash
git add just/db/populate.just
git commit -m "feat: add just db::reset-test command"
```

---

## Task 5: Update CI Workflow

**Files:**
- Modify: `.github/workflows/build-test-db.yml`

**Step 1: Replace workflow with just-based version**

```yaml
name: Build Test Database Image

on:
  push:
    branches: [main]
    paths:
      - 'backend/tests/populate.py'
      - 'backend/tests/helpers/tournament_config.py'
      - 'backend/app/management/commands/populate_*.py'
      - 'backend/**/migrations/*.py'
      - 'backend/**/models.py'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: kettleofketchup/draftforge/test-db

jobs:
  build-test-db:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Just
      uses: extractions/setup-just@v2

    - name: Login to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install Poetry
      uses: snok/install-poetry@v1
      with:
        version: '2.2.0'
        virtualenvs-create: true
        virtualenvs-in-project: true

    - name: Cache Poetry dependencies
      uses: actions/cache@v4
      with:
        path: .venv
        key: poetry-${{ runner.os }}-${{ hashFiles('poetry.lock') }}

    - name: Install Python dependencies
      run: poetry install --no-interaction --no-ansi

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Build backend image
      run: just docker::backend::build
      env:
        DOCKER_BUILDKIT: 1

    - name: Build test-db image
      run: just docker::db::build
      env:
        DOCKER_BUILDKIT: 1

    - name: Push to GHCR
      run: |
        docker tag draftforge/test-db:latest ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
        docker push ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

    - name: Output image info
      run: |
        echo "Test DB image pushed: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest"
        ls -lh backend/test.db.sqlite3
```

**Step 2: Commit**

```bash
git add .github/workflows/build-test-db.yml
git commit -m "refactor: use just for test-db CI workflow"
```

---

## Task 6: Update Documentation

**Files:**
- Modify: `.claude/CLAUDE.md` (add new commands to Quick Start / Common Just Commands sections)

**Step 1: Add documentation for new commands**

In the "Common Just Commands" section, add under the Docker Images subsection:

```markdown
# Test Database
just docker::db::build         # Build test-db image (skips if hash unchanged)
just db::reset-test            # Extract cached DB to backend/test.db.sqlite3
```

**Step 2: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: add test-db cache commands to CLAUDE.md"
```

---

## Task 7: Test Full Workflow Locally

**Step 1: Build the test-db image**

Run: `just docker::db::build`
Expected: Runs populate, builds image, outputs hash

**Step 2: Run again to verify caching**

Run: `just docker::db::build`
Expected: "Test DB image up-to-date (hash: ...)" - should be instant

**Step 3: Test reset**

Run: `rm backend/test.db.sqlite3 && just db::reset-test && ls -la backend/test.db.sqlite3`
Expected: File restored from cached image

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: any adjustments from local testing"
```
