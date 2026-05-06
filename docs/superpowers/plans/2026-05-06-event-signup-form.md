# Event Signup Form — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a website signup form that collects the same data Discord collects, gated by the same per-event flags, sharing one canonical service with the Discord adapter.

**Architecture:** New shared service `apply_signup_input(org_user, event, patch)` in `events/services.py`. Single new endpoint `POST /api/events/<id>/signup/` accepting `{intent, profile}`. Discord adapters refactored to call the same shared service. Old `/rsvp/` and `/tentative/` endpoints deleted. Frontend gets `EventSignupModal` (Dialog desktop, Sheet mobile) opened from event page; skip-the-form fast path when profile already satisfies event config; `useUserDotaProfile()` query for stale-profile defense.

**Tech Stack:** Django + DRF + Pydantic, cacheops with `invalidate_after_commit`, React 19 + react-router (Vite SSR, not RSC), TanStack Query, react-hook-form + zod, shadcn `<Dialog>` / `<Sheet>` / `<RadioGroup>` (new) / `<ToggleGroup>` / `<Select>` / `<Collapsible>` / `<Badge>`, brand button system (`<SubmitButton>` / `<CancelButton>` / `<PrimaryButton>` / `<SecondaryButton>`), Playwright E2E.

**Spec:** `docs/superpowers/specs/2026-05-05-event-signup-form-design.md` (commit `abb758f7`).

---

## Phase 0 — Worktree setup

### Task 0: Create worktree and bootstrap

**Files:**
- New worktree: `/home/kettle/git_repos/draftforge/.worktrees/event-signup-form`
- New branch: `feat/event-signup-form` (off `main`)

- [ ] **Step 1: Create worktree off `main`**

```bash
git -C /home/kettle/git_repos/draftforge fetch origin main
git -C /home/kettle/git_repos/draftforge worktree add .worktrees/event-signup-form -b feat/event-signup-form origin/main
```

- [ ] **Step 2: Bootstrap (creates venv, installs deps)**

```bash
cd /home/kettle/git_repos/draftforge/.worktrees/event-signup-form && ./dev
```

- [ ] **Step 3: Copy backend secrets**

```bash
cp /home/kettle/git_repos/draftforge/backend/.env /home/kettle/git_repos/draftforge/.worktrees/event-signup-form/backend/.env
```

- [ ] **Step 4: Cherry-pick spec onto the new branch so it's accessible during implementation**

```bash
cd /home/kettle/git_repos/draftforge/.worktrees/event-signup-form && git cherry-pick abb758f7
```

If the cherry-pick fails because the spec already exists at the same path, skip — it's already in main once `feat/discord-embed-cap-194` lands. Otherwise resolve and continue.

- [ ] **Step 5: Run migrations and populate**

```bash
cd /home/kettle/git_repos/draftforge/.worktrees/event-signup-form && just db::migrate::all && just db::populate::all
```

All steps after this run from `/home/kettle/git_repos/draftforge/.worktrees/event-signup-form`. Use `cd` (not `git -C`) per project convention for worktrees.

---

## Phase 1 — Populate fixtures (must come first; later tests need this data)

### Task 1: Add `event_player_no_profile` user fixture

**Files:**
- Modify: `backend/tests/data/users.py` (after `event_player_18`, ~line 654)

- [ ] **Step 1: Append the new fixture user**

```python
event_player_no_profile = UserFixture(
    username="event_player_no_profile",
    email="event_player_no_profile@kettle.sh",
    discord_id="9999900000000001",
    nickname="No-Profile Player",
    positions=None,
)
```

- [ ] **Step 2: Add to the module's `USERS` list** (find the exporter and append)

```bash
grep -n "USERS\s*=\|USERS:\s*list" backend/tests/data/users.py
```

If `USERS` is a top-level list, append `event_player_no_profile`. If exporter uses `__all__`, add to `__all__`.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/data/users.py
git commit -m "test(populate): add event_player_no_profile fixture"
```

### Task 2: Add Deadlock event + screenshot-required Dota event + no-profile player to populate

**Files:**
- Modify: `backend/tests/populate/events.py`

- [ ] **Step 1: Create `event_player_no_profile` `OrgUser` (no `PlayerDotaProfile`)**

Locate the section that creates `OrgUser` rows for `event_player_*` (around line 100-120 based on grep) and add a branch that creates an `OrgUser` for `event_player_no_profile` *without* creating a `PlayerDotaProfile`.

```python
# After the existing event_player loop:
no_profile_user = CustomUser.objects.get(username="event_player_no_profile")
OrgUser.objects.update_or_create(
    user=no_profile_user, organization=org_7,
    defaults={"role": OrgUserRole.MEMBER},
)
# Intentionally do NOT create a PlayerDotaProfile — this is the empty-profile fixture.
```

- [ ] **Step 2: Add a Deadlock event with `require_steam_id=true` to org 7**

```python
deadlock_event = Event.objects.update_or_create(
    name="Test Deadlock Event",
    organization=org_7,
    defaults={
        "game_type": GameType.DEADLOCK,
        "scheduled_at": now() + timedelta(days=7),
        "state": EventState.SIGNUPS_OPEN,
        "require_steam_id": True,
        "min_players": 2, "max_players": 12,
        "people_per_team": 6, "number_of_teams": 2,
    },
)[0]
```

- [ ] **Step 3: Add a Dota 2 event with `discord_require_rank_screenshot=true`**

```python
dota_screenshot_event = Event.objects.update_or_create(
    name="Test Dota Event With Screenshot",
    organization=org_7,
    defaults={
        "game_type": GameType.DOTA2,
        "scheduled_at": now() + timedelta(days=7),
        "state": EventState.SIGNUPS_OPEN,
        "require_steam_id": True,
        "discord_require_rank_screenshot": True,
        "allow_active_mmr": True, "allow_previous_rank": True, "allow_battlecup_rating": True,
        "min_players": 2, "max_players": 10,
        "people_per_team": 5, "number_of_teams": 2,
    },
)[0]
```

- [ ] **Step 4: Run populate and verify both events + the no-profile user exist**

```bash
just db::populate::all
just db::run -- python manage.py shell -c "from events.models import Event; from app.models import CustomUser; print(Event.objects.filter(name__icontains='Test Deadlock').count(), Event.objects.filter(name__icontains='Test Dota Event With Screenshot').count(), CustomUser.objects.filter(username='event_player_no_profile').exists())"
```

Expected output: `1 1 True`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/populate/events.py
git commit -m "test(populate): add deadlock event + screenshot-required dota event + no-profile org user"
```

---

## Phase 2 — Pydantic schema for the patch payload

### Task 3: Add `SignupInputPatch` Pydantic model

**Files:**
- Modify: `backend/events/schemas.py`
- Test: `backend/events/tests/test_signup_schema.py` (new)

- [ ] **Step 1: Write failing test**

```python
# backend/events/tests/test_signup_schema.py
from pydantic import ValidationError as PydanticValidationError
import pytest

from events.schemas import SignupInputPatch


def test_empty_patch_parses():
    patch = SignupInputPatch()
    assert patch.model_dump(exclude_unset=True) == {}


def test_full_patch_parses():
    patch = SignupInputPatch(
        unverified_friend_id="12345678",
        positions=[1, 2, 3],
        rank_status="active",
        rank_medal="Crusader 3",
        battle_cup_tier=None,
        rank_screenshot="https://i.imgur.com/abc.png",
    )
    assert patch.rank_status == "active"
    assert patch.positions == [1, 2, 3]


def test_rank_status_rejects_invalid():
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(rank_status="bogus")


def test_battle_cup_tier_range():
    SignupInputPatch(battle_cup_tier=8)
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(battle_cup_tier=9)
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(battle_cup_tier=0)


def test_positions_range():
    SignupInputPatch(positions=[1, 5])
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(positions=[0])
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(positions=[6])
```

- [ ] **Step 2: Run test, verify fail**

```bash
just test::run 'python manage.py test events.tests.test_signup_schema -v 2'
```

Expected: ImportError on `SignupInputPatch`.

- [ ] **Step 3: Implement model in `backend/events/schemas.py`** (append at end)

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class SignupInputPatch(BaseModel):
    """Profile patch sent by web/Discord callers to apply_signup_input.

    All fields optional — callers send only what changed. Validation rules:
    - rank_status must be one of the allowed literals (event-policy gating
      lives in apply_signup_input, not here).
    - positions in {1..5}, deduped (deduping handled in service).
    - battle_cup_tier in {1..8}.
    - URL fields are validated for shape + extension in apply_signup_input
      so we keep the message strings consistent with the Discord vocabulary.
    """

    model_config = ConfigDict(extra="forbid")

    unverified_friend_id: Optional[str] = Field(default=None, max_length=20)
    positions: Optional[list[int]] = None
    rank_status: Optional[Literal["active", "previous", "never"]] = None
    rank_medal: Optional[str] = Field(default=None, max_length=64)
    battle_cup_tier: Optional[int] = Field(default=None, ge=1, le=8)
    rank_screenshot: Optional[str] = Field(default=None, max_length=500)
    battlecup_screenshot: Optional[str] = Field(default=None, max_length=500)

    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()

    def model_post_init(self, __context):
        if self.positions is not None:
            for p in self.positions:
                if p < 1 or p > 5:
                    from pydantic import ValidationError
                    raise ValueError(f"position {p} out of range 1..5")
```

The position-range check is in `model_post_init` because Pydantic doesn't natively validate list-element ranges in the field declaration. (Note: `model_post_init` raising `ValueError` produces a `ValidationError` from Pydantic's perspective — that's what the test catches.)

- [ ] **Step 4: Run test, verify pass**

```bash
just test::run 'python manage.py test events.tests.test_signup_schema -v 2'
```

- [ ] **Step 5: Commit**

```bash
git add backend/events/schemas.py backend/events/tests/test_signup_schema.py
git commit -m "feat(events): add SignupInputPatch pydantic model"
```

---

## Phase 3 — `resolve_or_create_org_user` extraction

### Task 4: Extract `resolve_or_create_org_user` and migrate callers

**Files:**
- Modify: `backend/events/services.py` (add new function near top)
- Modify: `backend/events/discord/handlers.py` (`_get_org_user` delegates to new helper)
- Modify: `backend/events/services.py` (`staff_add_signup` and `approve_signup` use new helper)
- Test: `backend/events/tests/test_resolve_or_create_org_user.py` (new)

- [ ] **Step 1: Write failing test**

```python
# backend/events/tests/test_resolve_or_create_org_user.py
from django.test import TestCase
from app.models import CustomUser
from app.organization import Organization
from org.models import OrgUser
from events.services import resolve_or_create_org_user


class ResolveOrCreateOrgUserTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="u1")
        self.org = Organization.objects.create(name="Org 1")

    def test_creates_when_missing(self):
        org_user = resolve_or_create_org_user(self.user, self.org)
        self.assertIsInstance(org_user, OrgUser)
        self.assertEqual(org_user.user, self.user)
        self.assertEqual(org_user.organization, self.org)

    def test_reuses_existing(self):
        existing = OrgUser.objects.create(user=self.user, organization=self.org)
        org_user = resolve_or_create_org_user(self.user, self.org)
        self.assertEqual(org_user.pk, existing.pk)

    def test_idempotent(self):
        a = resolve_or_create_org_user(self.user, self.org)
        b = resolve_or_create_org_user(self.user, self.org)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(OrgUser.objects.filter(user=self.user, organization=self.org).count(), 1)
```

- [ ] **Step 2: Run test, verify fail**

```bash
just test::run 'python manage.py test events.tests.test_resolve_or_create_org_user -v 2'
```

- [ ] **Step 3: Implement in `backend/events/services.py`** (add near other helpers)

```python
def resolve_or_create_org_user(user, organization):
    """Get or create OrgUser for (user, organization). Used by every signup path
    (web endpoint, Discord adapters via _get_org_user, staff_add_signup, approve_signup).
    """
    from org.models import OrgUser
    org_user, _ = OrgUser.objects.get_or_create(user=user, organization=organization)
    return org_user
