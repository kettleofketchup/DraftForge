from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import toml
except ImportError:
    toml = None
from alive_progress import alive_bar
from invoke.collection import Collection
from invoke.tasks import task

import paths

from .utils import crun, get_version

ns_docker = Collection("docker")
ns_docker_frontend = Collection("frontend")
ns_docker_backend = Collection("backend")
ns_docker_nginx = Collection("nginx")

ns_docker_all = Collection("all")
ns_docker.add_collection(ns_docker_frontend)
ns_docker.add_collection(ns_docker_nginx)
ns_docker.add_collection(ns_docker_backend)
ns_docker.add_collection(ns_docker_all)


def docker_build(
    c,
    image: str,
    version: str,
    dockerfile: Path,
    context: Path,
    target: str = "runtime",
    extra_contexts: dict[str, Path] | None = None,
    push: bool = False,
    use_cache: bool = True,
):
    """Build Docker image using buildx with registry caching.

    Args:
        c: Invoke context
        image: Full image name (e.g., ghcr.io/user/repo/image)
        version: Image version tag
        dockerfile: Path to Dockerfile
        context: Build context path
        target: Dockerfile target stage
        extra_contexts: Additional build contexts
        push: If True, push to registry. If False, load locally.
        use_cache: If True, use registry caching. Set False for local-only builds.
    """
    img_str = f"{image}:{version}"
    cache_ref = f"{image}:buildcache"

    extra_ctx_args = ""
    if extra_contexts:
        extra_ctx_args = " ".join(
            f"--build-context {name}={path}" for name, path in extra_contexts.items()
        )

    # Use --push for registry, --load for local Docker daemon
    output_flag = "--push" if push else "--load"

    # Cache args - only use registry cache when pushing or explicitly enabled
    # --cache-from is safe even if cache doesn't exist (buildx handles gracefully)
    cache_args = ""
    if use_cache or push:
        cache_args = (
            f"--cache-from type=registry,ref={cache_ref} "
            f"--cache-to type=registry,ref={cache_ref},mode=max "
        )

    cmd = (
        f"docker buildx build "
        f"--file {str(dockerfile)} "
        f"--target {target} "
        f"--tag {img_str} "
        f"--tag {image}:latest "
        f"{cache_args}"
        f"{extra_ctx_args} "
        f"{output_flag} "
        f"{str(context)}"
    )
    crun(c, cmd)


def docker_pull(c, image: str, version: str, dockerfile: Path, context: Path):

    cmd = f"docker pull {image}:{version}"
    cmd2 = f"docker pull {image}:latest"
    crun(c, cmd)
    crun(c, cmd2)


def tag_latest(c, image: str, version: str):
    """Push image to registry (legacy - buildx now handles this)."""
    # With buildx --push, images are already pushed during build
    # This is kept for compatibility but may not be needed
    crun(c, f"docker push {image}:{version}")
    crun(c, f"docker push {image}:latest")


def run_docker(c, image: str, version: str):
    crun(c, f"docker run -it {image}:{version}", pty=True)


# returns version, tag, dockerFilePath, Docker Context Path
def get_frontend():
    return (
        get_version(),
        paths.FRONTEND_TAG,
        paths.FRONTEND_DOCKERFILE_PATH,
        paths.FRONTEND_PATH,
    )


def get_cypress():
    return (
        get_version(),
        paths.CYPRESS_TAG,
        paths.CYPRESS_DOCKERFILE_PATH,
        paths.FRONTEND_PATH,
    )


def get_frontend_dev():
    return (
        get_version(),
        paths.FRONTEND_DEV_TAG,
        paths.FRONTEND_DOCKERFILE_PATH,
        paths.FRONTEND_PATH,
    )


def get_backend():
    return (
        get_version(),
        paths.BACKEND_TAG,
        paths.BACKEND_DOCKERFILE_PATH,
        paths.PROJECT_PATH,
    )


def get_backend_dev():
    return (
        get_version(),
        paths.BACKEND_DEV_TAG,
        paths.BACKEND_DOCKERFILE_PATH,
        paths.PROJECT_PATH,
    )


def get_nginx():
    return get_version(), paths.NGINX_TAG, paths.NGINX_DOCKERFILE_PATH, paths.NGINX_PATH


@task
def docker_frontend_build_prod(c, push=False):
    """Build production frontend image only."""
    version, image, dockerfile, context = get_frontend()
    # Pass docs directory as additional build context for assets
    extra_contexts = {"docs": paths.PROJECT_PATH / "docs"}
    docker_build(
        c, image, version, dockerfile, context, "runtime", extra_contexts, push=push
    )


