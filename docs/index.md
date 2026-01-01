# Dota Tournament Website Documentation

Welcome to the DTX Website documentation. This site helps manage DTX, a Dota2 gaming organization.

## Overview

The DTX Website is a full-stack application for managing:

- **Users** - Discord-integrated user management
- **Tournaments** - Tournament creation and management
- **Teams** - Team organization and drafting
- **Games** - Match tracking and statistics

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React, TypeScript, Vite, TailwindCSS, Shadcn UI |
| **Backend** | Django, Django REST Framework, Redis |
| **Infrastructure** | Docker, Nginx, GitHub Container Registry |
| **Authentication** | Discord OAuth via django-social-auth |

## Quick Links

- [Installation Guide](getting-started/installation.md)
- [Quick Start](getting-started/quick-start.md)
- [Docker Architecture](architecture/docker.md)
- [Invoke Tasks](development/invoke-tasks.md)

## Project Structure

```
website/
├── backend/          # Django REST API
├── frontend/         # React + TypeScript + Vite
├── docker/           # Docker Compose configurations
├── nginx/            # Nginx reverse proxy config
├── scripts/          # Invoke task scripts
└── docs/             # This documentation
```