```

- [ ] **Step 4: Migrate `_get_org_user` in `backend/events/discord/handlers.py`** to delegate

Find the existing `OrgUser.objects.get_or_create(user=user, organization=event.organization)` line inside `_get_org_user` and replace with `org_user = resolve_or_create_org_user(user, event.organization)`. Add `from events.services import resolve_or_create_org_user` at the top of the file.

- [ ] **Step 5: Migrate `staff_add_signup` and `approve_signup` in `backend/events/services.py`**

Find the `OrgUser.objects.get_or_create(user=user, organization=event.organization)` (or similar) calls inside these two functions and replace with `resolve_or_create_org_user(user, event.organization)` (or `signup.event.organization` for `approve_signup`).

- [ ] **Step 6: Run all events tests to verify no regressions**

```bash
just test::run 'python manage.py test events -v 2'
```

- [ ] **Step 7: Commit**

```bash
git add backend/events/services.py backend/events/discord/handlers.py backend/events/tests/test_resolve_or_create_org_user.py
git commit -m "refactor(events): extract resolve_or_create_org_user; migrate _get_org_user, staff_add_signup, approve_signup"
```

---

## Phase 4 — `apply_signup_input` shared service

This phase adds the service in TDD slices: one rule at a time, each its own test + commit. The function lives in `backend/events/services.py`. Tests live in `backend/events/tests/test_signup_input.py`.

### Task 5: Skeleton — empty patch is a no-op

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py` (new)

- [ ] **Step 1: Write failing test**

```python
# backend/events/tests/test_signup_input.py
from django.test import TestCase
from app.models import CustomUser, GameType
from app.organization import Organization
from events.models import Event, EventState
from events.services import apply_signup_input, resolve_or_create_org_user
from events.schemas import SignupInputPatch
from org.models_profiles import PlayerDotaProfile


class ApplySignupInputTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="alice")
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt", organization=self.org, game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True, allow_previous_rank=True, allow_battlecup_rating=True,
        )
        self.org_user = resolve_or_create_org_user(self.user, self.org)

    def test_empty_patch_is_noop(self):
        before = PlayerDotaProfile.objects.filter(org_user=self.org_user).count()
        result = apply_signup_input(org_user=self.org_user, event=self.event, patch=SignupInputPatch())
        after = PlayerDotaProfile.objects.filter(org_user=self.org_user).count()
        # Empty patch may create the profile row or not; either is acceptable as
        # long as no fields were written to surprising values.
        if result is not None:
            self.assertEqual(result.org_user, self.org_user)
        self.assertEqual(after, before if result is None else before + 1)
```

- [ ] **Step 2: Run, verify fail (ImportError on `apply_signup_input`)**

```bash
just test::run 'python manage.py test events.tests.test_signup_input.ApplySignupInputTests.test_empty_patch_is_noop -v 2'
```

- [ ] **Step 3: Implement skeleton in `backend/events/services.py`**

```python
def apply_signup_input(*, org_user, event, patch):
    """Idempotently write any provided fields onto the OrgUser's PlayerDotaProfile.

    Fields not in `patch` are not touched. Validates against `event` config flags
    and raises django.core.exceptions.ValidationError on policy violations.
    Cacheops invalidation is registered via invalidate_after_commit.
    """
    from org.models_profiles import PlayerDotaProfile
    from app.cache_utils import invalidate_after_commit
    from django.db import transaction

    set_fields = patch.model_dump(exclude_unset=True)
    if not set_fields:
        return None

    # Will be filled out in subsequent tasks.
    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    profile.save()
    transaction.on_commit(lambda: invalidate_after_commit(profile, org_user, event))
    return profile
```

- [ ] **Step 4: Run, verify pass**

```bash
just test::run 'python manage.py test events.tests.test_signup_input.ApplySignupInputTests.test_empty_patch_is_noop -v 2'
```

- [ ] **Step 5: Commit**

```bash
git add backend/events/services.py backend/events/tests/test_signup_input.py
git commit -m "feat(events): apply_signup_input skeleton (empty patch no-op)"
```

### Task 6: Friend ID write

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append failing test**

```python
def test_writes_friend_id(self):
    apply_signup_input(
        org_user=self.org_user, event=self.event,
        patch=SignupInputPatch(unverified_friend_id="12345678"),
    )
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.unverified_friend_id, "12345678")
```

- [ ] **Step 2: Run, verify fail**

```bash
just test::run 'python manage.py test events.tests.test_signup_input.ApplySignupInputTests.test_writes_friend_id -v 2'
```

- [ ] **Step 3: Implement (update `apply_signup_input`)**

```python
def apply_signup_input(*, org_user, event, patch):
    from org.models_profiles import PlayerDotaProfile
    from app.cache_utils import invalidate_after_commit
    from django.db import transaction

    set_fields = patch.model_dump(exclude_unset=True)
    if not set_fields:
        return None

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)

    if "unverified_friend_id" in set_fields:
        profile.unverified_friend_id = set_fields["unverified_friend_id"]

    profile.save()
    transaction.on_commit(lambda: invalidate_after_commit(profile, org_user, event))
    return profile
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/events/services.py backend/events/tests/test_signup_input.py
git commit -m "feat(events): apply_signup_input writes unverified_friend_id"
```

### Task 7: Positions write (with dedup)

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append failing test**

```python
def test_writes_positions_and_dedups(self):
    apply_signup_input(
        org_user=self.org_user, event=self.event,
        patch=SignupInputPatch(positions=[1, 3, 3, 5]),
    )
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertTrue(profile.pos_1)
    self.assertFalse(profile.pos_2)
    self.assertTrue(profile.pos_3)
    self.assertFalse(profile.pos_4)
    self.assertTrue(profile.pos_5)
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Add positions branch to `apply_signup_input`** (between Friend ID and `save()`)

```python
    if "positions" in set_fields:
        positions = set(set_fields["positions"] or [])
        profile.pos_1 = 1 in positions
        profile.pos_2 = 2 in positions
        profile.pos_3 = 3 in positions
        profile.pos_4 = 4 in positions
        profile.pos_5 = 5 in positions
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(events): apply_signup_input writes positions with dedup"
```

### Task 8: rank_status write with policy validation

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append failing tests**

```python
from django.core.exceptions import ValidationError as DjangoValidationError


def test_rank_status_active_writes(self):
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(rank_status="active"))
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.rank_status, "active")


def test_rank_status_disallowed_raises(self):
    self.event.allow_active_mmr = False
    self.event.save()
    with self.assertRaises(DjangoValidationError) as ctx:
        apply_signup_input(org_user=self.org_user, event=self.event,
                           patch=SignupInputPatch(rank_status="active"))
    self.assertEqual(ctx.exception.code, "rank_status_disallowed")
    self.assertIn("active MMR signups", str(ctx.exception))
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Add rank_status branch + error vocabulary table**

Add at module level in `services.py`:

```python
RANK_STATUS_DISALLOWED_MESSAGES = {
    "active": "This event does not accept active MMR signups.",
    "previous": "This event does not accept previous-rank signups.",
    "never": "This event does not accept Battle Cup–only signups.",
}
```

In `apply_signup_input`, between positions and `save()`:

```python
    from django.core.exceptions import ValidationError

    if "rank_status" in set_fields:
        status = set_fields["rank_status"]
        allowed = (
            (status == "active" and event.allow_active_mmr) or
            (status == "previous" and event.allow_previous_rank) or
            (status == "never" and event.allow_battlecup_rating)
        )
        if not allowed:
            raise ValidationError(
                RANK_STATUS_DISALLOWED_MESSAGES[status],
                code="rank_status_disallowed",
            )
        profile.rank_status = status
```

- [ ] **Step 4: Run both tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(events): apply_signup_input writes rank_status with policy validation"
```

### Task 9: rank_medal + battle_cup_tier writes

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append failing tests**

```python
def test_rank_medal_writes(self):
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(rank_medal="Crusader 3"))
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.rank_medal, "Crusader 3")


def test_battle_cup_tier_writes(self):
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(battle_cup_tier=5))
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.battle_cup_tier, 5)
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Add branches in `apply_signup_input`**

```python
    if "rank_medal" in set_fields:
        profile.rank_medal = set_fields["rank_medal"] or ""

    if "battle_cup_tier" in set_fields:
        profile.battle_cup_tier = set_fields["battle_cup_tier"]
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(events): apply_signup_input writes rank_medal and battle_cup_tier"
```

### Task 10: Screenshot URL writes with shape + extension validation

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append failing tests**

```python
def test_rank_screenshot_writes(self):
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(rank_screenshot="https://i.imgur.com/abc.png"))
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.rank_screenshot, "https://i.imgur.com/abc.png")


def test_screenshot_bad_shape_raises(self):
    with self.assertRaises(DjangoValidationError) as ctx:
        apply_signup_input(org_user=self.org_user, event=self.event,
                           patch=SignupInputPatch(rank_screenshot="ftp://example.com/x.png"))
    self.assertEqual(ctx.exception.code, "screenshot_bad_url")


def test_screenshot_bad_extension_raises(self):
    with self.assertRaises(DjangoValidationError):
        apply_signup_input(org_user=self.org_user, event=self.event,
                           patch=SignupInputPatch(rank_screenshot="https://i.imgur.com/abc.gif"))


def test_battlecup_screenshot_writes(self):
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(battlecup_screenshot="https://i.imgur.com/bc.jpg"))
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.battlecup_screenshot, "https://i.imgur.com/bc.jpg")
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Add screenshot validator helper + branches**

In `services.py`:

```python
import re

SCREENSHOT_URL_RE = re.compile(r"^https?://.+\.(png|jpe?g|webp)(\?.*)?$", re.IGNORECASE)
SCREENSHOT_BAD_URL_MESSAGE = "Screenshot must be a direct .png/.jpg/.jpeg/.webp URL."


def _validate_screenshot_url(url):
    if url and not SCREENSHOT_URL_RE.match(url):
        from django.core.exceptions import ValidationError
        raise ValidationError(SCREENSHOT_BAD_URL_MESSAGE, code="screenshot_bad_url")
```

In `apply_signup_input`:

```python
    if "rank_screenshot" in set_fields:
        _validate_screenshot_url(set_fields["rank_screenshot"])
        profile.rank_screenshot = set_fields["rank_screenshot"] or ""

    if "battlecup_screenshot" in set_fields:
        _validate_screenshot_url(set_fields["battlecup_screenshot"])
        profile.battlecup_screenshot = set_fields["battlecup_screenshot"] or ""
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(events): apply_signup_input writes screenshots with URL+extension validation"
```

### Task 11: Duplicate Friend ID check

**Files:**
- Modify: `backend/events/services.py`
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append failing test**

```python
def test_duplicate_friend_id_raises(self):
    bob = CustomUser.objects.create(username="bob")
    bob_org_user = resolve_or_create_org_user(bob, self.org)
    PlayerDotaProfile.objects.create(org_user=bob_org_user, unverified_friend_id="9999")
    with self.assertRaises(DjangoValidationError) as ctx:
        apply_signup_input(org_user=self.org_user, event=self.event,
                           patch=SignupInputPatch(unverified_friend_id="9999"))
    self.assertEqual(ctx.exception.code, "duplicate_friend_id")
    self.assertIn("9999", str(ctx.exception))
    self.assertIn("dota.kettle.sh", str(ctx.exception))
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Add the check at the top of the Friend ID branch in `apply_signup_input`**

