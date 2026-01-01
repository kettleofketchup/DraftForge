# Architecture Overview

The DTX Website follows a modern full-stack architecture with clear separation of concerns.

## High-Level Architecture

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
│   React + TypeScript    │   │   Django REST Framework     │
│      Port: 3000         │   │        Port: 8000           │
└─────────────────────────┘   └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │          Redis              │
                              │     (Cache Layer)           │
                              │        Port: 6379           │
                              └─────────────────────────────┘
```

## Request Flow

1. **Client Request** → Nginx receives on port 80/443
2. **Routing**:
    - `/api/*` → Backend (Django)
    - `/*` → Frontend (React)
3. **Backend** → Queries Redis cache, then database
4. **Response** → Returns through Nginx to client

## Service Responsibilities

### Nginx
- SSL termination
- Reverse proxy routing
- Static file serving
- Load balancing (future)

### Frontend
- Single Page Application (SPA)
- User interface rendering
- Client-side state management
- API consumption

### Backend
- REST API endpoints
- Business logic
- Authentication (Discord OAuth)
- Database operations
- Steam API integration

### Redis
- Session storage
- Query caching (django-cacheops)
- Rate limiting data
