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
):
    img_str = f"{image}:{version}"
    cmd = (
        f"docker build -f {str(dockerfile)} "
        f"{str(context)} -t {img_str} --target {target}"
    )
    crun(c, cmd)

    crun(c, f"docker tag {img_str} {image}:latest")


def docker_pull(c, image: str, version: str, dockerfile: Path, context: Path):

    cmd = f"docker pull {image}:{version}"
    cmd2 = f"docker pull {image}:latest"
    crun(c, cmd)
    crun(c, cmd2)


def tag_latest(c, image: str, version: str):
    crun(c, f"docker tag {image}:{version} {image}:latest")
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
def docker_frontend_build(c):
    version, image, dockerfile, context = get_frontend()
    docker_build(c, image, version, dockerfile, context, "runtime")
    # frontend-dev needed for Cypress tests in CI
    version, image, dockerfile, context = get_frontend_dev()
    docker_build(c, image, version, dockerfile, context, "runtime-dev")


@task
def docker_backend_build(c):
    version, image, dockerfile, context = get_backend()
    docker_build(c, image, version, dockerfile, context)
    version, image, dockerfile, context = get_backend_dev()
    docker_build(c, image, version, dockerfile, context, "runtime-dev")


@task
def docker_nginx_build(c):
    version, image, dockerfile, context = get_nginx()
    docker_build(c, image, version, dockerfile, context)


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
    docker_frontend_build(c)
    version, image, dockerfile, context = get_frontend()
    tag_latest(c, image, version)
    # frontend-dev needed for Cypress tests in CI
    version, image, dockerfile, context = get_frontend_dev()
    tag_latest(c, image, version)


@task
def docker_backend_push(c):
    docker_backend_build(c)
    version, image, dockerfile, context = get_backend()
    tag_latest(c, image, version)
    version, image, dockerfile, context = get_backend_dev()
    tag_latest(c, image, version)


@task
def docker_nginx_push(c):
    version, image, dockerfile, context = get_nginx()
    docker_nginx_build(c)
    tag_latest(c, image, version)


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
def docker_build_all(c):
    funcs = [docker_backend_build, docker_frontend_build, docker_nginx_build]
    with alive_bar(total=3, title="Building Images") as bar:
        for func in funcs:
            func(c)
            bar()


@task
def docker_push_all(c):
    docker_build_all(c)
    funcs = [docker_backend_push, docker_frontend_push, docker_nginx_push]
    with alive_bar(total=3, title="Pushing Images") as bar:
        for func in funcs:
            func(c)
            bar()


@task
def docker_pull_all(c):
    funcs = [docker_backend_pull, docker_frontend_pull, docker_nginx_pull]
    with alive_bar(total=3, title="Pulling Images") as bar:
        for func in funcs:
            func(c)
            bar()


ns_docker_frontend.add_task(docker_frontend_build, "build")
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