@task
def docker_frontend_build_dev(c, push=False):
    """Build dev frontend image with Cypress/Playwright (slower)."""
    version, image, dockerfile, context = get_frontend_dev()
    docker_build(c, image, version, dockerfile, context, "runtime-dev", push=push)


@task
def docker_frontend_build(c, push=False):
    """Build both production and dev frontend images."""
    docker_frontend_build_prod(c, push=push)
    docker_frontend_build_dev(c, push=push)


@task
def docker_backend_build(c, push=False):
    """Build both production and dev backend images."""
    version, image, dockerfile, context = get_backend()
    docker_build(c, image, version, dockerfile, context, push=push)
    version, image, dockerfile, context = get_backend_dev()
    docker_build(c, image, version, dockerfile, context, "runtime-dev", push=push)


@task
def docker_nginx_build(c, push=False):
    """Build nginx image."""
    version, image, dockerfile, context = get_nginx()
    docker_build(c, image, version, dockerfile, context, push=push)


@task
def docker_nginx_pull(c):
    version, image, dockerfile, context = get_nginx()
    docker_pull(c, image, version, dockerfile, context)


@task
def docker_backend_pull(c):
    version, image, dockerfile, context = get_backend()
    docker_pull(c, image, version, dockerfile, context)
    version, image, dockerfile, context = get_backend_dev()
    docker_pull(c, image, version, dockerfile, context)


@task
def docker_frontend_pull(c):
    version, image, dockerfile, context = get_frontend()
    docker_pull(c, image, version, dockerfile, context)
    # frontend-dev needed for Cypress tests in CI
    version, image, dockerfile, context = get_frontend_dev()
    docker_pull(c, image, version, dockerfile, context)


@task
def docker_frontend_push(c):
    """Build and push frontend images to registry."""
    docker_frontend_build(c, push=True)


@task
def docker_backend_push(c):
    """Build and push backend images to registry."""
    docker_backend_build(c, push=True)


@task
def docker_nginx_push(c):
    """Build and push nginx image to registry."""
    docker_nginx_build(c, push=True)


@task
def docker_backend_run(c):
    version = get_version()
    image = paths.BACKEND_TAG
    run_docker(c, image, version)


@task
def docker_frontend_run(c):
    version, image, dockerfile, context = get_frontend()
    run_docker(c, image, version)


@task
def docker_backend_run(c):
    version, image, dockerfile, context = get_backend()
    run_docker(c, image, version)


@task
def docker_nginx_run(c):
    version, image, dockerfile, context = get_nginx()
    run_docker(c, image, version)


@task()
def docker_build_all(c, push=False):
    """Build all Docker images (backend, frontend, nginx).

    Args:
        push: If True, push to registry after building.
    """
    funcs = [
        lambda: docker_backend_build(c, push=push),
        lambda: docker_frontend_build(c, push=push),
        lambda: docker_nginx_build(c, push=push),
    ]
    with alive_bar(total=3, title="Building Images") as bar:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(func): func for func in funcs}
            for future in as_completed(futures):
                future.result()
                bar()


@task
def docker_push_all(c):
    """Build and push all Docker images to registry."""
    docker_build_all(c, push=True)


@task
def docker_pull_all(c):
    funcs = [docker_backend_pull, docker_frontend_pull, docker_nginx_pull]
    with alive_bar(total=3, title="Pulling Images") as bar:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(func, c): func for func in funcs}
            for future in as_completed(futures):
                future.result()
                bar()


ns_docker_frontend.add_task(docker_frontend_build, "build")
ns_docker_frontend.add_task(docker_frontend_build_prod, "build-prod")
ns_docker_frontend.add_task(docker_frontend_build_dev, "build-dev")
ns_docker_backend.add_task(docker_backend_build, "build")
ns_docker_nginx.add_task(docker_nginx_build, "build")

ns_docker_backend.add_task(docker_backend_push, "push")
ns_docker_frontend.add_task(docker_frontend_push, "push")
ns_docker_nginx.add_task(docker_nginx_push, "push")

ns_docker_backend.add_task(docker_backend_run, "run")
ns_docker_frontend.add_task(docker_frontend_run, "run")
ns_docker_nginx.add_task(docker_nginx_run, "run")

ns_docker_all.add_task(docker_pull_all, "pull")
ns_docker_all.add_task(docker_build_all, "build")
ns_docker_all.add_task(docker_push_all, "push")
ns_docker_all.add_task(docker_build_all, "build")
