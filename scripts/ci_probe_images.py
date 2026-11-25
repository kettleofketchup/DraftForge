#!/usr/bin/env python3
"""Report which Playwright-stack images and test DB GHCR lacks, before any setup.

The first step of playwright.yml `prepare`: stdlib only, no docker, no just, so it
runs right after checkout on the bare runner. It checks the refs `just
ci::prepare-images` checks, with the same rule (present means main's
`draftforge/<img>:<hash>` exists or, in PR mode, this PR's
`draftforge-ci/<img>:pr-<n>-<hash>`), by manifest HEADs over the registry API
instead of `docker buildx imagetools inspect`.

    python3 -I scripts/ci_probe_images.py

Prints one `<name> <hash12> present|missing` line per item, then `missing=<names>`.
With GITHUB_OUTPUT set it also writes `missing=<names>` and `build=true|false` there;
`build` is written last, so a probe that dies early leaves it unset and the workflow
takes the build path. Any registry error counts as missing, for the same reason.
Always exits 0 unless DF_PREPARE_PR is malformed (exit 2).

Env: GHCR_USER and GHCR_TOKEN (pull credentials; anonymous without them),
DF_PREPARE_PR (PR mode), DF_TEST_DB_REGISTRY (as in ci::prepare-images; a non-GHCR
one counts as missing), DF_PROBE_REGISTRY_URL (tests: the registry's base URL).
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "ghcr.io"
REGISTRY = f"{HOST}/kettleofketchup/draftforge"
CI_REGISTRY = f"{HOST}/kettleofketchup/draftforge-ci"
# name -> the service hash-docker-image.sh hashes; keep in step with ci::prepare-images
# (test_ci_probe_images.py compares the refs both check).
IMAGES = {
    "frontend-dev": "frontend",
    "backend-dev": "backend",
    "playwright-runner": "playwright",
    "nginx": "nginx",
}
ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)
TIMEOUT = 10


def _hash(script: str, *args: str) -> str:
    out = subprocess.run(
        [str(ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", out):
        raise RuntimeError(f"{script} printed {out!r}, not a sha256")
    return out


def refs(pr: str) -> dict[str, list[str]]:
    """name -> the refs whose existence makes it present, in ci::prepare-images order."""
    db_registry = os.environ.get("DF_TEST_DB_REGISTRY") or f"{REGISTRY}/test-db"
    out = {
        name: [f"{REGISTRY}/{name}:{_hash('hash-docker-image.sh', service)}"]
        for name, service in IMAGES.items()
    }
    out["test-db"] = [f"{db_registry}:{_hash('hash-test-db-sources.sh')}"]
    if pr:
        for name, found in out.items():
            found.append(f"{CI_REGISTRY}/{name}:pr-{pr}-{found[0].rsplit(':', 1)[1]}")
    return out


def _open(req: urllib.request.Request) -> int:
    """HTTP status of `req`, one retry on a network error or 5xx; 0 if never answered."""
    status = 0
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            status = e.code
            if e.code < 500:
                return status
        except (urllib.error.URLError, OSError):
            status = 0
    return status


def _token(base: str, repo: str) -> str | None:
    """A pull token for `repo`: with GHCR_USER/GHCR_TOKEN, else (or if refused) anonymous."""
    query = urllib.parse.urlencode(
        {"service": HOST, "scope": f"repository:{repo}:pull"}
    )
    user, secret = os.environ.get("GHCR_USER", ""), os.environ.get("GHCR_TOKEN", "")
    attempts = [f"{user}:{secret}", None] if user and secret else [None]
    for cred in attempts:
        req = urllib.request.Request(f"{base}/token?{query}")
        if cred is not None:
            basic = base64.b64encode(cred.encode()).decode()
            req.add_header("Authorization", f"Basic {basic}")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                token = json.load(resp).get("token")
            if isinstance(token, str) and token:
                return token
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None


def exists(base: str, ref: str) -> bool:
    """True only on a 200 for the manifest HEAD; any error is False (counts as missing)."""
    name, _, tag = ref.rpartition(":")
    host, _, repo = name.partition("/")
    if host != HOST or not repo or not tag:
        return False
    try:
        token = _token(base, repo)
    except Exception:  # noqa: BLE001 - an unexpected error must mean "build"
        return False
    if token is None:
        return False
    req = urllib.request.Request(
        f"{base}/v2/{repo}/manifests/{urllib.parse.quote(tag)}",
        method="HEAD",
        headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT},
    )
    return _open(req) == 200


def main() -> int:
    pr = os.environ.get("DF_PREPARE_PR", "")
    if pr and not pr.isdigit():
        print(
            f"::error::ci_probe_images: DF_PREPARE_PR must be a PR number, got {pr!r}"
        )
        return 2
    base = os.environ.get("DF_PROBE_REGISTRY_URL") or f"https://{HOST}"
    wanted = refs(pr)
    flat = [ref for found in wanted.values() for ref in found]
    with ThreadPoolExecutor(max_workers=len(flat)) as pool:
        hit = dict(zip(flat, pool.map(lambda r: exists(base, r), flat)))
    missing = [n for n, found in wanted.items() if not any(hit[r] for r in found)]
    lines = [
        f"{n:<18} {found[0].rsplit(':', 1)[1][:12]}  "
        f"{'missing' if n in missing else 'present'}"
        for n, found in wanted.items()
    ]
    print("\n".join(lines))
    print(f"missing={' '.join(missing)}", flush=True)
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a") as f:
            f.write(f"missing={' '.join(missing)}\n")
            f.write(f"build={'true' if missing else 'false'}\n")
    if (summary := os.environ.get("GITHUB_STEP_SUMMARY")) and not missing:
        with open(summary, "a") as f:
            f.write("```\n" + "\n".join(lines) + "\nnothing to build\n```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