```python
    if "unverified_friend_id" in set_fields:
        fid = set_fields["unverified_friend_id"]
        if fid:
            collision = (
                PlayerDotaProfile.objects
                .filter(org_user__organization=event.organization, unverified_friend_id=fid)
                .exclude(org_user=org_user)
                .exists()
            )
            if collision:
                from django.core.exceptions import ValidationError
                raise ValidationError(
                    f"Friend ID {fid} is already registered to another player. "
                    f"Contact an admin or login to https://dota.kettle.sh to claim it.",
                    code="duplicate_friend_id",
                )
        profile.unverified_friend_id = fid
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(events): apply_signup_input rejects duplicate friend_id with vocabulary message"
```

### Task 12: Multi-call partial-patch contract test

**Files:**
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append test**

```python
def test_multi_call_partial_patch_accumulates(self):
    # Mirror Discord's 4-turn flow.
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(rank_status="active"))
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(positions=[1, 2]))
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(rank_medal="Legend 4"))
    apply_signup_input(org_user=self.org_user, event=self.event,
                       patch=SignupInputPatch(rank_screenshot="https://i.imgur.com/x.png"))
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.rank_status, "active")
    self.assertTrue(profile.pos_1 and profile.pos_2)
    self.assertFalse(profile.pos_3)
    self.assertEqual(profile.rank_medal, "Legend 4")
    self.assertEqual(profile.rank_screenshot, "https://i.imgur.com/x.png")


def test_idempotent_re_application(self):
    patch = SignupInputPatch(rank_status="active", positions=[3])
    apply_signup_input(org_user=self.org_user, event=self.event, patch=patch)
    apply_signup_input(org_user=self.org_user, event=self.event, patch=patch)
    self.assertEqual(PlayerDotaProfile.objects.filter(org_user=self.org_user).count(), 1)
    profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
    self.assertEqual(profile.rank_status, "active")
    self.assertTrue(profile.pos_3)
```

- [ ] **Step 2: Run both, verify pass (no implementation needed — multi-call is already supported)**

```bash
just test::run 'python manage.py test events.tests.test_signup_input -v 2'
```

- [ ] **Step 3: Commit**

```bash
git commit -am "test(events): pin multi-call partial-patch contract and idempotency"
```

### Task 13: Cacheops invalidation test

**Files:**
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append test**

```python
from unittest.mock import patch as mock_patch


def test_cacheops_invalidation_after_commit(self):
    with mock_patch("events.services.invalidate_after_commit") as spy:
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_status="active"),
        )
    # After the test method's outer transaction commits (TestCase wraps each test
    # in atomic), invalidate_after_commit is called once with (profile, org_user, event).
    # We can't intercept the on_commit callback directly here, so we patch the
    # symbol the service calls and assert it received the right args.
    spy.assert_called_once()
    args, kwargs = spy.call_args
    # Allow either positional or keyword call style.
    objs = list(args)
    self.assertEqual(len(objs), 3)
```

- [ ] **Step 2: Update `apply_signup_input` so the import is at module-level (so the patch works)**

In `services.py`, replace `from app.cache_utils import invalidate_after_commit` inside the function with a top-level `from app.cache_utils import invalidate_after_commit`. The `transaction.on_commit(lambda: invalidate_after_commit(...))` line stays.

Note: `transaction.on_commit` callbacks fire when the outer test-case transaction commits, which never happens under `TestCase`. To force the callback to fire so the spy sees it, wrap the call in `self.captureOnCommitCallbacks(execute=True)`:

```python
def test_cacheops_invalidation_after_commit(self):
    with mock_patch("events.services.invalidate_after_commit") as spy:
        with self.captureOnCommitCallbacks(execute=True):
            apply_signup_input(
                org_user=self.org_user, event=self.event,
                patch=SignupInputPatch(rank_status="active"),
            )
    spy.assert_called_once()
    args, kwargs = spy.call_args
    self.assertEqual(len(args), 3)
```

- [ ] **Step 3: Run, verify pass**

- [ ] **Step 4: Commit**

```bash
git commit -am "test(events): pin invalidate_after_commit fires with (profile, org_user, event)"
```

### Task 14: Rollback test — invalidations not fired on rollback

**Files:**
- Test: `backend/events/tests/test_signup_input.py`

- [ ] **Step 1: Append test**

```python
from django.db import transaction


def test_rollback_does_not_fire_invalidation(self):
    with mock_patch("events.services.invalidate_after_commit") as spy:
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    apply_signup_input(
                        org_user=self.org_user, event=self.event,
                        patch=SignupInputPatch(rank_status="active"),
                    )
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
    spy.assert_not_called()
```

- [ ] **Step 2: Run, verify pass**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(events): pin invalidate_after_commit not fired on rollback"
```

---

## Phase 5 — `create_tentative_signup` service

### Task 15: Extract `create_tentative_signup`

**Files:**
- Modify: `backend/events/services.py`
- Modify: `backend/events/views.py` (the existing `tentative` action delegates; will be deleted in Task 33)
- Test: `backend/events/tests/test_create_tentative_signup.py` (new)

- [ ] **Step 1: Write failing test**

```python
# backend/events/tests/test_create_tentative_signup.py
from django.test import TestCase
from app.models import CustomUser, GameType
from app.organization import Organization
from events.models import Event, EventState, EventSignup, SignupStatus
from events.services import create_tentative_signup


class CreateTentativeSignupTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="alice")
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt", organization=self.org, game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
        )

    def test_creates_tentative_signup(self):
        signup = create_tentative_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(signup.user, self.user)

    def test_rejects_duplicate_active_signup(self):
        EventSignup.objects.create(event=self.event, user=self.user, status=SignupStatus.RSVP)
        with self.assertRaises(ValueError):
            create_tentative_signup(self.event, self.user)

    def test_cleans_up_cancelled_row(self):
        EventSignup.objects.create(event=self.event, user=self.user, status=SignupStatus.CANCELLED)
        signup = create_tentative_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(EventSignup.objects.filter(event=self.event, user=self.user).count(), 1)
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement in `services.py`**

```python
def create_tentative_signup(event, user):
    """Create a TENTATIVE EventSignup. Mirrors the inline logic previously in
    EventViewSet.tentative (views.py:486-525)."""
    from events.models import EventSignup, SignupStatus, EventState
    from events.discord.dispatch import notify_signup_changed
    from app.cache_utils import invalidate_after_commit
    from django.db import transaction

    if event.state != EventState.SIGNUPS_OPEN:
        raise ValueError("Event is not accepting signups")

    existing = (
        EventSignup.objects.filter(event=event, user=user)
        .exclude(status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED])
        .first()
    )
    if existing:
        if existing.status == SignupStatus.TENTATIVE:
            raise ValueError("Already marked as tentative")
        raise ValueError(f"Already signed up (status: {existing.status})")

    EventSignup.objects.filter(
        event=event, user=user,
        status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED],
    ).delete()

    signup = EventSignup.objects.create(event=event, user=user, status=SignupStatus.TENTATIVE)
    transaction.on_commit(lambda: invalidate_after_commit(signup, event))
    transaction.on_commit(lambda: notify_signup_changed(event))
    return signup
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/events/services.py backend/events/tests/test_create_tentative_signup.py
git commit -m "feat(events): extract create_tentative_signup service"
```

---

## Phase 6 — New `POST /api/events/<id>/signup/` endpoint

### Task 16: Endpoint skeleton — auth + state + body validation

**Files:**
- Modify: `backend/events/views.py` (add `signup` action)
- Test: `backend/events/tests/test_signup_endpoint.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# backend/events/tests/test_signup_endpoint.py
from django.test import TestCase
from rest_framework.test import APIClient
from app.models import CustomUser, GameType
from app.organization import Organization
from events.models import Event, EventState


class SignupEndpointAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt", organization=self.org, game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True, allow_previous_rank=True, allow_battlecup_rating=True,
        )

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(f"/api/events/{self.event.pk}/signup/", {"intent": "rsvp"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_wrong_state_returns_400(self):
        self.event.state = EventState.CLOSED
        self.event.save()
        user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(user)
        resp = self.client.post(f"/api/events/{self.event.pk}/signup/", {"intent": "rsvp"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not accepting signups", resp.json()["error"])

    def test_invalid_intent_returns_400(self):
        user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(user)
        resp = self.client.post(f"/api/events/{self.event.pk}/signup/", {"intent": "bogus"}, format="json")
        self.assertEqual(resp.status_code, 400)
```

