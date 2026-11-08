"""Version and release commands (`just version::*`).

Run from the repo root with the project venv:
    python -m scripts.version set X.Y.Z [--no-commit] [--no-tag-version]
    python -m scripts.version from-env [--env-file F]
    python -m scripts.version from-pyproject
    python -m scripts.version sync [--version X.Y.Z | --env-file F]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import paths
from scripts import changelog
from scripts.sync_version import (
    get_version_from_env,
    get_version_from_pyproject,
    update_env_version,
    update_pyproject_version,
)

VERSIONED_ENV_FILES = (paths.PROD_ENV_FILE, paths.RELEASE_ENV_FILE)


class VersionError(Exception):
    pass


def sync_from_env(env_file: Path = paths.RELEASE_ENV_FILE) -> None:
    print(f"Syncing version from {env_file}...")
    version = get_version_from_env(env_file)
    print(f"Syncing to version: {version}")
    update_pyproject_version(version)
    print("Version sync complete!")


def sync_from_pyproject() -> None:
    print("Syncing version from pyproject.toml...")
    version = get_version_from_pyproject()
    print(f"Syncing to version: {version}")
    for env_file in VERSIONED_ENV_FILES:
        update_env_version(env_file, version)
    print("Version sync complete!")


def write_version_files(version: str) -> None:
    print(f"Setting version to {version}...")
    update_pyproject_version(version)
    for env_file in VERSIONED_ENV_FILES:
        update_env_version(env_file, version)
    print("Version sync complete!")


def sync(version: str | None = None, env_file: Path | None = None) -> str:
    """Write `version` (or the one in env_file) to pyproject.toml and the env files."""
    if version is None:
        source = env_file or paths.RELEASE_ENV_FILE
        print(f"Syncing version from {source}...")
        version = get_version_from_env(source)
    write_version_files(version)
    return version


def set_version(version: str, commit: bool = True, tag_version: bool = True) -> None:
    """Set the version everywhere; by default also release it.

    With commit (the default) this is the release: it assembles changelog.d/ into
    CHANGELOG.md, commits "Updated version to X.Y.Z" with the fragments removed,
    tags X.Y.Z and pushes main, then the tag. A failure before the main push rolls
    back. With --no-commit it only rewrites the version files and, unless
    --no-tag-version, makes a local tag.
    """
    root = paths.PROJECT_PATH
    if commit:
        try:
            changelog.release_preflight(root, version, tag_version)
        except changelog.ChangelogError as exc:
            raise VersionError(f"version::set: {exc}") from exc
        if not changelog.fragment_paths(root):
            print(f"Warning: changelog.d/ has no fragments; {version} has no notes.")
            try:
                answer = input(f"Release {version} with no changelog notes? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() != "y":
                raise VersionError("Cancelled; nothing was changed.")

    if not commit:
        write_version_files(version)
        if tag_version:
            print(f"Creating local git tag {version}...")
            if subprocess.run(["git", "tag", version], cwd=root).returncode != 0:
                print(f"Warning: Failed to create tag {version} (may already exist).")
        return

    print(
        f"Releasing {version}: assembling CHANGELOG.md, committing, tagging, pushing..."
    )
    try:
        consumed = changelog.release(
            root, version, date.today().isoformat(), lambda: write_version_files(version)
        )
    except changelog.ChangelogError as exc:
        raise VersionError(f"version::set: {exc}") from exc
    print(
        f"Released {version} ({len(consumed)} changelog fragment(s)): pushed main and tag {version}."
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.version")
    sub = p.add_subparsers(dest="cmd", required=True)

    set_p = sub.add_parser("set", help="release X.Y.Z (or only write it with --no-commit)")
    set_p.add_argument("version")
    set_p.add_argument("--no-commit", dest="commit", action="store_false")
    set_p.add_argument("--no-tag-version", dest="tag_version", action="store_false")

    env_p = sub.add_parser("from-env", help="copy the env file's VERSION to pyproject.toml")
    env_p.add_argument("--env-file", type=Path, default=paths.RELEASE_ENV_FILE)

    sub.add_parser("from-pyproject", help="copy pyproject.toml's version to the env files")

    sync_p = sub.add_parser("sync", help="write one version to pyproject.toml and the env files")
    group = sync_p.add_mutually_exclusive_group()
    group.add_argument("--version")
    group.add_argument("--env-file", type=Path)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    ns = _parser().parse_args(argv)
    try:
        if ns.cmd == "set":
            set_version(ns.version, commit=ns.commit, tag_version=ns.tag_version)
        elif ns.cmd == "from-env":
            sync_from_env(ns.env_file)
        elif ns.cmd == "from-pyproject":
            sync_from_pyproject()
        elif ns.cmd == "sync":
            sync(ns.version, ns.env_file)
    except VersionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"version::{ns.cmd}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
