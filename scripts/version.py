from pathlib import Path

import semver
from invoke import UnexpectedExit
from invoke.collection import Collection
from invoke.tasks import task

import paths
from backend.tasks import ns_db
from scripts.docker import docker_pull_all, ns_docker
from scripts.sync_version import (
    get_version_from_env,
    get_version_from_pyproject,
    update_env_version,
    update_pyproject_version,
)
from scripts.update import ns_update
from scripts.utils import crun, get_version

config = None
version = None


ns_version = Collection("version")


@task
def sync_version_from_env(c, env_file=".env.release"):
    """Sync version from environment file to pyproject.toml"""
    # Import functions locally to avoid import issues
    import os
    import sys

    print(f"Syncing version from {env_file}...")
    version = get_version_from_env(env_file)
    print(f"Syncing to version: {version}")
    update_pyproject_version(version)
    print("Version sync complete!")


@task
def sync_version_from_pyproject(c):
    """Sync version from pyproject.toml to environment files"""
    # Import functions locally to avoid import issues
    import os
    import sys

    from scripts.sync_version import get_version_from_pyproject, update_env_version

    print("Syncing version from pyproject.toml...")
    version = get_version_from_pyproject()
    print(f"Syncing to version: {version}")

    # Update environment files
    for env_file in [paths.PROD_ENV_FILE, paths.RELEASE_ENV_FILE]:
        update_env_version(env_file, version)

    print("Version sync complete!")


@task
def set_version(c, version, commit=True, tag_version=True):
    """Set version across all files and optionally commit and tag.

    Args:
        version: The version string to set (e.g., "1.2.3")
        commit: If True, commit the version changes (default: True)
        tag_version: If True, create a git tag for the version (default: True)
    """
    # Import functions locally to avoid import issues
    import os
    import sys

    from scripts.sync_version import update_env_version, update_pyproject_version

    print(f"Setting version to {version}...")

    # Update pyproject.toml
    update_pyproject_version(version)

    # Update environment files
    for env_file in [paths.PROD_ENV_FILE, paths.RELEASE_ENV_FILE]:
        update_env_version(env_file, version)

    print("Version sync complete!")

    if commit:
        print(f"Committing version changes...")
        crun(c, "git add pyproject.toml docker/.env.release docker/.env.prod")
        result = crun(c, f'git commit -m "Updated version to {version}"', warn=True)
        if result.ok:
            print("Committed version changes.")
        else:
            print("Warning: Git commit failed (possibly nothing to commit).")

    if tag_version:
        print(f"Creating git tag {version}...")
        result = crun(c, f"git tag {version}", warn=True)
        if result.ok:
            print(f"Created tag {version}.")
        else:
            print(f"Warning: Failed to create tag {version} (may already exist).")


@task
def build_with_version(c, version=None, env_file=None):
    """Build Docker images with version sync"""
    import os
    import sys

    from scripts.sync_version import (
        get_version_from_env,
        update_env_version,
        update_pyproject_version,
    )

    # Determine the version to use
    if version:
        target_version = version
        print(f"Setting version to {target_version}...")
        # Update all files with the specified version
        update_pyproject_version(target_version)
        for env_file_path in [".env.release", ".env.debug"]:
            update_env_version(env_file_path, target_version)
    elif env_file:
        print(f"Syncing version from {env_file}...")
        target_version = get_version_from_env(env_file)
        print(f"Syncing to version: {target_version}")
        # Update pyproject.toml with version from env file
        update_pyproject_version(target_version)
    else:
        # Default to using .env.release
        env_file = ".env.release"
        print(f"Syncing version from {env_file}...")
        target_version = get_version_from_env(env_file)
        print(f"Syncing to version: {target_version}")
        update_pyproject_version(target_version)

    print(f"Building with VERSION={target_version}")

    # Set environment variable for docker compose
    os.environ["VERSION"] = target_version

    # Build using local compose file
    cmd = f"docker compose -f docker-compose.local.yaml build --build-arg VERSION={target_version}"
    c.run(cmd)

    print(f"Build complete with version {target_version}")


@task
def tag(c):
    version = get_version()
    v_semver = semver.VersionInfo.parse(version)

    print(f"Tagging version: {version}")

    crun(c, f"git tag {version}")
    crun(c, "git push --tags")

    v_semver = v_semver.bump_patch()
    print("new version is string:", str(v_semver))
    set_version(c, str(v_semver))


ns_version.add_task(sync_version_from_env, "from-env")
ns_version.add_task(sync_version_from_pyproject, "from-pyproject")
ns_version.add_task(set_version, "set")
ns_version.add_task(build_with_version, "build")

ns_version.add_task(tag, "tag")