- [ ] **Step 2: Run, verify fail (404 / 405 because action doesn't exist)**

```bash
just test::run 'python manage.py test events.tests.test_signup_endpoint.SignupEndpointAuthTests -v 2'
```

- [ ] **Step 3: Implement the action on `EventViewSet`** (in `views.py`, near other actions)

```python
@action(
    detail=True, methods=["post"],
    permission_classes=[permissions.IsAuthenticated],
)
def signup(self, request, pk=None):
    from django.db import transaction
    from events.schemas import SignupInputPatch
    from events.services import (
        apply_signup_input, create_tentative_signup, process_rsvp,
        resolve_or_create_org_user,
    )
    from pydantic import ValidationError as PydanticValidationError
    from django.core.exceptions import ValidationError as DjangoValidationError

    event = self.get_object()
    if event.state != EventState.SIGNUPS_OPEN:
        return Response({"error": "Event is not accepting signups"}, status=400)

    body = request.data or {}
    intent = body.get("intent")
    if intent not in ("rsvp", "tentative"):
        return Response({"error": "intent must be 'rsvp' or 'tentative'"}, status=400)

    try:
        patch = SignupInputPatch(**(body.get("profile") or {}))
    except PydanticValidationError as exc:
        return Response({"error": str(exc)}, status=400)

    org_user = resolve_or_create_org_user(request.user, event.organization)

    try:
        with transaction.atomic():
            apply_signup_input(org_user=org_user, event=event, patch=patch)
            if intent == "rsvp":
                signup = process_rsvp(event, request.user)
            else:
                signup = create_tentative_signup(event, request.user)
    except DjangoValidationError as exc:
        return Response({"error": exc.messages[0] if hasattr(exc, "messages") else str(exc)}, status=400)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)

    return Response(EventSignupSerializer(signup).data, status=201)
```

- [ ] **Step 4: Run, verify the three auth/state/body tests pass**

- [ ] **Step 5: Commit**

```bash
git add backend/events/views.py backend/events/tests/test_signup_endpoint.py
git commit -m "feat(events): add POST /signup/ endpoint skeleton (auth, state, body validation)"
```

### Task 17: Endpoint happy paths — rsvp + tentative

**Files:**
- Test: `backend/events/tests/test_signup_endpoint.py`

- [ ] **Step 1: Append failing tests**

```python
class SignupEndpointHappyPathTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt", organization=self.org, game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True, allow_previous_rank=True, allow_battlecup_rating=True,
            min_players=2, max_players=10,
        )
        self.user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(self.user)

    def test_empty_patch_creates_signup(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "rsvp", "profile": {}}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn("status", resp.json())

    def test_full_patch_creates_signup_and_writes_profile(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {
                "intent": "rsvp",
                "profile": {
                    "unverified_friend_id": "12345",
                    "positions": [1, 2],
                    "rank_status": "active",
                    "rank_medal": "Legend 4",
                },
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        from org.models_profiles import PlayerDotaProfile
        from org.models import OrgUser
        org_user = OrgUser.objects.get(user=self.user, organization=self.org)
        profile = PlayerDotaProfile.objects.get(org_user=org_user)
        self.assertEqual(profile.unverified_friend_id, "12345")
        self.assertEqual(profile.rank_medal, "Legend 4")

    def test_tentative_intent_creates_tentative_signup(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "tentative"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        from events.models import EventSignup, SignupStatus
        signup = EventSignup.objects.get(event=self.event, user=self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
```

- [ ] **Step 2: Run, verify pass (skeleton already supports these)**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(events): pin signup endpoint happy paths"
```

### Task 18: Endpoint transactional rollback test

**Files:**
- Test: `backend/events/tests/test_signup_endpoint.py`

- [ ] **Step 1: Append test**

```python
from django.test import TransactionTestCase


class SignupEndpointRollbackTests(TransactionTestCase):
    def test_min_mmr_failure_rolls_back_profile_write(self):
        from app.models import CustomUser, GameType
        from app.organization import Organization
        from events.models import Event, EventState
        from org.models_profiles import PlayerDotaProfile
        from org.models import OrgUser

        org = Organization.objects.create(name="Org")
        event = Event.objects.create(
            name="Evt", organization=org, game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN, min_mmr=5000,
            allow_active_mmr=True, allow_previous_rank=True, allow_battlecup_rating=True,
        )
        user = CustomUser.objects.create(username="alice")
        client = APIClient()
        client.force_authenticate(user)

        resp = client.post(
            f"/api/events/{event.pk}/signup/",
            {
                "intent": "rsvp",
                "profile": {"rank_status": "active", "rank_medal": "Herald 1"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        # Profile write must have rolled back.
        org_user = OrgUser.objects.filter(user=user, organization=org).first()
        if org_user:
            self.assertFalse(PlayerDotaProfile.objects.filter(org_user=org_user).exists())
```

(`process_rsvp` raises `ValueError` when `min_mmr` floor isn't met — confirm by reading `services.py` for the exact behavior; if the gate is screenshot-based instead, swap to a screenshot-required event with no screenshot in the patch.)

- [ ] **Step 2: Run, verify pass**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(events): pin signup endpoint transactional rollback"
```

### Task 19: `notify_signup_changed` fires once after commit (not double-fire)

**Files:**
- Test: `backend/events/tests/test_signup_endpoint.py`

- [ ] **Step 1: Append test**

```python
def test_notify_signup_changed_fires_once_after_commit(self):
    from app.models import CustomUser, GameType
    from app.organization import Organization
    from events.models import Event, EventState
    from unittest.mock import patch as mock_patch

    org = Organization.objects.create(name="Org")
    event = Event.objects.create(
        name="Evt", organization=org, game_type=GameType.DOTA2,
        state=EventState.SIGNUPS_OPEN,
        allow_active_mmr=True, allow_previous_rank=True, allow_battlecup_rating=True,
    )
    user = CustomUser.objects.create(username="alice")
    client = APIClient()
    client.force_authenticate(user)

    with mock_patch("events.services.notify_signup_changed") as spy:
        resp = client.post(
            f"/api/events/{event.pk}/signup/",
            {"intent": "rsvp"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)

    # TransactionTestCase commits writes, so on_commit callbacks fire.
    self.assertEqual(spy.call_count, 1)
```

(This is in the `TransactionTestCase` class from Task 18 because real commit is needed for `on_commit` callbacks to fire.)

- [ ] **Step 2: Run, verify pass**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(events): pin notify_signup_changed fires exactly once after commit"
```

### Task 20: Discord-then-web idempotency (race test)

**Files:**
- Test: `backend/events/tests/test_signup_endpoint.py`

- [ ] **Step 1: Append test (in `TransactionTestCase` class)**

```python
def test_discord_then_web_idempotent(self):
    from app.models import CustomUser, GameType
    from app.organization import Organization
    from events.models import Event, EventState, EventSignup
    from events.services import process_rsvp

    org = Organization.objects.create(name="Org")
    event = Event.objects.create(
        name="Evt", organization=org, game_type=GameType.DOTA2,
        state=EventState.SIGNUPS_OPEN,
        allow_active_mmr=True, allow_previous_rank=True, allow_battlecup_rating=True,
    )
    user = CustomUser.objects.create(username="alice")
    # Simulate Discord-side signup first.
    process_rsvp(event, user)
    # Now web tries to sign up.
    client = APIClient()
    client.force_authenticate(user)
    resp = client.post(f"/api/events/{event.pk}/signup/", {"intent": "rsvp"}, format="json")
    self.assertEqual(resp.status_code, 400)
    self.assertEqual(EventSignup.objects.filter(event=event, user=user).count(), 1)
```

- [ ] **Step 2: Run, verify pass**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(events): pin discord-then-web signup idempotency"
```

---

## Phase 7 — Discord adapter refactor (using shared service)

### Task 21: Refactor `handle_signup_modal_submit` to call `apply_signup_input`

**Files:**
- Modify: `backend/events/discord/handlers.py` (`handle_signup_modal_submit`)
- Modify: `backend/events/tests/test_signup_interactions.py` (assert spy)

- [ ] **Step 1: Add a spy assertion to an existing happy-path test in `test_signup_interactions.py`**

Find a test that exercises `handle_signup_modal_submit` with full values. Wrap its inner call:

```python
from unittest.mock import patch as mock_patch

with mock_patch("events.discord.handlers.apply_signup_input") as spy:
    result = handle_signup_modal_submit(...)
spy.assert_called_once()
patch_arg = spy.call_args.kwargs["patch"]
self.assertEqual(patch_arg.unverified_friend_id, ...)  # whatever the test passed
```

- [ ] **Step 2: Run the test, verify fail (handler doesn't call `apply_signup_input` yet)**

- [ ] **Step 3: Refactor `handle_signup_modal_submit`**

Replace the inline `_save_dota_profile(...)` call (and the duplicate-Friend-ID block) with:

```python
from events.services import apply_signup_input
from events.schemas import SignupInputPatch
from django.core.exceptions import ValidationError as DjangoValidationError

# Build patch from values dict
patch_kwargs = {}
if values.get("unverified_friend_id"):
    patch_kwargs["unverified_friend_id"] = values["unverified_friend_id"]
if values.get("positions"):
    patch_kwargs["positions"] = values["positions"]
if values.get("rank_status"):
    patch_kwargs["rank_status"] = values["rank_status"]
patch = SignupInputPatch(**patch_kwargs)

try:
    apply_signup_input(org_user=org_user, event=event, patch=patch)
except DjangoValidationError as exc:
    return {"action": "error", "message": exc.messages[0] if hasattr(exc, "messages") else str(exc)}
```

- [ ] **Step 4: Run modified test + the rest of `test_signup_interactions.py`, verify pass**

```bash
just test::run 'python manage.py test events.tests.test_signup_interactions -v 2'
```

- [ ] **Step 5: Commit**

```bash
git add backend/events/discord/handlers.py backend/events/tests/test_signup_interactions.py
git commit -m "refactor(discord): handle_signup_modal_submit calls apply_signup_input"
```

### Task 22: Refactor `PositionConfirmButton.callback`

**Files:**
- Modify: `backend/discordbot/components.py` (`PositionConfirmButton.callback` — currently writes positions inline)
- Modify: `backend/discordbot/tests/test_components.py` (assert spy)

- [ ] **Step 1: Add spy assertion to the existing `PositionConfirmButton` test**

```python
with mock_patch("events.services.apply_signup_input") as spy:
    await callback(interaction)
spy.assert_called_once()
patch_arg = spy.call_args.kwargs["patch"]
self.assertEqual(set(patch_arg.positions), {1, 2, 3})  # whatever the test selected
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Refactor `PositionConfirmButton.callback`** (in `components.py`)

Replace the `profile.pos_1 = ...; profile.save(); invalidate_obj(profile)` block with:

```python
from events.services import apply_signup_input
from events.schemas import SignupInputPatch

await sync_to_async(apply_signup_input)(
    org_user=org_user, event=event,
    patch=SignupInputPatch(positions=[int(v) for v in positions]),
)
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/discordbot/components.py backend/discordbot/tests/test_components.py
git commit -m "refactor(discord): PositionConfirmButton calls apply_signup_input"
```

### Task 23: Refactor `handle_rank_medal_select` and `handle_battle_cup_submit`

**Files:**
- Modify: `backend/events/discord/handlers.py`
- Modify: `backend/events/tests/test_signup_interactions.py` (or `test_components.py` — wherever these are exercised)

- [ ] **Step 1: Add spy assertions for both handlers**

```python
with mock_patch("events.discord.handlers.apply_signup_input") as spy:
    handle_rank_medal_select(event_id=..., discord_user_id=..., medal="Legend 3")
spy.assert_called_once()
self.assertEqual(spy.call_args.kwargs["patch"].rank_medal, "Legend 3")

with mock_patch("events.discord.handlers.apply_signup_input") as spy:
    handle_battle_cup_submit(event_id=..., discord_user_id=..., tier="5")
spy.assert_called_once()
self.assertEqual(spy.call_args.kwargs["patch"].battle_cup_tier, 5)
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Refactor both handlers** to build a `SignupInputPatch` and call `apply_signup_input`. Drop direct `profile.rank_medal = …; profile.save()` writes.

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "refactor(discord): rank_medal + battle_cup_tier handlers call apply_signup_input"
```

### Task 24: Refactor `handle_screenshot_upload`

**Files:**
- Modify: `backend/events/discord/handlers.py` (`handle_screenshot_upload`)
- Modify: `backend/events/tests/test_signup_interactions.py` (assert spy)

- [ ] **Step 1: Add spy assertion**

```python
with mock_patch("events.discord.handlers.apply_signup_input") as spy:
    handle_screenshot_upload(event_id=..., discord_user_id=...,
                             screenshot_type="rank",
                             attachment_url="https://example.com/a.png")
spy.assert_called_once()
self.assertEqual(spy.call_args.kwargs["patch"].rank_screenshot, "https://example.com/a.png")
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Refactor** the function to build `{"rank_screenshot": url}` (or `{"battlecup_screenshot": url}` based on `screenshot_type`) and call `apply_signup_input`. Drop direct `profile.rank_screenshot = ...; profile.save()` writes.

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "refactor(discord): screenshot upload handler calls apply_signup_input"
```

### Task 25: Delete `_save_dota_profile`

**Files:**
- Modify: `backend/events/discord/handlers.py`

- [ ] **Step 1: Delete the function and any remaining call sites**

```bash
grep -n "_save_dota_profile" backend/events/discord/handlers.py backend/events/discord/*.py backend/discordbot/*.py
```

If any remain, refactor them to use `apply_signup_input`. Then delete the function definition.

- [ ] **Step 2: Run all events + discordbot tests**

```bash
just test::run 'python manage.py test events discordbot -v 2'
```

- [ ] **Step 3: Commit**

```bash
git commit -am "refactor(discord): delete _save_dota_profile (replaced by apply_signup_input)"
```

### Task 26: ValidationError → ephemeral error message preservation test

**Files:**
- Test: `backend/events/tests/test_signup_interactions.py` or `test_components.py`

- [ ] **Step 1: Append test**

Pick any handler that uses the disallowed-rank-status path. Configure the event so `allow_active_mmr=False`, send a patch with `rank_status="active"`, and assert the result dict's `message` exactly equals `"This event does not accept active MMR signups."`:

```python
def test_disallowed_rank_status_returns_vocabulary_message(self):
    self.event.allow_active_mmr = False
    self.event.save()
    result = handle_signup_modal_submit(
        event_id=self.event.pk, discord_user_id="123",
        game_type=1, values={"rank_status": "active"},
    )
    self.assertEqual(result["action"], "error")
    self.assertEqual(result["message"], "This event does not accept active MMR signups.")
```

- [ ] **Step 2: Run, verify pass**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(discord): pin error-message vocabulary preservation"
```

### Task 27: Reaction-signup smoke test

**Files:**
- Test: `backend/events/tests/test_reaction_signup.py`

- [ ] **Step 1: Add a smoke test asserting the reaction-driven path still creates a signup after the refactor.**

```python
def test_reaction_signup_still_works_after_refactor(self):
    # Existing test setup: a user with a complete profile reacts to the embed.
    # After the refactor, the path is unchanged (reactions don't write profile fields).
    # This is a regression-catcher; behavior must equal the pre-refactor behavior.
    # ... reuse existing test scaffolding ...
    pass
```

If a similar smoke test already exists, mark this task done without changes; record that fact in the commit message.

- [ ] **Step 2: Run, verify pass**

- [ ] **Step 3: Commit (or skip if existing coverage suffices)**

```bash
git commit -am "test(discord): smoke-test reaction signup path post-refactor" || true
```

---

## Phase 8 — Test migrations + endpoint deletion

### Task 28: Migrate backend `test_api.py` from `/rsvp/` to `/signup/`

**Files:**
- Modify: `backend/events/tests/test_api.py`

- [ ] **Step 1: Find all `/rsvp/` and `/tentative/` POSTs**

```bash
grep -n "/rsvp/\|/tentative/" backend/events/tests/test_api.py
```

- [ ] **Step 2: Replace each with `/signup/` and add `{"intent": "rsvp"}` or `{"intent": "tentative"}` body.**

For each match, change:

```python
self.client.post(f"/api/events/{event.pk}/rsvp/")
```

to:

```python
self.client.post(f"/api/events/{event.pk}/signup/", {"intent": "rsvp"}, format="json")
```

- [ ] **Step 3: Run, verify pass**

```bash
just test::run 'python manage.py test events.tests.test_api -v 2'
```

- [ ] **Step 4: Commit**

```bash
git commit -am "test(events): migrate test_api.py from /rsvp/ /tentative/ to /signup/"
```

### Task 29: Delete `rsvp` and `tentative` actions from `EventViewSet`

**Files:**
- Modify: `backend/events/views.py`

- [ ] **Step 1: Delete the `rsvp` action method (~lines 452-490) and the `tentative` action method (~lines 486-525).**

- [ ] **Step 2: Run all events tests**

```bash
just test::run 'python manage.py test events -v 2'
```

If any test still references `/rsvp/` or `/tentative/`, migrate it.

- [ ] **Step 3: Commit**

```bash
git commit -am "refactor(events): delete rsvp and tentative DRF actions (replaced by /signup/)"
```

### Task 30: Schema-drift snapshot + assertion

**Files:**
- Modify: `backend/app/tests/test_schema_drift.py` (snapshot file path may live alongside)

- [ ] **Step 1: Regenerate the OpenAPI snapshot**

```bash
just test::run 'python manage.py spectacular --file backend/app/tests/openapi-snapshot.yaml'
```

(Adjust path/command per the actual `test_schema_drift.py` setup — read the file and follow its in-source instructions.)

- [ ] **Step 2: Add assertion to `test_schema_drift.py`**

```python
def test_signup_endpoint_in_schema(self):
    """Catch accidental future removal of /signup/."""
    schema = load_schema()
    self.assertIn("/api/events/{id}/signup/", schema["paths"])
    self.assertNotIn("/api/events/{id}/rsvp/", schema["paths"])
    self.assertNotIn("/api/events/{id}/tentative/", schema["paths"])
```

- [ ] **Step 3: Run schema-drift test, verify pass**

```bash
just test::run 'python manage.py test app.tests.test_schema_drift -v 2'
```

- [ ] **Step 4: Commit**

```bash
git commit -am "test(schema): regenerate snapshot + assert /signup/ exists, /rsvp/ and /tentative/ removed"
```

---

## Phase 9 — Frontend foundation

### Task 31: Install shadcn `<RadioGroup>` primitive

**Files:**
- New: `frontend/app/components/ui/radio-group.tsx`

- [ ] **Step 1: Install via shadcn CLI**

```bash
cd frontend && npx shadcn@latest add radio-group
```

- [ ] **Step 2: Verify file exists**

```bash
ls frontend/app/components/ui/radio-group.tsx
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/ui/radio-group.tsx frontend/components.json frontend/package.json frontend/package-lock.json
git commit -m "deps(ui): add shadcn radio-group primitive"
```

### Task 32: `useUserDotaProfile()` hook

**Files:**
- New: `frontend/app/hooks/useUserProfile.ts`
- New: `frontend/app/hooks/__tests__/useUserDotaProfile.test.ts`

- [ ] **Step 1: Write failing test**

```ts
// frontend/app/hooks/__tests__/useUserDotaProfile.test.ts
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useUserDotaProfile } from '../useUserProfile';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('useUserDotaProfile', () => {
  it('uses initialData when provided', async () => {
    const initial = { unverified_friend_id: '123', rank_status: 'active' as const, rank_medal: 'Legend 1', positions: { pos_1: true, pos_2: false, pos_3: false, pos_4: false, pos_5: false }, mmr: null, battle_cup_tier: null, rank_screenshot: null, battlecup_screenshot: null };
    const { result } = renderHook(
      () => useUserDotaProfile(42, { initialData: initial }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data?.unverified_friend_id).toBe('123');
  });
});
```

- [ ] **Step 2: Run, verify fail**

```bash
cd frontend && npm test -- useUserDotaProfile
```

- [ ] **Step 3: Implement**

```ts
// frontend/app/hooks/useUserProfile.ts
'use client';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import api from '~/components/api/axios';
import type { DotaProfileData } from '~/components/user';

export function useUserDotaProfile(
  userPk: number | null | undefined,
  options?: { initialData?: DotaProfileData | null },
) {
  return useQuery({
    queryKey: ['user-dota-profile', userPk],
    queryFn: async () => {
      const resp = await api.get<DotaProfileData>(`/users/${userPk}/dota-profile/`);
      return resp.data;
    },
    enabled: userPk != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    initialData: options?.initialData ?? undefined,
  });
}
```

(If no `/users/<pk>/dota-profile/` endpoint exists yet, derive the profile from `event.user_data.dota_profile` directly via `initialData` only — no fetch needed for v1. Document this in the file.)

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/app/hooks/useUserProfile.ts frontend/app/hooks/__tests__/useUserDotaProfile.test.ts
git commit -m "feat(hooks): useUserDotaProfile with SSR initialData"
```

### Task 33: `evaluateSignupGap` helper

**Files:**
- New: `frontend/app/components/events/EventSignupModal/evaluateSignupGap.ts`
- New: `frontend/app/components/events/__tests__/evaluateSignupGap.test.ts`

- [ ] **Step 1: Write failing test**

```ts
// frontend/app/components/events/__tests__/evaluateSignupGap.test.ts
import { describe, it, expect } from 'vitest';
import { evaluateSignupGap } from '../EventSignupModal/evaluateSignupGap';
import { GameType } from '../schemas';

const baseEvent = {
  id: 1, game_type: GameType.DOTA2,
  require_steam_id: false,
  allow_active_mmr: true, allow_previous_rank: true, allow_battlecup_rating: true,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
};

const completeProfile = {
  unverified_friend_id: '123',
  rank_status: 'active' as const,
  rank_medal: 'Legend 1',
  positions: { pos_1: true, pos_2: false, pos_3: false, pos_4: false, pos_5: false },
  battle_cup_tier: null,
  rank_screenshot: null,
  battlecup_screenshot: null,
  mmr: null,
};

describe('evaluateSignupGap', () => {
  it('returns complete when nothing is missing', () => {
    expect(evaluateSignupGap(baseEvent as never, completeProfile as never)).toBe('complete');
  });

  it('flags friend_id when required-and-missing (universal across game types)', () => {
    const event = { ...baseEvent, require_steam_id: true, game_type: 99 /* not Dota */ };
    const profile = { ...completeProfile, unverified_friend_id: null };
    expect(evaluateSignupGap(event as never, profile as never)).toEqual(['friend_id']);
  });

  it('flags rank_status when missing on Dota 2', () => {
    const profile = { ...completeProfile, rank_status: null };
    expect(evaluateSignupGap(baseEvent as never, profile as never)).toContain('rank_status');
  });

  it('flags rank_screenshot when required-and-missing for active rank', () => {
    const event = { ...baseEvent, discord_require_rank_screenshot: true };
    const profile = { ...completeProfile, rank_screenshot: null };
    expect(evaluateSignupGap(event as never, profile as never)).toContain('rank_screenshot');
  });

  it('does not flag rank_screenshot for never-rank when battlecup screenshot suffices', () => {
    const event = { ...baseEvent, discord_require_battlecup_screenshot: true };
    const profile = {
      ...completeProfile,
      rank_status: 'never' as const, rank_medal: null,
      battle_cup_tier: 5,
      battlecup_screenshot: 'https://i.imgur.com/x.png',
    };
    expect(evaluateSignupGap(event as never, profile as never)).toBe('complete');
  });
});
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement**

