"""scripts/buildx_timing.py: join BuildKit vertex names with their durations."""

import json
from pathlib import Path

import pytest

from scripts import buildx_timing

LOG = """\
#0 building with "builder-1" instance using docker-container driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 2.10kB done
#1 DONE 0.1s

#5 [base 1/3] FROM docker.io/library/node:22-slim@sha256:abc
#5 CACHED

#9 [deps 2/4] RUN npm ci
#9 4.512 added 812 packages in 41s
#9 DONE 41.3s

#12 [runtime-dev 3/3] RUN npx playwright install --with-deps chromium
#12 0.913 Downloading Chromium
#12 DONE 63.0s

#14 exporting to image
#14 exporting layers 2.1s done
#14 DONE 9.4s
"""


def test_names_join_durations_by_vertex() -> None:
    steps = {s.vertex: s for s in buildx_timing.parse_history_log(LOG)}
    assert steps[9].name == "[deps 2/4] RUN npm ci"
    assert steps[9].seconds == 41.3
    assert steps[12].seconds == 63.0
    assert steps[14].name == "exporting to image"
    assert steps[5].cached and steps[5].seconds is None


def test_render_ranks_uncached_steps() -> None:
    text, md = buildx_timing.render(
        "frontend-dev (runtime-dev)", 120.0, buildx_timing.parse_history_log(LOG), top=2
    )
    lines = text.splitlines()
    assert (
        lines[0]
        == "── slowest build steps (buildx frontend-dev (runtime-dev): 2m00s) ──"
    )
    assert "63.0s" in lines[1] and "playwright install" in lines[1]
    assert "41.3s" in lines[2]
    assert lines[3] == "  … plus 1 cached step(s)"
    assert "| 63.0 |" in md


def test_missing_ref_never_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"containerimage.digest": "sha256:x"}))
    assert buildx_timing.main(["--metadata-file", str(meta), "--label", "x"]) == 0
    assert "no build-step report" in capsys.readouterr().out


def test_summary_written_on_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "build.log"
    log.write_text(LOG)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    args = [
        "--metadata-file",
        "/dev/null",
        "--label",
        "x",
        "--seconds",
        "75",
        "--log",
        str(log),
    ]
    assert buildx_timing.main(args) == 0
    assert "::notice title=buildx x::1m15s" in capsys.readouterr().out
    assert "RUN npm ci" in summary.read_text()
