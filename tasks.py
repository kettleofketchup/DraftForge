from invoke.collection import Collection
from invoke.tasks import task
import toml
from pathlib import Path
import paths
config = None
version = None
def get_pyproject():
    global config
    if not config:
        with paths.PYPROJECT_PATH.open('r') as f:
            config = toml.load(f)
        

def get_version():
    global version
    if version:
        return version
    get_pyproject()
    version = config['project']['version']  
    return version



ns = Collection()
ns_dev = Collection("dev")

ns_docker = Collection("docker")
ns_docker_frontend = Collection("frontend")
ns_docker_backend = Collection("backend")
ns_docker.add_collection(ns_docker_frontend)
ns_docker.add_collection(ns_docker_backend)

ns.add_collection(ns_docker, "docker")
ns.add_collection(ns_dev, "dev")

def tag_latest(c, image:str, version:str):

    c.run(f"docker tag {image}:{version} {image}:latest")
    c.run(f"docker push {image}:{version}")
    c.run(f"docker push {image}:latest")

def run_docker(c, image:str, version:str):
    c.run(f'docker run -it {image}:{version}', pty=True)

@task
def docker_build_frontend(c):
    version = get_version()
    image = f"{paths.FRONTEND_TAG}:{version}"
    cmd = f"docker build -f {str(paths.FRONTEND_DOCKERFILE_PATH)} {str(paths.FRONTEND_PATH)} -t {image}"
    print(cmd)
    c.run(cmd)

ns_docker_frontend.add_task(docker_build_frontend,"build")

@task
def docker_build_backend(c):
    version = get_version()
    image = f"{paths.BACKEND_TAG}:{version}"

    cmd = f"docker build -f {str(paths.BACKEND_DOCKERFILE_PATH)} . -t {image}"
    print(cmd)
    c.run(cmd)

ns_docker_backend.add_task(docker_build_backend,"build")




@task
def docker_push_frontend(c):
    version = get_version()
    image = paths.FRONTEND_TAG
    docker_build_frontend(c)
    tag_latest(c, image, version)

@task
def docker_push_backend(c):
    version = get_version()
    image = paths.BACKEND_TAG
    docker_build_backend(c)
    tag_latest(c, image, version)

@task
def docker_run_backend(c):
    version = get_version()
    image = paths.BACKEND_TAG
    run_docker(c, image, version)

@task
def docker_run_frontend(c):
    version = get_version()
    image = paths.FRONTEND_TAG
    run_docker(c, image, version)




ns_docker_backend.add_task(docker_push_backend, 'push')
ns_docker_frontend.add_task(docker_push_frontend, 'push')
ns_docker_backend.add_task( docker_run_backend, 'run')
ns_docker_frontend.add_task(docker_run_frontend, 'run')

@task
def dev_debug(c):
    version = get_version()
    cmd = f"docker-compose -f docker-compose.debug.yaml up"
    
    c.run(cmd)
