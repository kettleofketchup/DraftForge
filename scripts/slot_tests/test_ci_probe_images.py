"""scripts/ci_probe_images.py, prepare's probe-first step, against a stub registry.

It must agree with `just ci::prepare-images --probe`, and the prepare job must skip
setup and builds only on its explicit build=false.
"""

import base64
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from scripts.slot_tests.test_ci_prepare_images import (
    ALL,
    JUST,
    PR,
    ci_ref,
    prepare,
    refs,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci_probe_images.py"
USER, SECRET = "octocat", "ghs_example"


class Registry:
    """A GHCR-shaped stub: /token hands out per-repo bearer tokens, HEAD on a
    manifest answers 200 for a ref in `present` with that repo's token, else 404."""

    def __init__(self) -> None:
        self.present: set[str] = set()
        self.status: int | None = None  # forced status for every manifest HEAD
        self.refuse_basic = False
        self.token_auth: list[str] = []
        self.heads: list[str] = []
        registry = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                pass

            def do_GET(self) -> None:
                from urllib.parse import parse_qs, urlparse

                url = urlparse(self.path)
                auth = self.headers.get("Authorization", "")
                registry.token_auth.append(auth)
                if url.path != "/token" or (auth and registry.refuse_basic):
                    self.send_response(401)
                    self.end_headers()
                    return
                scope = parse_qs(url.query)["scope"][0]
                repo = scope.removeprefix("repository:").removesuffix(":pull")
                body = json.dumps({"token": f"t-{repo}"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_HEAD(self) -> None:
                repo, _, tag = self.path.removeprefix("/v2/").partition("/manifests/")
                ref = f"ghcr.io/{repo}:{tag}"
                registry.heads.append(ref)
                ok = (
                    ref in registry.present
                    and self.headers.get("Authorization") == f"Bearer t-{repo}"
                    and "application/vnd.oci.image.index.v1+json"
                    in self.headers.get("Accept", "")
                )
                code = registry.status or (200 if ok else 404)
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def registry() -> Iterator[Registry]:
    reg = Registry()
    thread = threading.Thread(target=reg.server.serve_forever, daemon=True)
    thread.start()
    yield reg
    reg.server.shutdown()
    reg.server.server_close()


def probe(
    tmp_path: Path, registry: Registry, **extra: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, str], Path]:
    out, summary = tmp_path / "output", tmp_path / "summary"
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DF_", "GHCR_", "GITHUB_"))
        },
        "DF_PROBE_REGISTRY_URL": registry.url,
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GHCR_USER": USER,
        "GHCR_TOKEN": SECRET,
        **extra,
    }
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    outputs = dict(
        line.split("=", 1)
        for line in (out.read_text() if out.exists() else "").splitlines()
    )
    return result, outputs, summary


def test_everything_present_means_build_false(
    tmp_path: Path, registry: Registry
) -> None:
    registry.present = {refs()[n] for n in ALL}
    result, outputs, summary = probe(tmp_path, registry)
    assert result.returncode == 0, result.stderr
    assert outputs == {"missing": "", "build": "false"}
    assert result.stdout.splitlines()[-1] == "missing="
    assert "nothing to build" in summary.read_text()
    basic = base64.b64encode(f"{USER}:{SECRET}".encode()).decode()
    assert set(registry.token_auth) == {f"Basic {basic}"}
    assert SECRET not in result.stdout + result.stderr


def test_a_missing_item_means_build_true(tmp_path: Path, registry: Registry) -> None:
    registry.present = {refs()[n] for n in ALL - {"nginx", "test-db"}}
    result, outputs, summary = probe(tmp_path, registry)
    assert result.returncode == 0, result.stderr
    assert outputs == {"missing": "nginx test-db", "build": "true"}
    assert not summary.exists()  # ci::prepare-images writes the summary when it builds


def test_pr_mode_counts_this_prs_draftforge_ci_tag(
    tmp_path: Path, registry: Registry
) -> None:
    registry.present = {refs()[n] for n in ALL - {"backend-dev"}} | {
        ci_ref("backend-dev")
    }
    result, outputs, _ = probe(tmp_path, registry, DF_PREPARE_PR=PR)
    assert outputs == {"missing": "", "build": "false"}, result.stdout + result.stderr
    result, outputs, _ = probe(tmp_path, registry)  # hosted: main's hash tag only
    assert outputs == {"missing": "backend-dev", "build": "true"}, result.stderr


