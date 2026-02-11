import subprocess
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


def get_content_hash(service: str) -> str:
    """Get content hash for a Docker image service.

    Args:
        service: One of 'frontend', 'backend', 'nginx'
    """
    script = paths.PROJECT_PATH / "scripts" / "hash-docker-image.sh"
    result = subprocess.run(
        [str(script), service],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(paths.PROJECT_PATH),
    )
    return result.stdout.strip()


ns_docker = Collection("docker")
ns_docker_frontend = Collection("frontend")
ns_docker_backend = Collection("backend")
ns_docker_nginx = Collection("nginx")

ns_docker_all = Collection("all")
ns_docker_release = Collection("release")
ns_docker.add_collection(ns_docker_frontend)
ns_docker.add_collection(ns_docker_nginx)
ns_docker.add_collection(ns_docker_backend)
ns_docker.add_collection(ns_docker_all)
ns_docker.add_collection(ns_docker_release)


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
    content_hash: str | None = None,
    include_version_tag: bool = True,
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
        content_hash: If provided, also tag with this content hash.
        include_version_tag: If False, skip the version tag (for dev builds).
    """
    cache_ref = f"{image}:buildcache"

    tags = [f"--tag {image}:latest"]
    if include_version_tag:
        tags.append(f"--tag {image}:{version}")
    if content_hash:
        tags.append(f"--tag {image}:{content_hash}")
    tag_args = " ".join(tags)

    extra_ctx_args = ""
    if extra_contexts:
        extra_ctx_args = " ".join(
            f"--build-context {name}={path}" for name, path in extra_contexts.items()
        )

    # Use --push for registry, --load for local Docker daemon
    output_flag = "--push" if push else "--load"

    # Cache args:
    # --cache-from is safe even if cache doesn't exist (buildx handles gracefully)
    # --cache-to requires write permissions, so only use when pushing
    cache_args = ""
    if use_cache or push:
        cache_args = f"--cache-from type=registry,ref={cache_ref} "
    if push:
        cache_args += f"--cache-to type=registry,ref={cache_ref},mode=max "

    cmd = (
        f"docker buildx build "
        f"--file {str(dockerfile)} "
        f"--target {target} "
        f"{tag_args} "
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


def docker_pull_by_hash(c, image: str, service: str) -> bool:
    """Try to pull an image by content hash, falling back to latest.

    On success, tags the pulled image as :latest for docker compose compatibility.
    Returns True if pull succeeded, False otherwise.
    """
    content_hash = get_content_hash(service)
    short_hash = content_hash[:12]

    # Strategy 1: Try exact hash-tagged image
    print(f"Pulling {image} by hash ({short_hash}...)...")
    result = c.run(f"docker pull {image}:{content_hash}", warn=True, hide=True)
    if result and result.ok:
        print(f"  ✓ Found exact match for {image} (hash: {short_hash}...)")
        c.run(f"docker tag {image}:{content_hash} {image}:latest", hide=True)
        return True

    # Strategy 2: Fall back to latest
    print(f"  Hash not found, trying {image}:latest...")
    result = c.run(f"docker pull {image}:latest", warn=True, hide=True)
    if result and result.ok:
        print(f"  ✓ Pulled {image}:latest")
        return True

    print(f"  ✗ No image available for {image}")
    return False


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
def docker_frontend_build_prod(c, push=False, release=False):
    """Build production frontend image only."""
    version, image, dockerfile, context = get_frontend()
    content_hash = get_content_hash("frontend")
    # Pass docs directory as additional build context for assets
    extra_contexts = {"docs": paths.PROJECT_PATH / "docs"}
    docker_build(
        c,
        image,
        version,
        dockerfile,
        context,
        "runtime",
        extra_contexts,
        push=push,
        content_hash=content_hash,
        include_version_tag=release,
    )


@task
def docker_frontend_build_dev(c, push=False):
    """Build dev frontend image with Cypress/Playwright (slower)."""
    version, image, dockerfile, context = get_frontend_dev()
    content_hash = get_content_hash("frontend")
    docker_build(
        c,
        image,
        version,
        dockerfile,
        context,
        "runtime-dev",
        push=push,
        content_hash=content_hash,
        include_version_tag=False,
    )


@task
def docker_frontend_build(c, push=False):
    """Build both production and dev frontend images."""
    docker_frontend_build_prod(c, push=push)
    docker_frontend_build_dev(c, push=push)


@task
def docker_test_build(c, push=False):
    """Build frontend-dev image for CI fallback."""
    docker_frontend_build_dev(c, push=push)


@task
def docker_backend_build(c, push=False, release=False):
    """Build both production and dev backend images."""
    content_hash = get_content_hash("backend")
    version, image, dockerfile, context = get_backend()
    docker_build(
        c,
        image,
        version,
        dockerfile,
        context,
        push=push,
        content_hash=content_hash,
        include_version_tag=release,
    )
    version, image, dockerfile, context = get_backend_dev()
    docker_build(
        c,
        image,
        version,
        dockerfile,
        context,
        "runtime-dev",
        push=push,
        content_hash=content_hash,
        include_version_tag=False,
    )


@task
def docker_nginx_build(c, push=False, release=False):
    """Build nginx image."""
    content_hash = get_content_hash("nginx")
    version, image, dockerfile, context = get_nginx()
    docker_build(
        c,
        image,
        version,
        dockerfile,
        context,
        push=push,
        content_hash=content_hash,
        include_version_tag=release,
    )


@task
def docker_nginx_pull(c):
    _, image, _, _ = get_nginx()
    if not docker_pull_by_hash(c, image, "nginx"):
        raise RuntimeError(f"Failed to pull {image}")


@task
def docker_backend_pull(c):
    _, image, _, _ = get_backend()
    _, image_dev, _, _ = get_backend_dev()
    success = docker_pull_by_hash(c, image, "backend")
    success_dev = docker_pull_by_hash(c, image_dev, "backend")
    if not (success and success_dev):
        raise RuntimeError("Failed to pull backend images")


@task
def docker_frontend_pull(c):
    _, image, _, _ = get_frontend()
    _, image_dev, _, _ = get_frontend_dev()
    success = docker_pull_by_hash(c, image, "frontend")
    success_dev = docker_pull_by_hash(c, image_dev, "frontend")
    if not (success and success_dev):
        raise RuntimeError("Failed to pull frontend images")


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

# --- Release (prod-only) tasks ---


@task
def docker_release_build(c, push=False):
    """Build production-only images (backend, frontend, nginx). No -dev.
    Includes version tags for release tracking."""
    funcs = [
        lambda: docker_backend_build(c, push=push, release=True),
        lambda: docker_frontend_build_prod(c, push=push, release=True),
        lambda: docker_nginx_build(c, push=push, release=True),
    ]
    with alive_bar(total=3, title="Building Release Images") as bar:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(func): func for func in funcs}
            for future in as_completed(futures):
                future.result()
                bar()


@task
def docker_release_push(c):
    """Build and push production-only images."""
    docker_release_build(c, push=True)


@task
def docker_release_pull(c):
    """Pull production-only images (no -dev)."""
    funcs = [
        lambda: docker_pull_by_hash(c, get_backend()[1], "backend"),
        lambda: docker_pull_by_hash(c, get_frontend()[1], "frontend"),
        lambda: docker_pull_by_hash(c, get_nginx()[1], "nginx"),
    ]
    with alive_bar(total=3, title="Pulling Release Images") as bar:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(func): func for func in funcs}
            for future in as_completed(futures):
                future.result()
                bar()


ns_docker_release.add_task(docker_release_build, "build")
ns_docker_release.add_task(docker_release_push, "push")
ns_docker_release.add_task(docker_release_pull, "pull")

# Test-specific builds
ns_docker.add_task(docker_test_build, "test-build")
