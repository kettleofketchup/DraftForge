# Docs Invoke Commands and GitHub Pages Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `inv docs.serve` and `inv docs.build` commands, create GitHub Action for auto-deploying docs to GitHub Pages on push to main.

**Architecture:** New `scripts/docs.py` module with two tasks in a `docs` collection. GitHub Action uses `actions/deploy-pages` for artifact-based deployment (no gh-pages branch needed).

**Tech Stack:** Python Invoke, MkDocs Material, GitHub Actions, GitHub Pages

---

### Task 1: Create docs.py invoke module

**Files:**
- Create: `scripts/docs.py`

**Step 1: Create the docs module**

```python
from invoke.collection import Collection
from invoke.tasks import task

import paths

ns_docs = Collection("docs")


@task
def serve(c):
    """Start MkDocs development server with hot reload."""
    with c.cd(paths.PROJECT_PATH):
        c.run("mkdocs serve", pty=True)


@task
def build(c):
    """Build static documentation site."""
    with c.cd(paths.PROJECT_PATH):
        c.run("mkdocs build")


ns_docs.add_task(serve, name="serve")
ns_docs.add_task(build, name="build")
```

**Step 2: Verify file created**

Run: `cat scripts/docs.py`
Expected: Shows the module content

**Step 3: Commit**

```bash
git add scripts/docs.py
git commit -m "feat: add docs invoke module with serve and build tasks"
```

---

### Task 2: Integrate docs collection into tasks.py

**Files:**
- Modify: `tasks.py:10-11` (add import)
- Modify: `tasks.py:38-39` (add collection)

**Step 1: Add import after line 10**

Add after `from scripts.tests import dev_test, ns_test`:
```python
from scripts.docs import ns_docs
```

**Step 2: Add collection after line 38**

Add after `ns.add_collection(ns_test, "test")`:
```python
ns.add_collection(ns_docs, "docs")
```

**Step 3: Verify tasks are available**

Run: `source .venv/bin/activate && inv --list | grep docs`
Expected:
```
  docs.build                Build static documentation site.
  docs.serve                Start MkDocs development server with hot reload.
```

**Step 4: Test docs.build command**

Run: `source .venv/bin/activate && inv docs.build`
Expected: MkDocs builds successfully, creates `site/` directory

**Step 5: Commit**

```bash
git add tasks.py
git commit -m "feat: integrate docs collection into invoke tasks"
```

---

### Task 3: Create GitHub Actions workflow for docs deployment

**Files:**
- Create: `.github/workflows/docs.yml`

**Step 1: Create the workflow file**

```yaml
name: Deploy Docs

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
      - 'mkdocs.yml'
      - '.github/workflows/docs.yml'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install MkDocs dependencies
        run: pip install mkdocs-material

      - name: Build docs
        run: mkdocs build

      - name: Setup Pages
        uses: actions/configure-pages@v4

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: './site'

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Step 2: Verify file created**

Run: `cat .github/workflows/docs.yml`
Expected: Shows the workflow content

**Step 3: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "ci: add GitHub Actions workflow for docs deployment to GitHub Pages"
```

---

### Task 4: Update inv-runner agent

**Files:**
- Modify: `.claude/agents/inv-runner.md`

**Step 1: Add docs namespace to Available Task Namespaces table (after line 62)**

Add row to the table:
```markdown
| `docs.*` | Documentation build commands |
```

**Step 2: Add Docs Commands section (after line 162, before Common Workflows)**

Add new section:
```markdown
## Docs Commands (`inv docs.*`)

```bash
inv docs.serve    # Start MkDocs dev server with hot reload (port 8000)
inv docs.build    # Build static documentation site to site/
```
```

**Step 3: Commit**

```bash
git add .claude/agents/inv-runner.md
git commit -m "docs: add docs.* commands to inv-runner agent"
```

---

### Task 5: Update mkdocs-documentation agent

**Files:**
- Modify: `.claude/agents/mkdocs-documentation.md:112-124`

**Step 1: Update Local Development section**

Replace the Local Development section (lines 112-124) with:
```markdown
## Local Development

```bash
source .venv/bin/activate

# Serve locally with hot reload
inv docs.serve

# Build static site
inv docs.build
```

Site available at http://127.0.0.1:8000

## GitHub Pages Deployment

Docs auto-deploy to GitHub Pages on push to `main` when changes are made to:
- `docs/**`
- `mkdocs.yml`

**URL:** https://kettleofketchup.github.io/dota_tournament/
```

**Step 2: Commit**

```bash
git add .claude/agents/mkdocs-documentation.md
git commit -m "docs: update mkdocs-documentation agent with invoke commands"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add docs commands to Common Invoke Commands section**

Find the "Common Invoke Commands" section and add after the Docker commands:
```markdown
# Docs
inv docs.serve         # Start MkDocs dev server
inv docs.build         # Build static docs site
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add docs commands to CLAUDE.md quick reference"
```

---

### Task 7: Add site/ to .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: Check if site/ is already ignored**

Run: `grep -n "^site" .gitignore || echo "Not found"`

**Step 2: Add site/ to .gitignore if not present**

Add to .gitignore:
```
site/
```

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add site/ to gitignore (MkDocs build output)"
```

---

### Task 8: Final verification

**Step 1: Verify all tasks are available**

Run: `source .venv/bin/activate && inv --list`
Expected: Shows `docs.build` and `docs.serve` in the list

**Step 2: Test docs.build**

Run: `source .venv/bin/activate && inv docs.build`
Expected: Builds successfully, creates `site/` directory

**Step 3: Verify site/ is ignored**

Run: `git status`
Expected: `site/` directory not shown as untracked

**Step 4: Summary of commits**

Run: `git log --oneline -8`
Expected: Shows all commits from this implementation
