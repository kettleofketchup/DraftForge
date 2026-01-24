from pathlib import Path

domains = ["dota.kettle.sh", "www.dota.kettle.sh"]


PROJECT_PATH: Path = Path(__file__).parent.absolute()
FRONTEND_PATH: Path = PROJECT_PATH / "frontend"
BACKEND_PATH: Path = PROJECT_PATH / "backend"
NGINX_PATH: Path = PROJECT_PATH / "nginx"
DOCKER_PATH: Path = PROJECT_PATH / "docker"

FRONTEND_DOCKERFILE_PATH: Path = FRONTEND_PATH / "Dockerfile"
CYPRESS_DOCKERFILE_PATH: Path = FRONTEND_PATH / "Dockerfile.cypress"

BACKEND_DOCKERFILE_PATH: Path = BACKEND_PATH / "Dockerfile"
NGINX_DOCKERFILE_PATH: Path = NGINX_PATH / "Dockerfile"

PYPROJECT_PATH = PROJECT_PATH / "pyproject.toml"
CERTBOT_DIR: Path = NGINX_PATH / "data" / "certbot"
CERTBOT_WEBROOT: Path = CERTBOT_DIR / "webroot"
CERTBOT_WORK: Path = CERTBOT_DIR / "work"
CERTBOT_CONFIGS: Path = CERTBOT_DIR / "configs"
CERTBOT_LOGS: Path = CERTBOT_DIR / "logs"

REGISTRY: str = "ghcr.io/kettleofketchup/draftforge"
BACKEND_TAG: str = f"{REGISTRY}/backend"
FRONTEND_TAG: str = f"{REGISTRY}/frontend"
NGINX_TAG: str = f"{REGISTRY}/nginx"
BACKEND_TAG: str = f"{REGISTRY}/backend"
FRONTEND_TAG: str = f"{REGISTRY}/frontend"
NGINX_target: str = f"{REGISTRY}/nginx"

BACKEND_DEV_TAG: str = f"{REGISTRY}/backend-dev"
FRONTEND_DEV_TAG: str = f"{REGISTRY}/frontend-dev"
FRONTEND_DEV_TARGET: str = f"runtime-dev"
CYPRESS_TAG: str = f"{REGISTRY}/cypress"
TEST_ENV_FILE: Path = DOCKER_PATH / ".env.test"


DEBUG_ENV_FILE: Path = DOCKER_PATH / ".env.dev"
PROD_ENV_FILE: Path = DOCKER_PATH / ".env.prod"
RELEASE_ENV_FILE: Path = DOCKER_PATH / ".env.release"
BACKEND_ENV_FILE: Path = BACKEND_PATH / ".env"

TEST_DB_PATH: Path = BACKEND_PATH / "test.db.sqlite3"
DEV_DB_PATH: Path = BACKEND_PATH / "dev.db.sqlite3"
PROD_DB_PATH: Path = BACKEND_PATH / "prod.db.sqlite3"


DOCKER_COMPOSE_DEBUG_PATH: Path = DOCKER_PATH / "docker-compose.debug.yaml"
DOCKER_COMPOSE_TEST_PATH: Path = DOCKER_PATH / "docker-compose.test.yaml"
DOCKER_COMPOSE_RELEASE_PATH: Path = DOCKER_PATH / "docker-compose.release.yaml"

DOCKER_COMPOSE_PROD_PATH: Path = DOCKER_PATH / "docker-compose.prod.yaml"

DOCKER_COMPOSE_DEBUG_M1_PATH: Path = DOCKER_PATH / "docker-compose.debug.m1.yaml"
