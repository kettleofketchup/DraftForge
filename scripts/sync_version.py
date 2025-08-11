#!/usr/bin/env python3
"""
Script to sync version numbers across pyproject.toml and environment files.
Usage:
    python scripts/sync_version.py --version 0.3.8
    python scripts/sync_version.py --from-env .env.release
    python scripts/sync_version.py --from-pyproject
"""

import argparse
import os
import re
from pathlib import Path


def get_version_from_env(env_file: str) -> str:
    """Extract version from environment file."""
    env_path = Path(env_file)
    if not env_path.exists():
        raise FileNotFoundError(f"Environment file {env_file} not found")

    with open(env_path, "r") as f:
        content = f.read()

    match = re.search(r'VERSION="([^"]+)"', content)
    if not match:
        raise ValueError(f"VERSION not found in {env_file}")

    return match.group(1)


def get_version_from_pyproject() -> str:
    """Extract version from pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")

    with open(pyproject_path, "r") as f:
        content = f.read()

    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        raise ValueError("Version not found in pyproject.toml")

    return match.group(1)


def update_pyproject_version(version: str):
    """Update version in pyproject.toml."""
    pyproject_path = Path("pyproject.toml")

    with open(pyproject_path, "r") as f:
        content = f.read()

    # Handle both static version and dynamic version
    if 'dynamic = ["version"]' in content:
        # If using dynamic version, we need to switch back to static
        content = re.sub(r'dynamic = \["version"\]', f'version = "{version}"', content)
    else:
        # Update existing version
        content = re.sub(r'version = "[^"]+"', f'version = "{version}"', content)

    with open(pyproject_path, "w") as f:
        f.write(content)

    print(f"Updated pyproject.toml version to {version}")


def update_env_version(env_file: str, version: str):
    """Update version in environment file."""
    env_path = Path(env_file)

    if not env_path.exists():
        print(f"Warning: {env_file} not found, skipping")
        return

    with open(env_path, "r") as f:
        content = f.read()

    content = re.sub(r'VERSION="[^"]+"', f'VERSION="{version}"', content)

    with open(env_path, "w") as f:
        f.write(content)

    print(f"Updated {env_file} version to {version}")


def main():
    parser = argparse.ArgumentParser(description="Sync version numbers across files")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--version", help="Set specific version")
    group.add_argument("--from-env", help="Use version from environment file")
    group.add_argument(
        "--from-pyproject", action="store_true", help="Use version from pyproject.toml"
    )

    parser.add_argument(
        "--env-files",
        nargs="+",
        default=[".env.release", ".env.debug"],
        help="Environment files to update",
    )

    args = parser.parse_args()

    # Determine the version to use
    if args.version:
        version = args.version
    elif args.from_env:
        version = get_version_from_env(args.from_env)
    elif args.from_pyproject:
        version = get_version_from_pyproject()

    print(f"Syncing to version: {version}")

    # Update pyproject.toml
    update_pyproject_version(version)

    # Update environment files
    for env_file in args.env_files:
        update_env_version(env_file, version)

    print("Version sync complete!")


if __name__ == "__main__":
    main()
