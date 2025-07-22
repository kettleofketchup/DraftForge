from pathlib import Path

domains = ["dota.kettle.sh", "www.dota.kettle.sh"]

PROJECT_PATH: Path = Path(__file__).parent.absolute()
FRONTEND_PATH: Path = PROJECT_PATH / "frontend"
BACKEND_PATH: Path = PROJECT_PATH / "backend"
NGINX_PATH: Path = PROJECT_PATH / "nginx"

FRONTEND_DOCKERFILE_PATH: Path = FRONTEND_PATH / "Dockerfile"
BACKEND_DOCKERFILE_PATH: Path = BACKEND_PATH / "Dockerfile"
NGINX_DOCKERFILE_PATH: Path = NGINX_PATH / "Dockerfile"

PYPROJECT_PATH = PROJECT_PATH / "pyproject.toml"
CERTBOT_DIR: Path = NGINX_PATH / "data" / "certbot"
CERTBOT_WEBROOT: Path = CERTBOT_DIR / "webroot"
CERTBOT_WORK: Path = CERTBOT_DIR / "work"
CERTBOT_CONFIGS: Path = CERTBOT_DIR / "configs"
CERTBOT_LOGS: Path = CERTBOT_DIR / "logs"

REGISTRY: str = "ghcr.io/kettleofketchup/dtx_website"
BACKEND_TAG: str = f"{REGISTRY}/backend"
FRONTEND_TAG: str = f"{REGISTRY}/frontend"
NGINX_TAG: str = f"{REGISTRY}/nginx"