```ts
// frontend/app/components/events/EventSignupModal/evaluateSignupGap.ts
import { GameType, type EventType } from '../schemas';
import type { DotaProfileData } from '~/components/user';

function hasAnyPosition(profile: DotaProfileData | null | undefined): boolean {
  if (!profile?.positions) return false;
  const p = profile.positions;
  return !!(p.pos_1 || p.pos_2 || p.pos_3 || p.pos_4 || p.pos_5);
}

export function evaluateSignupGap(
  event: EventType,
  profile: DotaProfileData | null | undefined,
): 'complete' | string[] {
  const missing: string[] = [];

  if (event.require_steam_id && !profile?.unverified_friend_id) missing.push('friend_id');

  if (event.game_type === GameType.DOTA2) {
    if (!profile?.rank_status) missing.push('rank_status');
    if (!hasAnyPosition(profile)) missing.push('positions');
    if (profile?.rank_status === 'active' || profile?.rank_status === 'previous') {
      if (!profile.rank_medal) missing.push('rank_medal');
    }
    if (profile?.rank_status === 'never' && profile.battle_cup_tier == null) {
      missing.push('battle_cup_tier');
    }
    if (event.discord_require_rank_screenshot &&
        (profile?.rank_status === 'active' || profile?.rank_status === 'previous') &&
        !profile.rank_screenshot) {
      missing.push('rank_screenshot');
    }
    if (event.discord_require_battlecup_screenshot &&
        profile?.rank_status === 'never' &&
        !profile.battlecup_screenshot) {
      missing.push('battlecup_screenshot');
    }
  }

  return missing.length === 0 ? 'complete' : missing;
}
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/events/EventSignupModal/evaluateSignupGap.ts frontend/app/components/events/__tests__/evaluateSignupGap.test.ts
git commit -m "feat(events): evaluateSignupGap helper for skip-the-form fast path"
```

### Task 34: `signupPatchSchema` zod schema builder

**Files:**
- New: `frontend/app/components/events/EventSignupModal/schema.ts`
- New: `frontend/app/components/events/__tests__/signupSchema.test.ts`

- [ ] **Step 1: Write failing test**

```ts
import { describe, it, expect } from 'vitest';
import { buildSignupPatchSchema } from '../EventSignupModal/schema';

const baseEvent = {
  game_type: 1 /* DOTA2 */,
  require_steam_id: true,
  allow_active_mmr: true, allow_previous_rank: true, allow_battlecup_rating: true,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
};

const emptyProfile = null;

describe('buildSignupPatchSchema', () => {
  it('requires friend_id when missing', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({});
    expect(result.success).toBe(false);
  });

  it('accepts a complete payload', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const ok = schema.safeParse({
      unverified_friend_id: '12345',
      rank_status: 'active',
      positions: [1, 2],
      rank_medal: 'Legend 1',
    });
    expect(ok.success).toBe(true);
  });

  it('rejects bad screenshot URL when required', () => {
    const event = { ...baseEvent, discord_require_rank_screenshot: true };
    const schema = buildSignupPatchSchema(event as never, emptyProfile);
    const result = schema.safeParse({
      unverified_friend_id: '12345', rank_status: 'active', positions: [1], rank_medal: 'Legend 1',
      rank_screenshot: 'not-a-url',
    });
    expect(result.success).toBe(false);
  });
});
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement**

```ts
// frontend/app/components/events/EventSignupModal/schema.ts
import { z } from 'zod';
import { GameType, type EventType } from '../schemas';
import type { DotaProfileData } from '~/components/user';

const SCREENSHOT_URL_RE = /^https?:\/\/.+\.(png|jpe?g|webp)(\?.*)?$/i;

