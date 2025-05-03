from pathlib import Path

import toml
from invoke.collection import Collection
from invoke.tasks import task

import paths

config = None
version = None


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
