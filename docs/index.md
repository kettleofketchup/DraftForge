# DraftForge Documentation

Welcome to the DraftForge documentation. DraftForge is a platform for managing Dota 2 tournaments, teams, and competitive gaming.

## Overview

DraftForge is a full-stack application for managing:

- **Users** - Discord-integrated user management
- **Tournaments** - Tournament creation and management
- **Teams** - Team organization and drafting
- **Games** - Match tracking and statistics

## Screenshots

<div class="grid cards" markdown>

| Home | Tournaments |
|------|-------------|
| ![Home](assets/site_snapshots/home.png) | ![Tournaments](assets/site_snapshots/tournaments.png) |

| Tournament Detail | Player Draft |
|--------------------|--------------|
| ![Tournament](assets/site_snapshots/tournament.png) | ![Draft](assets/site_snapshots/draft.png) |

| Bracket | Hero Draft |
|---------|------------|
| ![Bracket](assets/site_snapshots/bracket.png) | ![Hero Draft](assets/site_snapshots/HeroDraft.png) |

</div>

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React, TypeScript, Vite, TailwindCSS, Shadcn UI |
| **Backend** | Django, Django REST Framework, Redis |
| **Infrastructure** | Docker, Nginx, GitHub Container Registry |
| **Observability** | structlog, OpenTelemetry (opt-in) |
| **Authentication** | Discord OAuth via django-social-auth |

## Quick Links

- [Installation Guide](getting-started/installation.md)
- [Quick Start](getting-started/quick-start.md)
- [Docker Architecture](architecture/docker.md)
- [Just Commands](development/just-commands.md)

## Features

- [Draft System](features/draft.md) - Snake, Normal, and Shuffle draft modes
- [Hero Draft](features/herodraft.md) - Captains Mode hero banning and picking
- [CSV Import](features/csv-import.md) - Bulk-add users via CSV with team assignment and conflict detection

## Demo Recordings

| Captain 1 - HeroDraft | Captain 2 - HeroDraft |
|-----------------------|-----------------------|
| ![Captain 1](assets/gifs/captain1_herodraft.gif) | ![Captain 2](assets/gifs/captain2_herodraft.gif) |
| [Full Video](assets/videos/captain1_herodraft.webm) | [Full Video](assets/videos/captain2_herodraft.webm) |

| Shuffle Draft | Snake Draft |
|---------------|-------------|
| ![Shuffle Draft](assets/gifs/shuffle_draft.gif) | ![Snake Draft](assets/gifs/snake_draft.gif) |
| [Full Video](assets/videos/shuffle_draft.webm) | [Full Video](assets/videos/snake_draft.webm) |

| CSV Import |
|------------|
| ![CSV Import](assets/gifs/csv_import.gif) |
| [Full Video](assets/videos/csv_import.webm) |

### Generate Demos Locally

```bash
# Record all demos and generate GIFs
just demo::quick

# Or record individually
just demo::shuffle     # Shuffle draft
just demo::snake       # Snake draft
just demo::herodraft   # Hero draft with bracket
just demo::csv         # CSV import with bracket
```

See [Just Commands](development/just-commands.md#demo-tasks) for all options.

## Project Structure

```
website/
├── backend/          # Django REST API
├── frontend/         # React + TypeScript + Vite
├── docker/           # Docker Compose configurations
├── nginx/            # Nginx reverse proxy config
├── scripts/          # Utility scripts
└── docs/             # This documentation
```