export function buildSignupPatchSchema(
  event: EventType,
  profile: DotaProfileData | null | undefined,
) {
  const fields: Record<string, z.ZodType> = {};

  if (event.require_steam_id && !profile?.unverified_friend_id) {
    fields.unverified_friend_id = z.string().min(1).max(20);
  } else {
    fields.unverified_friend_id = z.string().max(20).optional();
  }

  if (event.game_type === GameType.DOTA2) {
    if (!profile?.rank_status) {
      fields.rank_status = z.enum(['active', 'previous', 'never']);
    } else {
      fields.rank_status = z.enum(['active', 'previous', 'never']).optional();
    }

    const hasPos = profile?.positions && Object.values(profile.positions).some(Boolean);
    if (!hasPos) {
      fields.positions = z.array(z.number().int().min(1).max(5)).min(1);
    } else {
      fields.positions = z.array(z.number().int().min(1).max(5)).optional();
    }

    fields.rank_medal = z.string().max(64).optional();
    fields.battle_cup_tier = z.number().int().min(1).max(8).optional();

    fields.rank_screenshot = z.string().regex(SCREENSHOT_URL_RE).optional();
    fields.battlecup_screenshot = z.string().regex(SCREENSHOT_URL_RE).optional();
  }

  return z.object(fields);
}

export type SignupInputPatch = z.infer<ReturnType<typeof buildSignupPatchSchema>>;
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/events/EventSignupModal/schema.ts frontend/app/components/events/__tests__/signupSchema.test.ts
git commit -m "feat(events): dynamic zod schema for signup form"
```

### Task 35: `toPatch` mapper

**Files:**
- New: `frontend/app/components/events/EventSignupModal/toPatch.ts`
- New: `frontend/app/components/events/__tests__/toPatch.test.ts`

- [ ] **Step 1: Write failing test**

```ts
import { describe, it, expect } from 'vitest';
import { toPatch } from '../EventSignupModal/toPatch';

describe('toPatch', () => {
  it('omits unchanged fields', () => {
    const profile = { unverified_friend_id: '12345', rank_status: 'active' };
    const values = { unverified_friend_id: '12345', rank_status: 'active', rank_medal: 'Legend 1' };
    expect(toPatch(values as never, profile as never)).toEqual({ rank_medal: 'Legend 1' });
  });

  it('includes everything when no profile', () => {
    expect(toPatch({ rank_status: 'never' } as never, null)).toEqual({ rank_status: 'never' });
  });
});
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement**

```ts
// frontend/app/components/events/EventSignupModal/toPatch.ts
import type { SignupInputPatch } from './schema';
import type { DotaProfileData } from '~/components/user';

export function toPatch(
  values: SignupInputPatch,
  profile: DotaProfileData | null | undefined,
): Partial<SignupInputPatch> {
  if (!profile) return values;

  const patch: Record<string, unknown> = {};
  const v = values as Record<string, unknown>;
  const p = profile as unknown as Record<string, unknown>;

  for (const key of Object.keys(v)) {
    if (v[key] === undefined) continue;
    if (JSON.stringify(v[key]) !== JSON.stringify(p[key])) {
      patch[key] = v[key];
    }
  }
  return patch as Partial<SignupInputPatch>;
}
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(events): toPatch mapper diffs values against profile"
```

---

## Phase 10 — Modal subcomponents

### Task 36: `FriendIdField` subcomponent

**Files:**
- New: `frontend/app/components/events/EventSignupModal/FriendIdField.tsx`

- [ ] **Step 1: Implement** (no test — covered by `EventSignupModal` integration test in Task 41)

```tsx
'use client';
import { Controller, type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';

export function FriendIdField({ control }: { control: Control }) {
  return (
    <FormField
      control={control}
      name="unverified_friend_id"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Dota 2 Friend ID</FormLabel>
          <FormControl>
            <Input
              {...field}
              data-testid="signup-friend-id"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="Your Friend ID (number from your Dotabuff URL)"
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/events/EventSignupModal/FriendIdField.tsx
git commit -m "feat(events): FriendIdField subcomponent"
```

### Task 37: `RankStatusRadioGroup` subcomponent

**Files:**
- New: `frontend/app/components/events/EventSignupModal/RankStatusRadioGroup.tsx`

- [ ] **Step 1: Implement**

```tsx
'use client';
import { Controller, type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import { cn } from '~/lib/utils';

type Option = { value: 'active' | 'previous' | 'never'; label: string; desc: string };

const ALL_OPTIONS: Array<Option & { flag: 'allow_active_mmr' | 'allow_previous_rank' | 'allow_battlecup_rating' }> = [
  { value: 'active',   flag: 'allow_active_mmr',      label: 'I have an active MMR', desc: 'Currently ranked in Dota 2' },
  { value: 'previous', flag: 'allow_previous_rank',   label: 'I had an MMR',          desc: 'Previously ranked but not currently' },
  { value: 'never',    flag: 'allow_battlecup_rating',label: "I've never had an MMR", desc: 'Never played ranked Dota 2' },
];

export function RankStatusRadioGroup({
  control, event,
}: {
  control: Control;
  event: { allow_active_mmr: boolean; allow_previous_rank: boolean; allow_battlecup_rating: boolean };
}) {
  const opts = ALL_OPTIONS.filter((o) => event[o.flag]);
  return (
    <FormField
      control={control}
      name="rank_status"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Rank Status</FormLabel>
          <FormControl>
            <RadioGroup
              data-testid="signup-rank-status"
              value={field.value ?? ''}
              onValueChange={field.onChange}
              className="flex flex-col gap-2"
            >
              {opts.map((o) => (
                <label
                  key={o.value}
                  className={cn(
                    'flex items-start gap-3 rounded-md border border-border p-3',
                    'hover:bg-base-200 cursor-pointer min-h-11',
                    field.value === o.value && 'ring-2 ring-ring',
                  )}
                >
                  <RadioGroupItem value={o.value} className="mt-1" />
                  <div className="flex flex-col">
                    <span className="font-medium">{o.label}</span>
                    <span className="text-sm text-muted-foreground">{o.desc}</span>
                  </div>
                </label>
              ))}
            </RadioGroup>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
```

- [ ] **Step 2: Type-check, commit**

```bash
git add frontend/app/components/events/EventSignupModal/RankStatusRadioGroup.tsx
git commit -m "feat(events): RankStatusRadioGroup subcomponent"
```

### Task 38: `PositionPickerGrid` subcomponent

**Files:**
- New: `frontend/app/components/events/EventSignupModal/PositionPickerGrid.tsx`

- [ ] **Step 1: Implement**

```tsx
'use client';
import { type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { ToggleGroup, ToggleGroupItem } from '~/components/ui/toggle-group';

const POSITIONS = [
  { value: '1', label: 'Carry',         emoji: '⚔️' },
  { value: '2', label: 'Mid',           emoji: '\u{1F3AF}' },
  { value: '3', label: 'Offlane',       emoji: '\u{1F6E1}️' },
  { value: '4', label: 'Soft Support',  emoji: '\u{1F49A}' },
  { value: '5', label: 'Hard Support',  emoji: '\u{1F49B}' },
];

export function PositionPickerGrid({ control }: { control: Control }) {
  return (
    <FormField
      control={control}
      name="positions"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Preferred Positions</FormLabel>
          <FormControl>
            <ToggleGroup
              type="multiple"
              data-testid="signup-positions"
              aria-label="Preferred positions"
              value={(field.value ?? []).map(String)}
              onValueChange={(values: string[]) => field.onChange(values.map(Number))}
              className="grid grid-cols-5 gap-2"
            >
              {POSITIONS.map((p) => (
                <ToggleGroupItem key={p.value} value={p.value} className="min-h-11 flex flex-col items-center">
                  <span aria-hidden>{p.emoji}</span>
                  <span className="text-xs">{p.label}</span>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
```

- [ ] **Step 2: Type-check, commit**

```bash
git add frontend/app/components/events/EventSignupModal/PositionPickerGrid.tsx
git commit -m "feat(events): PositionPickerGrid subcomponent"
```

### Task 39: `RankDetailFields` subcomponent

**Files:**
- New: `frontend/app/components/events/EventSignupModal/RankDetailFields.tsx`

- [ ] **Step 1: Implement**

```tsx
'use client';
import { type Control, useWatch } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select';

const MEDALS = ['Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];
const STARS = ['1', '2', '3', '4', '5'];
const BC_TIERS = ['1', '2', '3', '4', '5', '6', '7', '8'];

export function RankDetailFields({ control }: { control: Control }) {
  const rankStatus = useWatch({ control, name: 'rank_status' });

  if (rankStatus === 'never') {
    return (
      <FormField
        key="bc"
        control={control}
        name="battle_cup_tier"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Battle Cup Tier</FormLabel>
            <FormControl>
              <Select
                key={rankStatus}
                value={field.value != null ? String(field.value) : ''}
                onValueChange={(v) => field.onChange(parseInt(v, 10))}
              >
                <SelectTrigger data-testid="signup-battlecup-tier" className="min-h-11">
                  <SelectValue placeholder="Select tier" />
                </SelectTrigger>
                <SelectContent>
                  {BC_TIERS.map((t) => <SelectItem key={t} value={t}>Tier {t}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    );
  }

  if (rankStatus !== 'active' && rankStatus !== 'previous') return null;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <FormField
        key="medal"
        control={control}
        name="rank_medal_medal"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Medal</FormLabel>
            <FormControl>
              <Select key={rankStatus} value={field.value ?? ''} onValueChange={field.onChange}>
                <SelectTrigger data-testid="signup-rank-medal" className="min-h-11">
                  <SelectValue placeholder="Select medal" />
                </SelectTrigger>
                <SelectContent>
                  {MEDALS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        key="star"
        control={control}
        name="rank_medal_star"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Star</FormLabel>
            <FormControl>
              <Select key={rankStatus} value={field.value ?? ''} onValueChange={field.onChange}>
                <SelectTrigger data-testid="signup-rank-star" className="min-h-11">
                  <SelectValue placeholder="Star (1-5)" />
                </SelectTrigger>
                <SelectContent>
                  {STARS.map((s) => <SelectItem key={s} value={s}>Star {s}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
```

The medal+star fields are stitched into one `rank_medal` string at submit time inside the parent (`EventSignupModal`); `rank_medal_medal` and `rank_medal_star` are local form-state names.

- [ ] **Step 2: Type-check, commit**

```bash
git add frontend/app/components/events/EventSignupModal/RankDetailFields.tsx
git commit -m "feat(events): RankDetailFields subcomponent (medal+star or BC tier)"
```

### Task 40: `ScreenshotUrlField` subcomponent

**Files:**
- New: `frontend/app/components/events/EventSignupModal/ScreenshotUrlField.tsx`

- [ ] **Step 1: Implement**

```tsx
'use client';
import { type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';

export function ScreenshotUrlField({
  control, name = 'rank_screenshot', label = 'MMR Screenshot URL',
}: {
  control: Control; name?: 'rank_screenshot' | 'battlecup_screenshot'; label?: string;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              {...field}
              type="url"
              inputMode="url"
              data-testid="signup-screenshot-url"
              placeholder="https://i.imgur.com/your-screenshot.png"
            />
          </FormControl>
          <FormDescription>Upload your screenshot to imgur.com and paste the link here.</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/events/EventSignupModal/ScreenshotUrlField.tsx
git commit -m "feat(events): ScreenshotUrlField subcomponent"
```

### Task 41: `EventSignupModal` root + integration test

**Files:**
- New: `frontend/app/components/events/EventSignupModal.tsx`
- New: `frontend/app/components/events/__tests__/EventSignupModal.test.tsx`

- [ ] **Step 1: Write failing integration test**

