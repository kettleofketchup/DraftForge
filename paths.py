from pathlib import Path
PROJECT_PATH: Path = Path('.')
FRONTEND_PATH: Path = PROJECT_PATH / 'frontend'
BACKEND_PATH: Path = PROJECT_PATH / 'backend'
FRONTEND_DOCKERFILE_PATH: Path = FRONTEND_PATH / 'Dockerfile'
BACKEND_DOCKERFILE_PATH: Path = BACKEND_PATH / 'Dockerfile'
PYPROJECT_PATH =  PROJECT_PATH / "pyproject.toml"

FRONTEND_TAG: str = "frontend"
BACKEND_TAG: str = "backend"
REGISTRY: str = "ghcr.io/dtx-dota/website"
BACKEND_TAG: str = f"{REGISTRY}/backend"
FRONTEND_TAG: str = f"{REGISTRY}/frontend"