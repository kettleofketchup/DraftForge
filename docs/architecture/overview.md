# Architecture Overview

DraftForge follows a modern full-stack architecture with clear separation of concerns.

## High-Level Architecture

```mermaid
flowchart TD
    Client([Client Browser])

    Client --> Nginx

    subgraph Docker["Docker Environment"]
        Nginx[Nginx<br/>:80, :443]

        Nginx -->|/api/*| Backend
        Nginx -->|/*| Frontend

        Frontend[Frontend<br/>React + TypeScript<br/>:3000]
        Backend[Backend<br/>Django REST<br/>:8000]

        Backend --> Redis[(Redis<br/>Cache<br/>:6379)]
        Backend --> SQLite[(SQLite<br/>Database)]
    end
```

## Request Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant N as Nginx
    participant F as Frontend
    participant B as Backend
    participant R as Redis
    participant DB as SQLite

    C->>N: HTTPS Request

    alt Static/SPA Route (/*)
        N->>F: Proxy Request
        F-->>N: React SPA
        N-->>C: HTML/JS/CSS
    else API Route (/api/*)
        N->>B: Proxy Request
        B->>R: Check Cache
        alt Cache Hit
            R-->>B: Cached Data
        else Cache Miss
            B->>DB: Query
            DB-->>B: Result
            B->>R: Store in Cache
        end
        B-->>N: JSON Response
        N-->>C: API Response
    end
```

## Data Flow

```mermaid
flowchart LR
    subgraph Frontend["Frontend (React)"]
        UI[UI Components]
        Zustand[(Zustand Store)]
        Zod{Zod Validation}

        UI --> Zustand
        Zustand --> UI
    end

    subgraph Backend["Backend (Django)"]
        DRF[DRF ViewSets]
        Serializers[Serializers]
        Models[Models]
        Cacheops[django-cacheops]
    end

    subgraph Data["Data Layer"]
        Redis[(Redis Cache)]
        SQLite[(SQLite DB)]
    end

    subgraph External["External APIs"]
        Discord[Discord OAuth]
        Steam[Steam API]
    end

    UI -->|fetch /api/*| DRF
    DRF --> Serializers
    Serializers --> Models
    Models --> Cacheops
    Cacheops --> Redis
    Cacheops --> SQLite
    DRF -->|JSON| Zod
    Zod -->|Validated Data| Zustand

    DRF <--> Discord
    DRF <--> Steam
```

## Service Responsibilities

### Nginx
- SSL termination
- Reverse proxy routing
- Static file serving
- Load balancing (future)

### Frontend
- Server-Side Rendering (SSR) with React Router 7
- User interface rendering
- Client-side state management
- API consumption

#### SSR API Configuration

The frontend uses SSR (Server-Side Rendering) for improved performance and SEO. During SSR, API requests are made from the Node.js server inside the Docker container, not from the browser.

**How it works:**

- **Client-side (browser):** Uses `/api` - proxied by Nginx to the backend
- **Server-side (SSR):** Uses `SSR_API_URL` environment variable

**Configuration:**

The `SSR_API_URL` environment variable controls where the frontend server makes API requests during SSR:

| Deployment | SSR_API_URL |
|------------|-------------|
| Docker Compose (default) | `http://backend:8000/api` |
| Kubernetes | `http://backend-service:8000/api` |
| External backend | `https://api.example.com/api` |
| Local dev (no Docker) | `http://localhost:8000/api` |

Set in your environment file (e.g., `docker/.env.dev`):

```bash
SSR_API_URL=http://backend:8000/api
```

!!! note "Docker Service Names"
    In Docker Compose, services can reach each other by service name. The `backend` in the URL refers to the backend service defined in `docker-compose.yaml`.

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