```tsx
// frontend/app/components/events/__tests__/EventSignupModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EventSignupModal } from '../EventSignupModal';
import { GameType } from '../schemas';

const event = {
  id: 1, name: 'Evt', game_type: GameType.DOTA2,
  require_steam_id: true,
  allow_active_mmr: true, allow_previous_rank: true, allow_battlecup_rating: true,
  discord_require_rank_screenshot: false, discord_require_battlecup_screenshot: false,
};

function withQuery(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('EventSignupModal', () => {
  it('renders Friend ID + rank-status + positions when profile is empty', () => {
    render(withQuery(
      <EventSignupModal
        event={event as never}
        intent="rsvp"
        profile={null}
        open
        onOpenChange={vi.fn()}
      />,
    ));
    expect(screen.getByTestId('signup-friend-id')).toBeInTheDocument();
    expect(screen.getByTestId('signup-rank-status')).toBeInTheDocument();
    expect(screen.getByTestId('signup-positions')).toBeInTheDocument();
  });

  it('hides Friend ID when profile already has it', () => {
    render(withQuery(
      <EventSignupModal
        event={event as never}
        intent="rsvp"
        profile={{ unverified_friend_id: '123' } as never}
        open
        onOpenChange={vi.fn()}
      />,
    ));
    expect(screen.queryByTestId('signup-friend-id')).toBeNull();
  });

  it('uses correct title for rsvp vs tentative', () => {
    const { rerender } = render(withQuery(
      <EventSignupModal event={event as never} intent="rsvp" profile={null} open onOpenChange={vi.fn()} />,
    ));
    expect(screen.getByText(/Sign Up for Evt/)).toBeInTheDocument();
    rerender(withQuery(
      <EventSignupModal event={event as never} intent="tentative" profile={null} open onOpenChange={vi.fn()} />,
    ));
    expect(screen.getByText(/Mark Tentative for Evt/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, verify fail**

```bash
cd frontend && npm test -- EventSignupModal
```

- [ ] **Step 3: Implement `EventSignupModal.tsx`**

```tsx
'use client';
import { useMemo, useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog, DialogContent, DialogTitle, DialogHeader, DialogFooter } from '~/components/ui/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from '~/components/ui/sheet';
import { Form } from '~/components/ui/form';
import { Badge } from '~/components/ui/badge';
import { SubmitButton, CancelButton } from '~/components/ui/buttons';
import { useMediaQuery } from '~/hooks/useMediaQuery';
import { buildSignupPatchSchema, type SignupInputPatch } from './EventSignupModal/schema';
import { toPatch } from './EventSignupModal/toPatch';
import { FriendIdField } from './EventSignupModal/FriendIdField';
import { RankStatusRadioGroup } from './EventSignupModal/RankStatusRadioGroup';
import { PositionPickerGrid } from './EventSignupModal/PositionPickerGrid';
import { RankDetailFields } from './EventSignupModal/RankDetailFields';
import { ScreenshotUrlField } from './EventSignupModal/ScreenshotUrlField';
import { useSignupMutation } from '~/hooks/useEvent';
import { GameType, type EventType } from './schemas';
import type { DotaProfileData } from '~/components/user';

