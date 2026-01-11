# Installation

## Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- Poetry (Python package manager)

## Clone the Repository

```bash
git clone https://github.com/kettleofketchup/dota_tournament.git
cd dota_tournament
```

## Python Environment Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies with Poetry
poetry install
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
source .venv/bin/activate

# Pull pre-built images
inv docker.all.pull

# Or build locally
inv docker.all.build
```

## Database Setup

```bash
source .venv/bin/activate
inv db.migrate.all     # Run migrations for all environments
# Or for specific environment:
# inv db.migrate.dev   # Dev only (default)
# inv db.migrate.test  # Test only
# inv db.migrate.prod  # Prod only
```

## Verify Installation

```bash
source .venv/bin/activate
inv dev.debug
```

Visit https://localhost to verify the application is running.
