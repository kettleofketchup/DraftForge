# Demo Video Recording Guidelines

## When to Re-record Demos

After editing files in these paths, **run the corresponding demo task**:

| Path Pattern | Run This | Videos Updated |
|--------------|----------|----------------|
| `frontend/app/components/herodraft/**` | `just demo::herodraft` | captain1_herodraft, captain2_herodraft, herodraft_chat.webp |
| `frontend/app/components/draft/**` | `just demo::shuffle` and `just demo::snake` | shuffle_draft, snake_draft |
| `frontend/app/components/bracket/**` | `just demo::herodraft` | (bracket is entry point to hero draft) |

## Action Required

When you complete edits to these components that affect visual appearance:

1. Run the appropriate demo command
2. Upload to R2: `just r2::upload`

**Do not ask the user** - just run the demo recording if the changes are visual.

## Demo Commands

| Command | Description |
|---------|-------------|
| `just demo::herodraft` | Record hero draft demo (resets demo data first) |
| `just demo::shuffle` | Record shuffle draft demo |
| `just demo::snake` | Record snake draft demo |
| `just demo::all` | Record all demos in parallel |
| `just demo::gifs` | Convert videos to GIF previews |
| `just demo::trim` | Trim initial white screen from videos |
| `just demo::clips` | Cut short animated WebP clips (`herodraft_chat.webp`) from the raw recordings |
| `just demo::clean` | Clean demo output directories |
| `just r2::upload` | Upload all assets to Cloudflare R2 |

## Prerequisites

Before running demos:

1. Test environment must be running: `just test::up`
2. Test data must be populated: `just db::populate::all`

## Test Data

Demos use isolated tournament data that resets automatically:

| Tournament | Key | Used By |
|------------|-----|---------|
| Demo HeroDraft Tournament | `demo_herodraft` | herodraft demo |
| Demo Captain Draft Tournament | `demo_captaindraft` | shuffle, snake demos |

## How It Works

Each demo command:

1. Resets the demo tournament via `/api/tests/demo/<key>/reset/`
2. Runs Playwright demo tests headless inside the frontend Docker container
3. Saves videos locally to `docs/assets/videos/`
4. Upload to R2 via `just r2::upload`

## GitHub Workflow

For official releases, use the manual GitHub workflow:

1. Go to **Actions** > **Record Demo Videos**
2. Select which demo to record (all, herodraft, shuffle, snake)
3. Choose **Create PR** to review before merging (recommended)
4. Click **Run workflow**

The workflow uses cached dependencies from CI for faster execution.

## Video Outputs

Videos are saved to `https://assets.kettle.sh/draftforge/videos/`:

- `captain1_herodraft.webm` - Hero draft from Team Alpha captain's view
- `captain2_herodraft.webm` - Hero draft from Team Beta captain's view
- `shuffle_draft.webm` - Shuffle (MMR-balanced) draft
- `snake_draft.webm` - Snake draft

GIFs are saved to `https://assets.kettle.sh/draftforge/gifs/` with the same names (`.gif` extension).

Animated WebP clips also go to `gifs/`:

- `herodraft_chat.webp` - ~5s of both captains side by side: one member per team suggests a hero and writes in team chat, each captain answers their own team, and neither sees the other's messages

The herodraft spec logs in one non-captain per team (unrecorded) for this. Before the clip both captains press Enter to open chat and trade `/all` lines. The spec writes the clip window to `herodraft.demo.yaml` (`chat_clip`), and `just demo::herodraft` cuts the clip after recording. Clips are cut from `frontend/demo-results/videos/`, not the trimmed copies in `docs/assets/videos/`.
