from datetime import date

from invoke.collection import Collection
from invoke.context import Context
from invoke.exceptions import Exit
from invoke.tasks import task

import paths
from scripts import changelog
from scripts.sync_version import (
    get_version_from_env,
    get_version_from_pyproject,
    update_env_version,
    update_pyproject_version,
)
from scripts.utils import crun

config = None
version = None


ns_version = Collection("version")


@task
def sync_version_from_env(c: Context, env_file: str = ".env.release") -> None:
    """Sync version from environment file to pyproject.toml"""
    print(f"Syncing version from {env_file}...")
    version = get_version_from_env(env_file)
    print(f"Syncing to version: {version}")
    update_pyproject_version(version)
    print("Version sync complete!")


@task
def sync_version_from_pyproject(c: Context) -> None:
    """Sync version from pyproject.toml to environment files"""
    print("Syncing version from pyproject.toml...")
    version = get_version_from_pyproject()
    print(f"Syncing to version: {version}")

    # Update environment files
    for env_file in [paths.PROD_ENV_FILE, paths.RELEASE_ENV_FILE]:
        update_env_version(env_file, version)

    print("Version sync complete!")


@task
def set_version(
    c: Context, version: str, commit: bool = True, tag_version: bool = True
) -> None:
    """Set version across all files; by default also release it.

    With commit (the default) this is the release: it assembles changelog.d/ into
    CHANGELOG.md, commits "Updated version to X.Y.Z" with the fragments removed,
    tags X.Y.Z and pushes main, then the tag. A failure before the main push rolls
    back. With --no-commit it only rewrites the version files and, unless
    --no-tag-version, makes a local tag.

    Args:
        version: The version string to set (e.g., "1.2.3")
        commit: If True, release: assemble, commit, tag and push (default: True)
        tag_version: If True, create a git tag for the version (default: True)
    """
    root = paths.PROJECT_PATH
    if commit:
        try:
            changelog.release_preflight(root, version, tag_version)
        except changelog.ChangelogError as exc:
            raise Exit(f"version.set: {exc}", code=1)
        if not changelog.fragment_paths(root):
            print(f"Warning: changelog.d/ has no fragments; {version} has no notes.")
            try:
                answer = input(f"Release {version} with no changelog notes? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() != "y":
                raise Exit("Cancelled; nothing was changed.", code=1)

    def write_version_files() -> None:
        print(f"Setting version to {version}...")
        update_pyproject_version(version)
        for env_file in [paths.PROD_ENV_FILE, paths.RELEASE_ENV_FILE]:
            update_env_version(env_file, version)
        print("Version sync complete!")

    if not commit:
        write_version_files()
        if tag_version:
            print(f"Creating local git tag {version}...")
            if not crun(c, f"git tag {version}", warn=True).ok:
                print(f"Warning: Failed to create tag {version} (may already exist).")
        return

    print(
        f"Releasing {version}: assembling CHANGELOG.md, committing, tagging, pushing..."
    )
    try:
        consumed = changelog.release(
            root, version, date.today().isoformat(), write_version_files
        )
    except changelog.ChangelogError as exc:
        raise Exit(f"version.set: {exc}", code=1)
    print(
        f"Released {version} ({len(consumed)} changelog fragment(s)): pushed main and tag {version}."
    )


@task
def build_with_version(
    c: Context, version: str | None = None, env_file: str | None = None
) -> None:
    """Build Docker images with version sync"""
    import os

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


ns_version.add_task(sync_version_from_env, "from-env")
ns_version.add_task(sync_version_from_pyproject, "from-pyproject")
ns_version.add_task(set_version, "set")
ns_version.add_task(build_with_version, "build")
