# Docs Invoke Commands and GitHub Pages Deployment

## Overview

Add invoke commands for building MkDocs documentation and create a GitHub Action to automatically deploy docs to GitHub Pages on push to main.

## Components

### 1. Invoke Commands

**New file:** `scripts/docs.py`

| Command | Description |
|---------|-------------|
| `inv docs.serve` | Start local dev server with hot reload (port 8000) |
| `inv docs.build` | Build static site to `site/` directory |

**Integration:** Add `ns_docs` collection to `tasks.py`

### 2. GitHub Action

**New file:** `.github/workflows/docs.yml`

**Trigger:** Push to `main` branch (changes to `docs/**` or `mkdocs.yml`)

**Steps:**
1. Checkout repository
2. Set up Python 3.11
3. Install MkDocs dependencies (`mkdocs-material`)
4. Build docs with `mkdocs build`
5. Deploy to GitHub Pages using `actions/deploy-pages`

**Resulting URL:** `https://kettleofketchup.github.io/dota_tournament/`

**GitHub Pages setup required:**
- Repository Settings → Pages → Source: "GitHub Actions"

### 3. Agent Updates

**Files to update:**

| File | Changes |
|------|---------|
| `.claude/agents/inv-runner.md` | Add `docs.serve` and `docs.build` commands |
| `.claude/agents/mkdocs-documentation.md` | Replace manual mkdocs commands with invoke equivalents |
| `CLAUDE.md` | Add docs commands to "Common Invoke Commands" section |

## Files Changed

- `scripts/docs.py` (new)
- `.github/workflows/docs.yml` (new)
- `tasks.py` (modify - add docs collection)
- `.claude/agents/inv-runner.md` (modify)
- `.claude/agents/mkdocs-documentation.md` (modify)
- `CLAUDE.md` (modify)