def test_registry_errors_count_as_missing(tmp_path: Path, registry: Registry) -> None:
    registry.present = {refs()[n] for n in ALL}
    registry.status = 500
    result, outputs, _ = probe(tmp_path, registry)
    assert result.returncode == 0, result.stderr
    assert outputs["build"] == "true"
    assert set(outputs["missing"].split()) == ALL


def test_unreachable_registry_counts_as_missing(
    tmp_path: Path, registry: Registry
) -> None:
    result, outputs, _ = probe(
        tmp_path, registry, DF_PROBE_REGISTRY_URL="http://127.0.0.1:9"
    )
    assert result.returncode == 0, result.stderr
    assert outputs["build"] == "true"
    assert set(outputs["missing"].split()) == ALL


def test_refused_credentials_fall_back_to_anonymous(
    tmp_path: Path, registry: Registry
) -> None:
    registry.present = {refs()[n] for n in ALL}
    registry.refuse_basic = True
    result, outputs, _ = probe(tmp_path, registry)
    assert outputs == {"missing": "", "build": "false"}, result.stdout + result.stderr
    assert "" in registry.token_auth


def test_malformed_pr_number_exits_2_without_build_output(
    tmp_path: Path, registry: Registry
) -> None:
    result, outputs, _ = probe(tmp_path, registry, DF_PREPARE_PR="1; true")
    assert result.returncode == 2
    assert "build" not in outputs  # unset: the workflow takes the build path
    assert registry.heads == []


@pytest.mark.skipif(JUST is None, reason="just is not on PATH")
@pytest.mark.parametrize("pr", ["", PR])
def test_checks_the_same_refs_as_prepare_images(
    tmp_path: Path, registry: Registry, pr: str
) -> None:
    extra = {"DF_PREPARE_PR": pr} if pr else {}
    (tmp_path / "probe").mkdir()
    (tmp_path / "recipe").mkdir()
    result, outputs, _ = probe(tmp_path / "probe", registry, **extra)
    assert outputs["build"] == "true", result.stderr
    recipe, calls = prepare(tmp_path / "recipe", set(), 0, "--probe", **extra)
    assert recipe.returncode == 0, recipe.stdout + recipe.stderr
    inspected = {c[3] for c in calls if c[:3] == ["buildx", "imagetools", "inspect"]}
    assert set(registry.heads) == inspected
    assert recipe.stdout.strip() == f"missing={outputs['missing']}"


def _prepare_steps() -> list[dict]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/playwright.yml").read_text())
    return workflow["jobs"]["prepare"]["steps"]


def test_prepare_probes_right_after_checkout() -> None:
    steps = _prepare_steps()
    names = [s.get("uses", s.get("name")) for s in steps]
    checkout = next(
        i for i, s in enumerate(steps) if "actions/checkout" in s.get("uses", "")
    )
    assert steps[checkout]["with"]["persist-credentials"] is False
    assert "fetch-depth" not in steps[checkout].get("with", {}), names
    probe_step = steps[checkout + 1]
    assert probe_step["id"] == "probe"
    assert probe_step["run"] == "python3 -I scripts/ci_probe_images.py"
    assert probe_step["continue-on-error"] is True


def test_prepare_skips_setup_and_build_only_on_build_false() -> None:
    steps = _prepare_steps()
    after = steps[[s.get("id") for s in steps].index("probe") + 1 :]
    gated = {"./.github/actions/setup-toolchain", "./.github/actions/setup-builder"}
    for step in after:
        cond = " ".join(str(step.get("if", "")).split())
        if step.get("name") == "Report elapsed time":
            assert cond == "always()"
        elif step.get("name") == "Set up Python for the test DB":
            assert cond == (
                "runner.environment == 'self-hosted' && (steps.probe.outcome != 'success'"
                " || contains(steps.probe.outputs.missing, 'test-db'))"
            )
        else:
            assert (
                step.get("uses") in gated
                or step.get("run") == "just ci::prepare-images"
            ), step
            assert "steps.probe.outputs.build != 'false'" in cond, step
    (build,) = [s for s in after if s.get("run") == "just ci::prepare-images"]
    assert set(build["env"]) == {"DF_PREPARE_READONLY", "DF_PREPARE_PR"}
