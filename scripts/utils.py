from pathlib import Path

try:
    import toml
except ImportError:
    toml = None
from invoke.collection import Collection
from invoke.tasks import task

import paths

config = None
version = None


def crun(c, *args, **kwargs):

    with c.cd(paths.PROJECT_PATH):
        if "pty" not in kwargs:
            print(f"Running: {' '.join(args)}")
        return c.run(*args, **kwargs)


def get_pyproject():
    global config
    if not config:
        with paths.PYPROJECT_PATH.open("r") as f:
            config = toml.load(f)
    return config


def get_version():
    global version
    config = get_pyproject()
    if version:
        return version

    version = config["project"]["version"]
    return version
