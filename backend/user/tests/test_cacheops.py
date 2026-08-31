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


# Relation paths that reach a profile table owning nickname/avatar (T1) or
# positions/rank (T2) from some *other* base table.
_PROFILE_JOIN_RE = re.compile(r"base_profile|dota_user_profile|deadlock_user_profile")

# Every backend package scanned for un-nocached profile joins.
_JOIN_SCAN_ROOTS = [
    REPO_ROOT / "backend" / "app",
    REPO_ROOT / "backend" / "discordbot",
    REPO_ROOT / "backend" / "events",
    REPO_ROOT / "backend" / "league",
    REPO_ROOT / "backend" / "org",
    REPO_ROOT / "backend" / "steam",
    REPO_ROOT / "backend" / "user",
]

# Lines of slack either side of the select_related() call in which .nocache()
# may appear — it chains before the call as often as after.
_NOCACHE_WINDOW = 8


def _iter_select_related_calls(path: pathlib.Path):
    """Yield ``(start_line, end_line, call_text)`` for every
    ``select_related(...)`` call in ``path``, walking parentheses balance so
    multi-line calls are captured whole.
    """
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        match = re.search(r"select_related\s*\(", lines[i])
        if not match:
            i += 1
            continue
        start_line = i + 1
        depth = 0
        chunks = []
        j = match.end() - 1
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
            if depth == 0:
                break
            i += 1
            j = 0
        yield start_line, i + 1, "\n".join(chunks)
        i += 1


def _uncached_profile_joins() -> list[str]:
    """Offenders: ``select_related()`` calls that traverse into a profile
    table without ``.nocache()`` anywhere in the surrounding chain.
    """
    offenders = []
    for root in _JOIN_SCAN_ROOTS:
        assert root.exists(), f"Scan root missing: {root}"
        for path in sorted(root.rglob("*.py")):
            parts = path.parts
            if "tests" in parts or "migrations" in parts:
                continue
            if path.name.startswith("test_"):
                continue
            lines = path.read_text().splitlines()
            for start, end, call in _iter_select_related_calls(path):
                if not _PROFILE_JOIN_RE.search(call):
                    continue
                window = "\n".join(
                    lines[max(0, start - 1 - _NOCACHE_WINDOW) : end + _NOCACHE_WINDOW]
                )
                if ".nocache()" in window:
                    continue
                offenders.append(
                    f"  {path.relative_to(REPO_ROOT)}:{start}\n"
                    f"    {call.splitlines()[0].strip()} ..."
                )
    return offenders


class ProfileJoinNoCacheGuardrailTests(TestCase):
    """Cacheops registers an auto-cached queryset's invalidation keys against
    its *base* table only. A ``select_related()`` that joins into
    BaseUserProfile / DotaUserProfile / DeadlockUserProfile is therefore never
    evicted when those tables are written, so a PATCH to
    ``/api/users/me/profile/base/`` serves the pre-edit nickname until TTL —
    and an enclosing ``@cached_as`` does not save you: it is evicted correctly,
    then instantly repopulated from the stale inner join.

    Every such join must opt out with ``.nocache()``.
    """

    def test_profile_joins_are_nocached(self):
        offenders = _uncached_profile_joins()
        assert not offenders, (
            "select_related() joins into a profile table without .nocache():\n"
            + "\n".join(offenders)
            + "\n\nCacheops invalidates a cached JOIN only on its base table, "
            "so these serve stale nickname/avatar/positions after a profile "
            "PATCH. Chain `.nocache()` onto the queryset."
        )