export type EventSignupModalProps = {
  event: EventType;
  intent: 'rsvp' | 'tentative';
  profile: DotaProfileData | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function EventSignupModal({ event, intent, profile, open, onOpenChange }: EventSignupModalProps) {
  const isDesktop = useMediaQuery('(min-width: 768px)');

  const schema = useMemo(
    () => buildSignupPatchSchema(event, profile),
    [
      event.id, event.require_steam_id,
      event.allow_active_mmr, event.allow_previous_rank, event.allow_battlecup_rating,
      event.discord_require_rank_screenshot, event.discord_require_battlecup_screenshot,
      profile?.unverified_friend_id != null,
      profile?.rank_status,
      profile?.rank_medal != null,
      profile?.battle_cup_tier != null,
      profile?.positions ? Object.values(profile.positions).some(Boolean) : false,
      profile?.rank_screenshot != null,
      profile?.battlecup_screenshot != null,
    ],
  );

  const form = useForm<SignupInputPatch & { rank_medal_medal?: string; rank_medal_star?: string }>({
    resolver: zodResolver(schema as never),
    mode: 'onChange',
    shouldUnregister: true,
    defaultValues: {},
  });

  const mutation = useSignupMutation(event.id);

  const onSubmit = form.handleSubmit(async (values) => {
    const merged: SignupInputPatch = { ...values };
    if (values.rank_medal_medal) {
      merged.rank_medal = values.rank_medal_medal === 'Immortal'
        ? 'Immortal'
        : `${values.rank_medal_medal} ${values.rank_medal_star ?? '1'}`;
    }
    delete (merged as Record<string, unknown>).rank_medal_medal;
    delete (merged as Record<string, unknown>).rank_medal_star;
    const patch = toPatch(merged, profile);
    await mutation.mutateAsync({ intent, profile: patch });
    onOpenChange(false);
  });

  const showFriendId = event.require_steam_id && !profile?.unverified_friend_id;
  const isDota = event.game_type === GameType.DOTA2;
  const showRankStatus = isDota && !profile?.rank_status;
  const hasPos = profile?.positions ? Object.values(profile.positions).some(Boolean) : false;
  const showPositions = isDota && !hasPos;
  const showRankDetail = isDota && !!form.watch('rank_status');
  const screenshotForActive = isDota && event.discord_require_rank_screenshot &&
    (form.watch('rank_status') === 'active' || form.watch('rank_status') === 'previous') &&
    !profile?.rank_screenshot;
  const screenshotForBC = isDota && event.discord_require_battlecup_screenshot &&
    form.watch('rank_status') === 'never' && !profile?.battlecup_screenshot;

  const title = intent === 'rsvp' ? `Sign Up for ${event.name}` : `Mark Tentative for ${event.name}`;
  const banner = intent === 'rsvp'
    ? "You're committing to play this event. We'll add you to the signup list."
    : "You're marking yourself tentative — we count you as interested but not committed.";

  const body = (
    <Form {...form}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4" data-testid="event-signup-modal">
        <Badge variant={intent === 'rsvp' ? 'default' : 'secondary'}>{banner}</Badge>
        {showFriendId && <FriendIdField control={form.control as never} />}
        {showRankStatus && <RankStatusRadioGroup control={form.control as never} event={event} />}
        {showPositions && <PositionPickerGrid control={form.control as never} />}
        {showRankDetail && <RankDetailFields control={form.control as never} />}
        {screenshotForActive && <ScreenshotUrlField control={form.control as never} name="rank_screenshot" />}
        {screenshotForBC && <ScreenshotUrlField control={form.control as never} name="battlecup_screenshot" label="Battle Cup Screenshot URL" />}
        <div className="flex justify-end gap-2 pt-2">
          <CancelButton type="button" onClick={() => onOpenChange(false)} disabled={mutation.isPending} data-testid="event-signup-cancel-btn">
            Cancel
          </CancelButton>
          <SubmitButton loading={mutation.isPending} disabled={!form.formState.isValid} data-testid="event-signup-submit-btn">
            {intent === 'rsvp' ? 'Sign Up' : 'Mark Tentative'}
          </SubmitButton>
        </div>
      </form>
    </Form>
  );

  if (isDesktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          {body}
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[90dvh] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
        </SheetHeader>
        {body}
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 4: Run integration test, verify pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/events/EventSignupModal.tsx frontend/app/components/events/__tests__/EventSignupModal.test.tsx
git commit -m "feat(events): EventSignupModal root with conditional sections + responsive Dialog/Sheet"
```

---

## Phase 11 — Mutation hook + page wiring

### Task 42: `useSignupMutation` + delete old hooks

**Files:**
- Modify: `frontend/app/hooks/useEvent.ts`
- Modify: `frontend/app/components/api/api.ts` (add `signupForEvent`)

- [ ] **Step 1: Add API helper**

In `frontend/app/components/api/api.ts`, append:

```ts
import api from './axios';

export type SignupBody = {
  intent: 'rsvp' | 'tentative';
  profile?: Record<string, unknown>;
};

export async function signupForEvent(eventId: number, body: SignupBody) {
  const resp = await api.post(`/events/${eventId}/signup/`, body);
  return resp.data;
}
```

- [ ] **Step 2: Replace `useRsvpMutation` and `useTentativeMutation` with `useSignupMutation`**

In `frontend/app/hooks/useEvent.ts`:

```ts
export function useSignupMutation(eventId: number) {
  const queryClient = useQueryClient();
  const currentUser = useUserStore.getState().currentUser;
  return useMutation({
    mutationFn: (body: SignupBody) => signupForEvent(eventId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
      if (currentUser?.pk) {
        queryClient.invalidateQueries({ queryKey: ['user-dota-profile', currentUser.pk] });
      }
      useOrgStore.getState().clearOrgUsers();
    },
  });
}
```

Delete `useRsvpMutation` and `useTentativeMutation` from this file.

- [ ] **Step 3: Type-check (will fail at consumers — fixed in next task)**

```bash
cd frontend && npm run typecheck 2>&1 | tail -30
```

- [ ] **Step 4: Commit (intentionally with broken consumers — next task fixes)**

```bash
git add frontend/app/hooks/useEvent.ts frontend/app/components/api/api.ts
git commit -m "feat(hooks): useSignupMutation; remove useRsvpMutation/useTentativeMutation"
```

### Task 43: Rewire `event.tsx` — replace ConfirmDialog flow + skip-the-form fast path

**Files:**
- Modify: `frontend/app/routes/event.tsx`

- [ ] **Step 1: Add state + helper imports + mutation**

At the top of the component:

```tsx
import { EventSignupModal } from '~/components/events/EventSignupModal';
import { evaluateSignupGap } from '~/components/events/EventSignupModal/evaluateSignupGap';
import { useSignupMutation } from '~/hooks/useEvent';
import { useUserDotaProfile } from '~/hooks/useUserProfile';
```

Replace the `rsvpMutation` / `tentativeMutation` references with `signupMutation = useSignupMutation(id ?? 0)` and:

```tsx
const profileQuery = useUserDotaProfile(currentUser?.pk, {
  initialData: event?.user_data?.dota_profile ?? null,
});
const profile = profileQuery.data;
const [signupModal, setSignupModal] = useState<{ open: boolean; intent: 'rsvp' | 'tentative' }>(
  { open: false, intent: 'rsvp' },
);
```

- [ ] **Step 2: Replace the existing ConfirmDialog "RSVP for Event" flow with the gap-evaluating click handler**

Replace the existing Sign Up button's `onClick={() => setShowRsvpConfirm(true)}` with:

```tsx
onClick={async () => {
  if (!event) return;
  const gap = evaluateSignupGap(event, profile);
  if (gap === 'complete') {
    try {
      await signupMutation.mutateAsync({ intent: 'rsvp', profile: {} });
      toast.success('Signed up!');
    } catch (err) {
      toast.error(extractApiError(err) || 'Failed to sign up');
    }
  } else {
    setSignupModal({ open: true, intent: 'rsvp' });
  }
}}
disabled={signupMutation.isPending}
```

Same for Tentative button (intent: 'tentative').

Same for `event-upgrade-rsvp-btn` (intent: 'rsvp', re-using gap evaluation).

Delete the `ConfirmDialog` block titled "RSVP for Event".

- [ ] **Step 3: Render `<EventSignupModal>` once at the end of the page tree**

```tsx
{event && (
  <EventSignupModal
    event={event}
    intent={signupModal.intent}
    profile={profile}
    open={signupModal.open}
    onOpenChange={(open) => setSignupModal((s) => ({ ...s, open }))}
  />
)}
```

- [ ] **Step 4: Type-check + run dev server, click through manually**

```bash
cd frontend && npm run typecheck 2>&1 | tail -10
just dev::debug &
# Open localhost, log in, navigate to an event, click Sign Up. Verify modal opens for incomplete profile, fast path fires for complete profile.
```

- [ ] **Step 5: Commit**

```bash
git add frontend/app/routes/event.tsx
git commit -m "feat(events): rewire event page to EventSignupModal with skip-the-form fast path"
```

---

## Phase 12 — Playwright E2E

### Task 44: Add `loginEventPlayerNoProfile` Playwright fixture

**Files:**
- Modify: `frontend/tests/playwright/fixtures/events.ts` (or wherever `loginEventPlayer` lives)

- [ ] **Step 1: Append the new fixture**

```ts
export async function loginEventPlayerNoProfile(context: BrowserContext) {
  await loginAs(context, 'event_player_no_profile');  // matches the populate user
}
```

- [ ] **Step 2: Export from `frontend/tests/playwright/fixtures/index.ts`**

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/playwright/fixtures/events.ts frontend/tests/playwright/fixtures/index.ts
git commit -m "test(playwright): add loginEventPlayerNoProfile fixture"
```

### Task 45: Migrate Playwright specs from `/rsvp/` and `/tentative/` to `/signup/`

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/01-smoke.spec.ts`
- Modify: `frontend/tests/playwright/e2e/16-events/03-roll-call.spec.ts`
- Modify: `frontend/tests/playwright/e2e/16-events/04-discord-integration.spec.ts`

- [ ] **Step 1: Update each `postWithCsrf` call**

Replace:

```ts
const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${eventId}/rsvp/`);
```

with:

```ts
const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${eventId}/signup/`, { intent: 'rsvp' });
```

(Verify the `postWithCsrf` signature accepts a body — it likely does. If not, look up the helper and pass JSON appropriately.)

- [ ] **Step 2: Update the UI-driven test in `01-smoke.spec.ts:189-199`**

The test today clicks `event-rsvp-btn` then a confirm dialog. After this change, the click goes through the new modal (or fast path if the user has a complete profile). Since `event_player_1` has a complete profile, the fast path fires — no modal expected. Update assertions:

```ts
const rsvpBtn = page.getByTestId('event-signup-btn');
await rsvpBtn.click();
// No confirm dialog now; fast path fires immediately.
await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({ timeout: 10000 });
```

(Also rename `event-rsvp-btn` → `event-signup-btn` consistently — verify what testid is actually used in the new event.tsx and align.)

- [ ] **Step 3: Run all migrated specs**

```bash
just test::pw::spec 16-events
```

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/16-events/
git commit -m "test(playwright): migrate 01-smoke, 03-roll-call, 04-discord-integration to /signup/"
```

### Task 46: New `12-event-signup-form.spec.ts` — happy paths + conditional reveals

**Files:**
- New: `frontend/tests/playwright/e2e/16-events/12-event-signup-form.spec.ts`

- [ ] **Step 1: Implement spec with all 8 cases**

```ts
import { test, expect } from '@playwright/test';
import { loginEventPlayer, loginEventPlayerNoProfile } from '~/fixtures';

test.describe('event signup form', () => {
  test('complete profile uses fast path (no modal)', async ({ page, context }) => {
    await loginEventPlayer(context);
    await page.goto('/events/<screenshot-not-required-event-id>');
    await page.getByTestId('event-signup-btn').click();
    await expect(page.getByTestId('event-signup-modal')).toHaveCount(0);
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible();
  });

  test('incomplete profile opens modal with all sections', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<screenshot-not-required-event-id>');
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    await expect(modal.getByTestId('signup-friend-id')).toBeVisible();
    await expect(modal.getByTestId('signup-rank-status')).toBeVisible();
    await expect(modal.getByTestId('signup-positions')).toBeVisible();

    // Fill all sections
    await modal.getByTestId('signup-friend-id').fill('12345678');
    await modal.getByTestId('signup-rank-status').getByText('I have an active MMR').click();
    await modal.getByTestId('signup-positions').getByText('Carry').click();
    await modal.getByTestId('signup-positions').getByText('Mid').click();
    await modal.getByTestId('signup-rank-medal').click();
    await page.getByText('Crusader').click();
    await modal.getByTestId('signup-rank-star').click();
    await page.getByText('Star 3').click();

    await modal.getByTestId('event-signup-submit-btn').click();
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({ timeout: 10000 });
  });

  test('rank_status="never" reveals Battle Cup Tier (not Medal/Star)', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<screenshot-not-required-event-id>');
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await modal.getByText("I've never had an MMR").click();
    await expect(modal.getByTestId('signup-battlecup-tier')).toBeVisible();
    await expect(modal.getByTestId('signup-rank-medal')).toHaveCount(0);
  });

  test('screenshot-required event surfaces URL field', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<screenshot-required-event-id>');
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await modal.getByText('I have an active MMR').click();
    await modal.getByTestId('signup-rank-medal').click();
    await page.getByText('Legend').click();
    await modal.getByTestId('signup-rank-star').click();
    await page.getByText('Star 1').click();
    await expect(modal.getByTestId('signup-screenshot-url')).toBeVisible();
    await modal.getByTestId('signup-screenshot-url').fill('not-a-url');
    await expect(modal.getByText(/screenshot must be/i)).toBeVisible();
    await modal.getByTestId('signup-screenshot-url').fill('https://i.imgur.com/x.png');
    await modal.getByTestId('signup-friend-id').fill('1');
    await modal.getByTestId('signup-positions').getByText('Carry').click();
    await modal.getByTestId('event-signup-submit-btn').click();
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({ timeout: 10000 });
  });

  test('tentative path uses same modal with different submit label', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<screenshot-not-required-event-id>');
    await page.getByTestId('event-tentative-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal.getByText(/Mark Tentative/)).toBeVisible();
    // Fill minimal and submit
    await modal.getByTestId('signup-friend-id').fill('1');
    await modal.getByText('I have an active MMR').click();
    await modal.getByTestId('signup-positions').getByText('Carry').click();
    await modal.getByTestId('signup-rank-medal').click();
    await page.getByText('Legend').click();
    await modal.getByTestId('signup-rank-star').click();
    await page.getByText('Star 1').click();
    await modal.getByTestId('event-signup-submit-btn').click();
    // Tentative tab gets the user.
    await expect(page.getByTestId('event-tab-tentative')).toBeVisible();
  });

  test('allow_active_mmr=false filters that radio out', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<event-with-active-mmr-disabled-id>');
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal.getByText('I had an MMR')).toBeVisible();
    await expect(modal.getByText("I've never had an MMR")).toBeVisible();
    await expect(modal.getByText('I have an active MMR')).toHaveCount(0);
  });

  test('Friend ID universal across game types (Deadlock event)', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<deadlock-event-id>');
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal.getByTestId('signup-friend-id')).toBeVisible();
    await expect(modal.getByTestId('signup-rank-status')).toHaveCount(0);
    await expect(modal.getByTestId('signup-positions')).toHaveCount(0);
  });

  test('upgrade tentative to rsvp re-runs gap evaluation', async ({ page, context }) => {
    await loginEventPlayer(context);  // complete profile
    await page.goto('/events/<screenshot-not-required-event-id>');
    await page.getByTestId('event-tentative-btn').click();  // creates tentative directly (fast path)
    await expect(page.getByTestId('event-cancel-tentative-btn')).toBeVisible();
    // Click Upgrade
    await page.getByTestId('event-upgrade-rsvp-btn').click();
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({ timeout: 10000 });
  });

  test('mobile viewport renders Sheet variant with sticky submit', async ({ page, context }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await loginEventPlayerNoProfile(context);
    await page.goto('/events/<screenshot-not-required-event-id>');
    // Use mobile-nav flow per testing skill convention
    await page.getByTestId('mobile-nav-trigger').click();
    await page.getByText('Sign Up').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    // Submit button is reachable without horizontal scroll
    await expect(modal.getByTestId('event-signup-submit-btn')).toBeInViewport();
  });
});
```

Replace `<screenshot-not-required-event-id>`, `<screenshot-required-event-id>`, `<event-with-active-mmr-disabled-id>`, `<deadlock-event-id>` with PKs read from the populate fixtures (look up via `populate/events.py` or the existing `fixtures/events.ts` helpers).

- [ ] **Step 2: Run the new spec**

```bash
just test::pw::spec 12-event-signup-form
```

- [ ] **Step 3: Iterate on selectors / event-IDs until all 9 cases pass**

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/16-events/12-event-signup-form.spec.ts
git commit -m "test(playwright): add 12-event-signup-form covering 9 scenarios incl mobile"
```

---

## Phase 13 — Final verification

### Task 47: Full backend test suite

- [ ] **Step 1: Run**

```bash
just test::run 'python manage.py test events discordbot org app -v 2'
```

Expected: all green.

- [ ] **Step 2: If any test fails, root-cause and fix.** Per project memory: "every test failure is a defect in our code or test until proven otherwise; pass-on-retry doesn't excuse it."

### Task 48: Full Playwright suite

- [ ] **Step 1: Run**

```bash
just test::pw::headless
```

Expected: all green.

- [ ] **Step 2: If any test fails, fix the underlying issue (not the test).**

### Task 49: Push branch + open PR

- [ ] **Step 1: Push**

```bash
cd /home/kettle/git_repos/draftforge/.worktrees/event-signup-form && git push -u origin feat/event-signup-form
```

- [ ] **Step 2: Open PR** (only if user explicitly asks).

```bash
gh pr create --title "feat: event signup form (web parity with discord)" --body "$(cat <<'EOF'
## Summary
- New POST /api/events/<id>/signup/ endpoint replacing /rsvp/ and /tentative/
- Shared apply_signup_input service used by web endpoint AND Discord adapters
- New EventSignupModal with conditional sections, skip-the-form fast path
- Brand-compliant per /brand review; uses existing tokens only
- All callers migrated; schema-drift snapshot regenerated

## Test plan
- [ ] just test::run 'python manage.py test events discordbot' green
- [ ] just test::pw::headless green
- [ ] Manual: complete-profile fast path on dev
- [ ] Manual: incomplete-profile modal + submit
- [ ] Manual: Discord embed still refreshes after web signup
- [ ] /brand review pass
EOF
)"
```

---

## Spec coverage check

- §"Goals" — covered by Tasks 5–14 (shared service), 16–20 (endpoint), 41 (modal), 44–46 (E2E).
- §"Field-name reference" — Task 8 (rank_status uses `allow_*`), Task 33 (`evaluateSignupGap` uses `require_steam_id`), Task 34 (schema builder). The reference table is consulted by every implementer touching these fields.
- §"Architecture / shared service" — Tasks 5–14.
- §"Resolving OrgUser" — Task 4 (`resolve_or_create_org_user`).
- §"Cacheops invalidation rules" — Task 13 (spy), Task 14 (rollback).
- §"New endpoint" — Tasks 16–20.
- §"Discord refactor" — Tasks 21–27.
- §"Tentative as a service" — Task 15.
- §"Removed endpoints + migration list" — Tasks 28–30, 45.
- §"Frontend file layout / EventSignupModal" — Tasks 36–41.
- §"Skip-the-form fast path" — Tasks 33, 43.
- §"Stale-profile defense" — Task 32 (`useUserDotaProfile`).
- §"Mutation wiring" — Task 42.
- §"Brand compliance" — embedded in Tasks 36–41 and 43 (component primitives, classes).
- §"Layout primitives (Dialog/Sheet)" — Task 41.
- §"Conditional sections + a11y" — Tasks 36–41.
- §"Form stack (memoization, shouldUnregister, defaults)" — Task 41.
- §"Test data — populate helper" — Tasks 1–2.
- §"Backend unit tests" — Tasks 5–14.
- §"Backend API tests" — Tasks 16–20.
- §"Discord regression tests + error vocab" — Tasks 21–27.
- §"Frontend Vitest" — Tasks 32, 33, 34, 35, 41.
- §"Playwright E2E + data-testid inventory" — Tasks 44–46.
- §"Schema-drift" — Task 30.
- §"Rollout" — Tasks 47–49.

No gaps detected.

---

## Plan complete

Plan saved to `docs/superpowers/plans/2026-05-06-event-signup-form.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Uses `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

**Which approach?**
