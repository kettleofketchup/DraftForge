# Demo Video Recording Guidelines

## When to Re-record Demos

After editing files in these paths, **run the corresponding demo task**:

| Path Pattern | Run This | Videos Updated |
|--------------|----------|----------------|
| `frontend/app/components/herodraft/**` | `inv demo.herodraft` | captain1_herodraft, captain2_herodraft |
| `frontend/app/components/draft/**` | `inv demo.shuffle` and `inv demo.snake` | shuffle_draft, snake_draft |
| `frontend/app/components/bracket/**` | `inv demo.herodraft` | (bracket is entry point to hero draft) |

## Action Required

When you complete edits to these components that affect visual appearance:

1. Run the appropriate demo command
2. Commit the updated videos with the code changes

**Do not ask the user** - just run the demo recording if the changes are visual.

## Demo Commands

| Command | Description |
|---------|-------------|
| `inv demo.herodraft` | Record hero draft demo (resets demo data first) |
| `inv demo.shuffle` | Record shuffle draft demo |
| `inv demo.snake` | Record snake draft demo |
| `inv demo.all` | Record all demos in parallel |
| `inv demo.gifs` | Convert videos to GIF previews |
| `inv demo.trim` | Trim initial white screen from videos |
| `inv demo.clean` | Clean demo output directories |

## Prerequisites

Before running demos:

1. Test environment must be running: `inv dev.test`
2. Test data must be populated: `inv db.populate.all`

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
3. Copies videos to `docs/assets/videos/`

## GitHub Workflow

For official releases, use the manual GitHub workflow:

1. Go to **Actions** > **Record Demo Videos**
2. Select which demo to record (all, herodraft, shuffle, snake)
3. Choose **Create PR** to review before merging (recommended)
4. Click **Run workflow**

The workflow uses cached dependencies from CI for faster execution.

## Video Outputs

Videos are saved to `docs/assets/videos/`:

- `captain1_herodraft.webm` - Hero draft from Team Alpha captain's view
- `captain2_herodraft.webm` - Hero draft from Team Beta captain's view
- `shuffle_draft.webm` - Shuffle (MMR-balanced) draft
- `snake_draft.webm` - Snake draft

GIFs are saved to `docs/assets/gifs/` with the same names (`.gif` extension).
