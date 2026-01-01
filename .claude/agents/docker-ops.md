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

| File | Purpose | Command |
|------|---------|---------|
| `docker-compose.debug.yaml` | Development | `inv dev.debug` |
| `docker-compose.test.yaml` | Testing | `inv dev.test` |
| `docker-compose.prod.yaml` | Production | `inv dev.prod` |
| `docker-compose.release.yaml` | Release | `inv dev.release` |

## Services Configuration

### Frontend Service

```yaml
frontend:
  image: ghcr.io/kettleofketchup/dtx_website/frontend-dev:latest
  volumes:
    - ./frontend/:/app              # Hot reload
    - /app/node_modules/.vite/      # Exclude vite cache
    - /app/.react-router/           # Exclude router cache
```

**Health Check**:
```bash
docker logs frontend
# Should show Vite dev server running on port 3000
```

### Backend Service

```yaml
backend:
  image: ghcr.io/kettleofketchup/dtx_website/backend-dev:latest
  depends_on:
    - redis
  volumes:
    - ./backend/:/app/backend
```

**Health Check**:
```bash
docker logs backend
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
docker exec redis redis-cli ping
# Should return: PONG
```

### Nginx Service

```yaml
nginx:
  image: ghcr.io/kettleofketchup/dtx_website/nginx:latest
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/default.template.conf:/etc/nginx/templates/
    - ./nginx/data/ssl/:/etc/letsencrypt/live/dota.kettle.sh/
```

**Health Check**:
```bash
curl -k https://localhost
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
# Check container status
docker ps -a

# View logs
docker logs <container_name>

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
docker exec backend ping redis
```

### Volume Permission Issues

```bash
# Check volume mounts
docker inspect <container> --format '{{.Mounts}}'

# Fix permissions (common issue)
sudo chown -R $USER:$USER ./backend/.redis_data
sudo chown -R $USER:$USER ./nginx/data/
```

### Image Issues

```bash
# List images
docker images | grep dtx_website

# Remove old images
docker image prune -f

# Force rebuild
inv docker.all.build
```

## Common Operations

### Start Fresh

```bash
source .venv/bin/activate

# Stop and remove everything
docker compose -f docker/docker-compose.debug.yaml down -v

# Rebuild and start
inv docker.all.build
inv dev.debug
```

### Check All Services

```bash
# Status of all containers
docker ps

# Expected output:
# frontend  - Up, healthy
# backend   - Up, healthy
# redis     - Up, healthy
# nginx     - Up, ports 80,443
```

### View Logs

```bash
# All services
docker compose -f docker/docker-compose.debug.yaml logs -f

# Specific service
docker logs -f frontend
docker logs -f backend
docker logs -f nginx
```

## Agent Collaboration

### With inv-runner Agent

When invoke docker tasks are modified:
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

### Production (Let's Encrypt)

```bash
inv prod.certbot
```

Certificates stored in `nginx/data/certbot/configs/`.

## Image Registry

All images hosted at:
```
ghcr.io/kettleofketchup/dtx_website/
├── frontend:latest
├── frontend-dev:latest
├── backend:latest
├── backend-dev:latest
└── nginx:latest
```

Version tags match `pyproject.toml` version.
