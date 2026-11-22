"""scripts/ci_timing.py log parsing: command segments, gaps and buildx reports."""

from scripts import ci_timing

LOG = """\
2026-11-22T15:09:14.0000000Z ##[group]Runner Image
2026-11-22T15:09:15.0000000Z ##[group]Run actions/checkout@v4
2026-11-22T15:09:17.0000000Z ##[group]Run just docker::all-push
2026-11-22T15:09:20.0000000Z Running: docker buildx build ...
2026-11-22T15:11:20.0000000Z ── slowest build steps (buildx frontend-dev (runtime-dev): 2m03s) ──
2026-11-22T15:11:20.0000001Z     63.0s  [runtime-dev 3/3] RUN npx playwright install --with-deps chromium
2026-11-22T15:11:20.0000002Z     41.3s  [deps 2/4] RUN npm ci
2026-11-22T15:11:20.0000003Z   … plus 4 cached step(s)
2026-11-22T15:11:21.0000000Z ##[group]Run just test::pw::cicd-chromium --shard=3/4
2026-11-22T15:12:21.0000000Z Post job cleanup.
"""


def test_segments_gaps_and_builds() -> None:
    segs, gaps, builds = ci_timing.parse_log(LOG, "2026-11-22T15:12:25Z")
    by_name = {s["name"]: s["dur_s"] for s in segs}
    assert by_name["actions/checkout@v4"] == 2.0
    assert by_name["just docker::all-push"] == 124.0
    assert by_name["just test::pw::cicd-chromium --shard=N"] == 60.0
    assert by_name["(post-job cleanup)"] == 4.0
    assert any(
        g["gap_s"] == 120.0 and g["segment"] == "just docker::all-push" for g in gaps
    )
    assert builds == [
        {"image": "frontend-dev (runtime-dev)", "step": "(total)", "dur_s": 123},
        {
            "image": "frontend-dev (runtime-dev)",
            "step": "[runtime-dev 3/3] RUN npx playwright install --with-deps chromium",
            "dur_s": 63.0,
        },
        {
            "image": "frontend-dev (runtime-dev)",
            "step": "[deps 2/4] RUN npm ci",
            "dur_s": 41.3,
        },
    ]


def test_family_strips_matrix_suffix() -> None:
    assert ci_timing.family("Playwright chromium (shard 3/4)") == "Playwright chromium"
    assert ci_timing.family("Backend tests (migrations)") == "Backend tests"
