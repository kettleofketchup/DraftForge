# Docker Operations Agent

Expert agent for Docker setup, configuration, and troubleshooting in the DTX website project.

## When to Use This Agent

Use this agent when:

- **Verifying Docker setup** - Ensuring containers are running correctly
- **Troubleshooting containers** - Debugging Docker issues
- **Modifying Docker Compose** - Updating service configurations
- **Image management** - Building, pushing, pulling images
- **Environment configuration** - Managing `.env` files
- **Network issues** - Container communication problems

## Docker Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx                                │
│                    (Reverse Proxy)                           │
│                   Ports: 80, 443                             │
└─────────────────┬───────────────────────┬───────────────────┘
                  │                       │
                  ▼                       ▼
┌─────────────────────────┐   ┌─────────────────────────────┐
│       Frontend          │   │         Backend             │
│   React (Port 3000)     │   │   Django (Port 8000)        │
└─────────────────────────┘   └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │          Redis              │
                              │       (Port 6379)           │
                              └─────────────────────────────┘
```

## Docker Compose Files

| File | Purpose | Project | Command |
|------|---------|---------|---------|
| `docker-compose.debug.yaml` | Development | `df-dev` | `just dev::debug` |
| `docker-compose.test.yaml` (+ `slot.yaml`, `slot-offline.yaml` on N ≥ 1) | Testing | `df` (slot 0) / `df-sN` | `just test::upd` |
| `docker-compose.prod.yaml` | Production | `df` | `just prod::up` |
| `docker-compose.release.yaml` | Release | `df` | `just dev::release` |

## Test Stack Slots and Safety

Each worktree has its own test stack slot. Slot 0 is project `df` (containers
`frontend`, `backend`, `redis`, `nginx`, `https://localhost`); slot N ≥ 1 is `df-sN`
(containers suffixed `-sN`, `https://localhost:1N443`). The dev stack is `df-dev`
(containers suffixed `-dev`).

- Find stacks and ports with `just test::slots` (read-only) and this worktree's slot
  with `just test::slot`. Never assume a container named `backend` belongs to the
  worktree you are in.
- Run compose through `just test::compose <args>` (test, this worktree's slot) or
  `just test::compose --stack dev <args>` (dev). Never raw `docker compose`, which has
  no `-p` and can recreate another worktree's stack.
- Never run host-wide commands (`docker stop $(docker ps -aq)`, `docker system prune`):
  other worktrees' stacks share the host.
- Ask the user before `just test::slot-reap`, `just test::slot-claim` or
  `just test::slot-release --slot N`.

Full reference: `docs/development/test-stack-slots.md`.

## Services Configuration

### Frontend Service

```yaml
frontend:
  image: ghcr.io/kettleofketchup/draftforge/frontend-dev:latest
  volumes:
    - ./frontend/:/app              # Hot reload
    - /app/node_modules/.vite/      # Exclude vite cache
    - /app/.react-router/           # Exclude router cache
```

**Health Check**:
```bash
just test::compose logs --tail=50 frontend
# Should show Vite dev server running on port 3000
```

### Backend Service

```yaml
backend:
  image: ghcr.io/kettleofketchup/draftforge/backend-dev:latest
  depends_on:
    - redis
  volumes:
    - ./backend/:/app/backend
```

**Health Check**:
```bash
just test::compose logs --tail=50 backend
# Should show Django running on port 8000
```

### Redis Service

```yaml
redis:
  image: redis:8.2.1-alpine
  volumes:
    - ./backend/.redis_data:/data
```

**Health Check**:
```bash
just test::compose exec -T redis redis-cli ping
# Should return: PONG
```

### Nginx Service

```yaml
nginx:
  image: ghcr.io/kettleofketchup/draftforge/nginx:latest
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/default.template.conf:/etc/nginx/templates/
    - ./nginx/data/ssl/:/etc/letsencrypt/live/dota.kettle.sh/
```

**Health Check**:
```bash
just test::slot   # DF_BASE_URL for this worktree
curl -k <DF_BASE_URL>
# Should return HTML
```

## Environment Files

| File | Used By | Purpose |
|------|---------|---------|
| `docker/.env.dev` | debug | Development settings |
| `docker/.env.test` | test | Testing settings |
| `docker/.env.prod` | prod | Production settings |
| `docker/.env.release` | release | Release with VERSION |

### Required Environment Variables

```bash
# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True  # False in production

# Discord OAuth
DISCORD_CLIENT_ID=your-client-id
DISCORD_CLIENT_SECRET=your-client-secret

# Steam API
STEAM_API_KEY=your-steam-key

# Version (release only)
VERSION=1.0.0
```

## Troubleshooting Guide

### Container Won't Start

```bash
# Check container status for this worktree's stack
just test::compose ps -a

# View logs
just test::compose logs --tail=100 <service>

# Every df* stack on the host, with owners and ports
just test::slots

# Check for port conflicts
docker ps --format "{{.Names}}: {{.Ports}}"
```

### Network Issues

```bash
# List networks
docker network ls

# Inspect network
docker network inspect <network_name>

# Test container connectivity
just test::compose exec -T backend ping -c1 redis
```

### Volume Permission Issues

```bash
# Check volume mounts
docker inspect <container> --format '{{.Mounts}}'

# Fix permissions (common issue; ask the user, needs sudo)
sudo chown -R $USER:$USER ./backend/.redis_data*
sudo chown -R $USER:$USER ./nginx/data/

# Rootless podman: frontend (uid 100999) cannot write the worktree
setfacl -R -m u:100999:rwX -m d:u:100999:rwX <worktree>
just test::compose restart frontend nginx
```

### Image Issues

```bash
# List images
docker images | grep dota_tournament

# Remove old images
docker image prune -f

# Force rebuild (shared :latest images; other stacks pick them up on recreate)
just docker::all-build
```

## Common Operations

### Start Fresh

```bash
# Stop and remove this worktree's dev stack (df-dev only)
just test::compose --stack dev down -v

# Rebuild and start
just docker::all-build
just dev::debug
```

### Check All Services

```bash
# Status of this worktree's test stack
just test::compose ps

# Expected output (slot 0; slot N adds a -sN suffix and publishes only 1N443):
# frontend  - Up, healthy
# backend   - Up, healthy
# redis     - Up, healthy
# nginx     - Up, ports 80,443
```

### View Logs

```bash
# All services (dev)
just dev::logs

# Specific service (test stack of this worktree; add --stack dev for dev)
just test::compose logs -f frontend
just test::compose logs -f backend
just test::compose logs -f nginx
```

## Agent Collaboration

### With just recipes

When the docker recipes in `just/docker/` are modified:
- Ensure Docker Compose files are updated
- Verify image tags are correct
- Test the workflow

### With mkdocs-documentation Agent

When Docker architecture changes:
- Update `docs/architecture/docker.md`
- Update `docs/architecture/overview.md` if needed

## SSL Certificates

### Development (Self-Signed)

Located at `nginx/data/ssl/`:
- `cert.crt` - Certificate
- `cert.key` - Private key

### Production

The release stack reads its certificate from `nginx/data/certbot/configs/live/dota.kettle.sh/`
on the host. The repo has no tooling to issue or renew it.

## Image Registry

All images hosted at:
```
ghcr.io/kettleofketchup/draftforge/
├── frontend:latest
├── frontend-dev:latest
├── backend:latest
├── backend-dev:latest
└── nginx:latest
```

Version tags match `pyproject.toml` version.
