# Draftforge

A tournament management platform for Dota 2 gaming communities.

**Website:** [dota.kettle.sh](https://dota.kettle.sh)

**Documentation:** [kettleofketchup.github.io/draftforge](https://kettleofketchup.github.io/draftforge/)

## Features

- **Tournament Management** - Create and manage tournaments with customizable formats
- **Draft System** - Three draft styles: Snake, Normal, and Shuffle (MMR-balanced)
- **Hero Draft** - Captains Mode hero picking with real-time WebSocket updates
- **Team Organization** - Captain-based team drafting with live updates
- **Match Tracking** - Steam API integration for match statistics
- **League System** - Player ratings and league standings
- **Discord Integration** - OAuth authentication and bot notifications

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| Frontend | React 19, TypeScript, Vite, TailwindCSS, Radix UI |
| Backend | Django 5, Django REST Framework, Daphne (WebSockets), Celery |
| Infrastructure | Docker, Nginx, Redis (caching) |
| Auth | Discord OAuth |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/kettleofketchup/draftforge.git
cd draftforge

# Setup Python environment
python -m venv .venv
source .venv/bin/activate
poetry install

# Start development environment
inv dev.debug
```

## Development

Full development documentation is available at [kettleofketchup.github.io/draftforge](https://kettleofketchup.github.io/draftforge/), including:

- [Installation Guide](https://kettleofketchup.github.io/draftforge/getting-started/installation/)
- [Quick Start](https://kettleofketchup.github.io/draftforge/getting-started/quick-start/)
- [Architecture Overview](https://kettleofketchup.github.io/draftforge/architecture/overview/)
- [API Reference](https://kettleofketchup.github.io/draftforge/api/endpoints/)

### Docker Images

Build and push Docker images using Invoke tasks:

```bash
# Build all images
inv docker.all.build

# Push all images
inv docker.all.push
```

Version is managed in `pyproject.toml`.

### GitHub Container Registry

Authenticate to push images:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```
