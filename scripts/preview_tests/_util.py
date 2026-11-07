"""Shared helpers for the DraftForge preview script tests.

Skips are loud: `require` skips locally but fails under CI=true unless the
caller marks the dependency as CI-exempt.
"""
import functools
import os
import shutil
import subprocess
import unittest
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELM_VERSION = "v3.19.4"


def in_ci() -> bool:
    return os.environ.get("CI", "").lower() in ("true", "1")


def require(cond: bool, what: str, ci_exempt: bool = False) -> None:
    if cond:
        return
    msg = f"MISSING: {what}"
    if in_ci() and not ci_exempt:
        raise AssertionError(msg)
    raise unittest.SkipTest(msg)


def which(name: str) -> bool:
    return shutil.which(name) is not None


def network_ok() -> bool:
    req = urllib.request.Request("https://raw.githubusercontent.com", method="HEAD")
    try:
        urllib.request.urlopen(req, timeout=3)
    except urllib.error.HTTPError:
        return True  # reachable; the root path itself answers with an error
    except OSError:
        return False
    return True


@functools.cache
def helm() -> str:
    """Return $HELM (default `helm`) after checking it is the pinned Helm 3."""
    binary = os.environ.get("HELM", "helm")
    try:
        out = subprocess.run([binary, "version", "--short"], capture_output=True,
                             text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        out = f"unusable ({exc})"
    if not out.startswith(HELM_VERSION + "+") and out != HELM_VERSION:
        raise AssertionError(
            f"HELM={binary} reports {out}, need {HELM_VERSION}; run "
            f'export HELM="$(mise where helm@3.19.4)/linux-amd64/helm"')
    return binary
