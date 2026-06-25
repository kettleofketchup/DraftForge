"""T1.9 — Cacheops integration guardrails for BaseUserProfile.

Local CI runs without a live Redis (cacheops degrades gracefully via
CACHEOPS_DEGRADE_ON_FAILURE=True), so we cannot reliably warm a real cached
endpoint and observe invalidation in unit tests. Instead we assert the
invariants directly:

1. The CACHEOPS dict registers ``user.baseuserprofile`` so cacheops will
   actually track invalidations for the model.
2. Every cacheops decorator block that depends on ``CustomUser`` *also*
   depends on ``BaseUserProfile`` — otherwise a PATCH to
   ``/api/users/me/profile/base/`` silently serves stale nickname/avatar to
   any cached endpoint that ships those fields (T1 epic regression risk).

A real-Redis integration test that warms a cached list endpoint, PATCHes the
nickname, and re-fetches to confirm invalidation belongs in the
container-backed test stack (just test::run ...) which has Redis available;
running it here would fall back to DummyCache and pass vacuously.
"""

import pathlib
import re

from django.conf import settings
from django.test import TestCase


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _iter_cached_as_blocks(path: pathlib.Path):
    """Yield ``(start_line, block_text)`` for every ``@cached_as(...)`` call
    in ``path``, correctly handling multi-line decorators by walking
    parentheses balance.
    """
    text = path.read_text()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.search(r"@cached_as\s*\(", line)
        if not match:
            i += 1
            continue
        start_line = i + 1  # 1-indexed for error messages
        depth = 0
        chunks = []
        # Start scanning from the @cached_as position
        j = match.start()
        while i < len(lines):
            current = lines[i] if j == 0 else lines[i][j:]
            chunks.append(current)
            for ch in current:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
            if depth == 0 and chunks:
                break
            i += 1
            j = 0
        yield start_line, "\n".join(chunks)
        i += 1


class CacheopsSettingsTests(TestCase):
    """The CACHEOPS dict must register user.baseuserprofile so that PATCHes
    on the model actually trigger invalidation of any @cached_as blocks that
    depend on it. Without this entry, cacheops silently treats the model as
    uncached and the dep is a no-op.

    When DISABLE_CACHE=1 (populate scripts, local test runs without Redis)
    settings.py clears CACHEOPS entirely — the dep is irrelevant there, so
    skip the assertion rather than reporting a spurious failure.
    """

    def test_cacheops_dict_registers_baseuserprofile(self):
        cacheops = getattr(settings, "CACHEOPS", {}) or {}
        if not getattr(settings, "CACHEOPS_ENABLED", True) or not cacheops:
            self.skipTest("CACHEOPS disabled (DISABLE_CACHE env or empty dict)")
        assert "user.baseuserprofile" in cacheops, (
            "CACHEOPS must register 'user.baseuserprofile' so @cached_as "
            "blocks depending on BaseUserProfile actually invalidate on PATCH "
            "to /api/users/me/profile/base/. See backend/backend/settings.py."
        )


# Files we scan. Add new files here whenever a new module starts using
# @cached_as with CustomUser deps.
SCAN_TARGETS = [
    REPO_ROOT / "backend" / "app" / "views_main.py",
    REPO_ROOT / "backend" / "app" / "functions" / "tournament.py",
    REPO_ROOT / "backend" / "app" / "user_cache.py",
]


def _customuser_blocks_missing(dep: str) -> list[str]:
    """Return formatted offender strings for every @cached_as block in
    SCAN_TARGETS that lists ``CustomUser`` but not ``dep``.

    Positions and nickname/avatar both ship on the same user-list/detail/org/
    league/draft endpoints, so any CustomUser-dependent block needs both
    BaseUserProfile (T1) and DotaUserProfile (T2) deps.
    """
    offenders = []
    for path in SCAN_TARGETS:
        assert path.exists(), f"Scan target missing: {path}"
        for start_line, block in _iter_cached_as_blocks(path):
            if "CustomUser" not in block:
                continue
            if dep not in block:
                offenders.append(
                    f"  {path.relative_to(REPO_ROOT)}:{start_line}\n"
                    f"    {block.splitlines()[0].strip()} ..."
                )
    return offenders


class CachedAsGuardrailTests(TestCase):
    """Every cacheops decorator block that depends on ``CustomUser`` MUST
    also depend on ``BaseUserProfile`` (nickname/avatar — T1 epic) AND
    ``DotaUserProfile`` (positions/dota-mmr — T2 epic). A CustomUser-only dep
    would serve stale data from cached endpoints (org rosters, tournament
    participants, draft payloads) after a PATCH to the profile-base or
    profile-game/dota endpoints.
    """

    def test_every_customuser_cached_as_block_also_lists_baseuserprofile(self):
        offenders = _customuser_blocks_missing("BaseUserProfile")
        assert not offenders, (
            "@cached_as sites depending on CustomUser but missing "
            "BaseUserProfile dep:\n"
            + "\n".join(offenders)
            + "\n\nAdd `BaseUserProfile` (from user.models) to each "
            "decorator's model list."
        )

    def test_every_customuser_cached_as_block_also_lists_dotauserprofile(self):
        """Any @cached_as(CustomUser, ...) site that ships positions must also
        depend on DotaUserProfile so a PATCH to /api/users/me/profile/game/dota/
        evicts it. Positions ship on the same user-list/detail/org/league
        endpoints that T1 guarded for BaseUserProfile, so the dependency set is
        identical."""
        offenders = _customuser_blocks_missing("DotaUserProfile")
        assert not offenders, (
            "@cached_as sites depending on CustomUser but missing "
            "DotaUserProfile dep:\n"
            + "\n".join(offenders)
            + "\n\nAdd `DotaUserProfile` (from user.models) to each "
            "decorator's model list."
        )
