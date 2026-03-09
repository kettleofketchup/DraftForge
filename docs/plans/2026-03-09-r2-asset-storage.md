# R2 Asset Storage Migration

**Date**: 2026-03-09
**Branch**: `feature/r2-assets`

## Problem

Demo videos (74MB), GIFs (3.1MB), and site snapshots (1.6MB) are committed to git,
bloating the repository. Every demo re-recording adds large binary diffs.

## Solution

Move all demo assets to Cloudflare R2 storage, served via `https://assets.kettle.sh/draftforge/`.

## Design

### Storage Layout

```
R2 bucket: dfdemos
├── draftforge/
│   ├── videos/          # .webm demo videos
│   ├── gifs/            # .gif preview clips
│   └── site_snapshots/  # .png screenshots
```

Public URL pattern: `https://assets.kettle.sh/draftforge/{videos,gifs,site_snapshots}/{filename}`

### Upload Tool

`rclone sync` with the pre-configured `draftforge:` remote (stored in `~/.config/rclone/rclone.conf`).

### Just Module: `just/r2.just`

- `_r2-auth` — private pre-function, validates `draftforge:` remote exists
- `r2::upload` — syncs all 3 asset directories
- `r2::upload::videos` / `r2::upload::gifs` / `r2::upload::snapshots` — individual syncs

### Demo Workflow (updated)

1. Record demos (`just demo::*`)
2. Trim + GIFs (`just demo::trim`, `just demo::gifs`)
3. Upload to R2 (`just r2::upload`)

Assets stay in `docs/assets/` locally as staging area but are gitignored.

### URL Migration

All markdown references changed from relative paths to absolute R2 URLs:
- `assets/videos/x.webm` → `https://assets.kettle.sh/draftforge/videos/x.webm`
- `../assets/gifs/x.gif` → `https://assets.kettle.sh/draftforge/gifs/x.gif`
- `../../assets/site_snapshots/x.png` → `https://assets.kettle.sh/draftforge/site_snapshots/x.png`

### Git Cleanup

- Add asset directories to `.gitignore`
- `git rm --cached` to untrack (keeps local files)

## Implementation Steps

1. Upload current assets to R2
2. Create `just/r2.just` module
3. Replace all asset URLs in markdown
4. Update `.gitignore`
5. `git rm --cached` tracked assets
6. Update demo workflow docs
