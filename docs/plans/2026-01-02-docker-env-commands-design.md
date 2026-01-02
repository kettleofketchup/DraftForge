# Docker Environment Commands Design

## Overview

Add consistent docker compose commands across dev, test, and prod environments with a clean namespace structure.

## Command Structure

### New Namespaces

| Namespace | Compose File | Env File |
|-----------|--------------|----------|
| `dev` | `docker-compose.debug.yaml` | `.env.dev` |
| `test` | `docker-compose.test.yaml` | `.env.test` |
| `prod` | `docker-compose.prod.yaml` | `.env.prod` |

### Commands Per Environment

Each namespace gets the following commands:

| Command | Docker Compose Equivalent | Description |
|---------|---------------------------|-------------|
| `up` | `docker compose up` | Start services |
| `down` | `docker compose down --remove-orphans` | Stop and remove containers |
| `logs` | `docker compose logs -f` | Follow logs |
| `ps` | `docker compose ps` | List running containers |
| `restart` | `docker compose restart` | Restart services |
| `stop` | `docker compose stop` | Stop without removing |
| `build` | `docker compose build` | Build images |
| `pull` | `docker compose pull` | Pull images |
| `top` | `docker compose top` | Display running processes |
| `exec` | `docker compose exec` | Execute command in container |

### Example Usage

```bash
inv dev.up
inv dev.logs
inv dev.down

inv test.up
inv test.ps
inv test.down

inv prod.up
inv prod.restart
inv prod.down
```

## Implementation

### Helper Functions

Reusable functions in `tasks.py` that take a `compose_file: Path` parameter:

```python
def docker_compose_up(c, compose_file: Path): ...
def docker_compose_down(c, compose_file: Path): ...
def docker_compose_logs(c, compose_file: Path): ...
def docker_compose_ps(c, compose_file: Path): ...
def docker_compose_restart(c, compose_file: Path): ...
def docker_compose_stop(c, compose_file: Path): ...
def docker_compose_build(c, compose_file: Path): ...
def docker_compose_pull(c, compose_file: Path): ...
def docker_compose_top(c, compose_file: Path): ...
def docker_compose_exec(c, compose_file: Path, service: str, cmd: str): ...
```

### Namespace Structure

- Use existing `ns_dev` and `ns_prod` collections
- Create new `ns_test` collection
- Existing commands (`dev.debug`, `dev.live`, etc.) are preserved

## Documentation Updates

Update `.claude/CLAUDE.md` with new commands in the "Common Invoke Commands" section.
