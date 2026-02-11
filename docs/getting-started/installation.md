# Installation

## Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- Poetry (Python package manager)

## Clone the Repository

```bash
git clone https://github.com/kettleofketchup/draftforge.git
cd draftforge
```

## Environment Setup

```bash
# First-time setup (installs just, creates venv, installs deps)
./dev
```

## Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

## Environment Configuration

Copy the example environment files:

```bash
cp docker/.env.dev.example docker/.env.dev
cp docker/.env.test.example docker/.env.test
```

Configure the following in your `.env` files:

- `DJANGO_SECRET_KEY` - Django secret key
- `DISCORD_CLIENT_ID` - Discord OAuth app client ID
- `DISCORD_CLIENT_SECRET` - Discord OAuth app secret
- `STEAM_API_KEY` - Steam API key for Dota2 integration

## Docker Images

Pull or build the Docker images:

```bash
# Pull pre-built images
just docker::all-pull

# Or build locally
just docker::all-build
```

## Database Setup

```bash
just db::migrate::all     # Run migrations for all environments
# Or for specific environment:
# just db::migrate::dev   # Dev only (default)
# just db::migrate::test  # Test only
# just db::migrate::prod  # Prod only
```

## Verify Installation

```bash
just dev::debug
```

Visit https://localhost to verify the application is running.
