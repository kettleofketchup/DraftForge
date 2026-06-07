# T2 — Game User Profiles (Dota + Deadlock) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move user-wide Dota positions + Dota-MMR-verification + Deadlock rank off `CustomUser`/`Player*Profile` into new `DotaUserProfile` and `DeadlockUserProfile` models (FK → `BaseUserProfile`), expose them through the layered profile API + EditProfileModal Dota/Deadlock tabs, and migrate every user-scoped `positions` consumer to a `usePlayerPositions` hook.

**Architecture:** Mirror the T1 BaseUserProfile vertical slice one layer down. `BaseUserProfile.save()` auto-creates both game profiles. `CustomUser.positions` / `has_active_dota_mmr` / `dota_mmr_last_verified` columns drop and become transitional `@property` shims proxying to `dota_user_profile` (read + write, same pattern T1 used for nickname/avatar). `PositionsModel.save()` rewrites its invalidation walk from the now-empty `customuser_set` to `dotauserprofile_set`. Frontend gains `gameUser.dota`/`gameUser.deadlock` adapter layers, a `selectPositions` selector, a `usePlayerPositions` ambient hook, and two new modal tabs mirroring `BaseTab`.

**Tech Stack:** Django 5 + DRF + django-cacheops (backend); React 19 + Zustand + TanStack Query 5 + shadcn Form + Zod + Vitest + Playwright (frontend).

**Single PR.** Full Deadlock parity with Dota.

## Architecture decision — positions read from the flat, rendered-once, indexed `_users[]` entity adapter

The review found the original "migrate all consumers to `usePlayerPositions` over `userProfileStore`" is **broken**: `userProfileStore` is modal-scoped (one user at a time, populated only when an edit modal opens), so list/card/table/coverage surfaces would read `undefined` and positions would vanish.

**Correct design (per the existing pattern):** the backend renders a **flat `_users[]`** — each user serialized **exactly once** with the info those surfaces need (positions included), deduplicated (the `_build_users_dict` / tournament `_users` pattern at `backend/app/serializers.py:173`). The frontend **entity adapter** (`userCacheStore`, `createEntityAdapter` with `byDiscordId`/`bySteamAccountId` indexes) ingests that flat list on every roster/list/org-scoped load and indexes by pk — exactly as it does today. So positions are **list-populated and indexed** on `userCacheStore.UserEntry`, rendered once.

Therefore:
- `selectPositions(state, userPk, gameType)` and `usePlayerPositions(userPk)` read the **`userCacheStore`** entity adapter (list-populated, indexed) — NOT the modal `userProfileStore`. They are gameType-aware wrappers over the rendered-once positions, forward-compatible with T3 org overrides.
- The modal `userProfileStore` stays the **edit-only** layered source (base/gameUser/orgProfiles), populated per-user by the layered GET when a modal opens.
- The Dota tab's `onSuccess` **dual-writes**: `userCacheStore.upsert(...)` (so every list surface reflects the new positions immediately) AND `userProfileStore.upsert(...)` (edit layer) AND `invalidateQueries(['userProfile', pk])` — the same load-bearing multi-write T1's BaseTab used.
- `UserEntry.positions` is **NOT deprecated** — it IS the flat `_users[]` field, rendered once and indexed. The 11 consumers migrate to the gameType-aware `selectPositions`/`usePlayerPositions` selector over `userCacheStore`, not to raw field access and not to the modal store.

**Inherits the 24 lessons in `docs/plans/2026-05-17-user-profile-entity-adapter-epic-design.md` ("Patterns from T1").** The ones that bite hardest in T2:
- **#1 select_related discipline** — every queryset feeding a user serializer that ships positions needs `select_related("dota_user_profile__positions")` (reverse path) or `select_related("user__dota_user_profile__positions")`.
- **#2 pre-pk pending-buffer flush ordering** — `del self._pending_*` only AFTER the child save succeeds.
- **#3 writable transitional serializer fields**, **#15 split property vs column fields in merge loops**, **#21 reverse-O2O cache pollution → `refresh_from_db()` after repoint loops**, **#23 steam-id sync invariant**.
- **#22 test container is built from main** — new dev deps need an image rebuild or guarded `SkipTest`.
- **#24 live-Redis cacheops behavioral tests ship skipped**; the grep guardrail in `test_cacheops.py` is the load-bearing gate.
- **related_name discipline (T2 hard constraint):** the `positions` FK on `DotaUserProfile` MUST have NO explicit `related_name` (Django default `dotauserprofile_set`) so `PositionsModel.save()`'s walk works. Any other value silently breaks invalidation and fails CI.

---

## Ground-truth starting state (verified 2026-06-07)

**Backend — greenfield except T1 foundation:**
- `backend/user/models.py`: only `BaseUserProfile` (no `save()`). `DotaUserProfile`/`DeadlockUserProfile` are a comment only.
- `backend/app/models.py`: `PositionsModel` (carry/mid/offlane/soft_support/hard_support IntegerFields 0-5) with `save()` walking `self.customuser_set.all()` + bare `invalidate_obj` (lines 43-48). `CustomUser.positions` real FK (line 111). `CustomUser.has_active_dota_mmr` BooleanField (line 97), `dota_mmr_last_verified` DateTimeField (line 98), `active_dota_mmr` helper method (lines 103-107). `CustomUser.save()` (318+) auto-creates PositionsModel when `not self.positions_id`, auto-creates BaseUserProfile via get_or_create, flushes `_pending_nickname`/`_pending_avatar`. `nickname`/`avatar` @property shims at 135-185.
- `backend/org/models_profiles.py`: `PlayerDeadlockProfile` = `rank` (CharField) + `rank_date` (DateField), FK `org_user`. `PlayerDotaProfile.pos_1..pos_5` BOOLEANS (org-scoped, NOT PositionsModel) — leave untouched.
- `backend/user/serializers.py`: `BaseUserProfileSerializer`, `UserProfileLayeredSerializer` with `get_gameUser → {}`.
- `backend/user/views.py`: `MeProfileView` GET, `MeProfileBasePatchView` PATCH. `backend/user/urls.py`: `me/profile/`, `me/profile/base/`.
- CACHEOPS: `user.baseuserprofile` present; `user.dotauserprofile`/`user.deadlockuserprofile` absent.
- Migration heads: `user/0002_backfill_base_profiles`, `app/0095_remove_customuser_avatar_remove_customuser_nickname`.
- `UserSerializer` (app/serializers.py:1106) has writable `positions = PositionsSerializer(read_only=False)` + `update()` mutating `instance.positions` (1182-1189) — must keep working via shim.

**Frontend — greenfield except T1 foundation:**
- `usePlayerPositions` / `selectPositions`: zero hits — create new.
- `useGameType()` → `useGameTypeStore(s => s.currentGameType)` returns `GameTypeValue | null` — ready.
- `userProfileTypes.ts`: `DotaUserProfile = { positions?: never }`, `DeadlockUserProfile = { rank?: never }` (stubs to expand). `UserProfileEntry.gameUser.dota/deadlock` present.
- `userProfileStore.ts`: has `selectBase`; no `selectPositions`; `hasChanged()` already compares `gameUser` layers.
- `EditProfileModal.tsx`: Base tab only; `{/* T2 adds: ... */}` placeholder in TabsList.
- `userProfileApi.ts`: `getUserProfile`, `patchBaseProfile` — no game PATCH.
- `useUserDotaProfile()` in `hooks/useUserProfile.ts` is a SEPARATE org-scoped dota fetch (takes orgId, returns pos_1..5 booleans). **Do not touch / do not confuse with `usePlayerPositions`.**
- GAME_TYPE scalar ids: `GAME_TYPE.DOTA2 === 1` (from `~/components/game/constants`). The Dota tab reads positions with the explicit numeric id, NOT the ambient `currentGameType` (which is `null` off event pages — lesson in the spec's hooks section).

**Migration target set (11 user-scoped consumers):** `EventSignupModal/schema.ts`, `EventSignupModal/toPatch.ts`, `EventSignupModal.tsx`, `teamdraft/sections/AvailablePlayersSection.tsx`, `teamdraft/TeamPositionCoverage.tsx`, `user/positions/index.tsx`, `user/userCard/editUserSchema.ts`, `user/userCard.tsx`, `user/UserStrip.tsx`, `pages/profile/profile.tsx`, `pages/tournament/hasErrors.tsx`.

**Leave-alone set (6):** `EventSignupModal/evaluateSignupGap.ts`, `events/games/dota2/Dota2RankSignalsCard.tsx`, `user/CSVImportModal/CSVImportModal.tsx`, `user/CSVImportModal/csvParser.ts`, `user/UserEventStrip.tsx` (all read org-dota `pos_1..5` booleans or CSV columns, not user-wide PositionsModel).

---

## File structure

**Backend create:**
- `backend/user/migrations/0003_dota_deadlock_user_profiles.py` — schema (new models)
- `backend/user/migrations/0004_backfill_game_profiles.py` — data move from CustomUser
- `backend/app/migrations/0096_drop_customuser_positions_dota_mmr.py` — column drop (depends on user/0004)
- `backend/user/tests/test_game_profiles_models.py`, `test_game_auto_create.py`, `test_game_migration.py`, `test_game_serializers.py`, `test_game_views.py`, `test_positions_shim.py`, `test_positions_invalidation.py`

**Backend modify:**
- `backend/user/models.py` — add `DotaUserProfile`, `DeadlockUserProfile`, `BaseUserProfile.save()`
- `backend/user/admin.py` — register both
- `backend/user/serializers.py` — game serializers + `get_gameUser`
- `backend/user/views.py`, `backend/user/urls.py` — game PATCH endpoint
- `backend/app/models.py` — `PositionsModel.save()` rewrite; `CustomUser` positions/mmr shims; `CustomUser.save()` chain
- `backend/backend/settings.py` — CACHEOPS entries
- `backend/app/serializers.py` — `select_related` for the positions reverse path

**Frontend create:**
- `frontend/app/hooks/usePlayerPositions.ts` + `__tests__/usePlayerPositions.test.tsx`
- `frontend/app/pages/user/EditProfileModal/tabs/DotaTab.tsx`
- `frontend/app/pages/user/EditProfileModal/tabs/DeadlockTab.tsx`

**Frontend modify:**
- `frontend/app/store/userProfileTypes.ts`, `userProfileStore.ts` (+ `.test.ts`)
- `frontend/app/components/api/userProfileApi.ts`
- `frontend/app/pages/user/EditProfileModal.tsx`, `EditProfileModal/schemas.ts`
- 11 consumer files (Task 16)
- `frontend/tests/playwright/e2e/15-edit-user/08-position-persistence.spec.ts`

---

## Task 1: `DotaUserProfile` + `DeadlockUserProfile` models + admin + schema migration

**Files:**
- Modify: `backend/user/models.py`
- Modify: `backend/user/admin.py`
- Create: `backend/user/migrations/0003_dota_deadlock_user_profiles.py` (generated)
- Test: `backend/user/tests/test_game_profiles_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/user/tests/test_game_profiles_models.py
from django.test import TestCase
from app.models import CustomUser, PositionsModel
from user.models import BaseUserProfile, DotaUserProfile, DeadlockUserProfile


class GameProfileModelTests(TestCase):
    def test_dota_profile_fks_base_and_owns_positions(self):
        user = CustomUser.objects.create(username="dp")
        bp = user.base_profile
        pos = PositionsModel.objects.create(carry=5)
        dota = DotaUserProfile.objects.create(base_profile=bp, positions=pos)
        assert dota.base_profile_id == bp.pk
        assert dota.positions.carry == 5
        # related_name discipline: default reverse accessor must be dotauserprofile_set
        assert list(pos.dotauserprofile_set.all()) == [dota]
        assert bp.dota_user_profile == dota

    def test_dota_profile_mmr_fields_default(self):
        user = CustomUser.objects.create(username="dp2")
        dota = DotaUserProfile.objects.create(base_profile=user.base_profile)
        assert dota.has_active_dota_mmr is False
        assert dota.dota_mmr_last_verified is None

    def test_deadlock_profile_fks_base_with_rank(self):
        user = CustomUser.objects.create(username="dl")
        dl = DeadlockUserProfile.objects.create(
            base_profile=user.base_profile, rank="Archon"
        )
        assert dl.base_profile.user_id == user.pk
        assert dl.rank == "Archon"
        assert user.base_profile.deadlock_user_profile == dl
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_game_profiles_models -v 2'`
Expected: FAIL — `ImportError: cannot import name 'DotaUserProfile'`.

- [ ] **Step 3: Add the models**

In `backend/user/models.py`, after `BaseUserProfile`:

```python
class DotaUserProfile(models.Model):
    """User-wide Dota profile. Owns position preferences + MMR-verification state
    that used to live on CustomUser (T2 epic)."""

    base_profile = models.OneToOneField(
        BaseUserProfile,
        on_delete=models.CASCADE,
        related_name="dota_user_profile",
        db_index=True,
    )
    # NO related_name on positions: PositionsModel.save() walks the Django
    # default reverse accessor `dotauserprofile_set`. Changing this silently
    # breaks cache invalidation (T2 hard constraint).
    positions = models.ForeignKey(
        "app.PositionsModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Dota User Profile"

    def __str__(self):
        return f"DotaUserProfile({self.base_profile.user_id})"


class DeadlockUserProfile(models.Model):
    """User-wide Deadlock profile. Mirrors org.PlayerDeadlockProfile's
    user-relevant fields (T2 epic)."""

    base_profile = models.OneToOneField(
        BaseUserProfile,
        on_delete=models.CASCADE,
        related_name="deadlock_user_profile",
        db_index=True,
    )
    rank = models.CharField(max_length=64, null=True, blank=True)
    rank_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Deadlock User Profile"

    def __str__(self):
        return f"DeadlockUserProfile({self.base_profile.user_id})"
```

In `backend/user/admin.py`, register both (mirror the existing `BaseUserProfile` registration).

- [ ] **Step 4: Generate the schema migration**

Run: `just db::makemigrations user`
Expected: creates `backend/user/migrations/0003_dota_deadlock_user_profiles.py` with two `CreateModel` ops. Open it and confirm: no data ops, FK to `app.positionsmodel`, depends on `user/0002`.

- [ ] **Step 5: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_game_profiles_models -v 2'`
Expected: PASS (3 tests). NOTE: these create `DotaUserProfile` explicitly — auto-create comes in Task 2.

- [ ] **Step 6: Commit**

```bash
git add backend/user/models.py backend/user/admin.py backend/user/migrations/0003_dota_deadlock_user_profiles.py backend/user/tests/test_game_profiles_models.py
git commit -m "feat(user): DotaUserProfile + DeadlockUserProfile models + schema migration (T2.1, epic #224)"
```

---

## Task 2: Auto-create game profiles on `BaseUserProfile.save()`

**Files:**
- Modify: `backend/user/models.py` (`BaseUserProfile.save()`)
- Test: `backend/user/tests/test_game_auto_create.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/user/tests/test_game_auto_create.py
from django.test import TestCase
from app.models import CustomUser
from user.models import DotaUserProfile, DeadlockUserProfile


class GameProfileAutoCreateTests(TestCase):
    def test_creating_user_creates_both_game_profiles(self):
        user = CustomUser.objects.create(username="auto")
        bp = user.base_profile
        assert DotaUserProfile.objects.filter(base_profile=bp).count() == 1
        assert DeadlockUserProfile.objects.filter(base_profile=bp).count() == 1
        assert bp.dota_user_profile is not None
        assert bp.deadlock_user_profile is not None

    def test_idempotent_on_resave(self):
        user = CustomUser.objects.create(username="idem")
        user.base_profile.save()
        user.base_profile.save()
        assert DotaUserProfile.objects.filter(base_profile=user.base_profile).count() == 1
        assert DeadlockUserProfile.objects.filter(base_profile=user.base_profile).count() == 1
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_game_auto_create -v 2'`
Expected: FAIL — `RelatedObjectDoesNotExist: BaseUserProfile has no dota_user_profile`.

- [ ] **Step 3: Add `BaseUserProfile.save()`**

In `backend/user/models.py`, add to `BaseUserProfile`:

```python
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-create user-wide game profiles. Idempotent via get_or_create.
        # invalidate_after_commit (not bare invalidate_obj) because this runs
        # inside the parent CustomUser.save() transaction (epic lesson:
        # auto-create within transaction.atomic).
        from app.cache_utils import invalidate_after_commit

        # CRITICAL: positions default MUST be a callable so PositionsModel is
        # created ONLY on the create branch. A bare
        # defaults={"positions": PositionsModel.objects.create()} evaluates the
        # create() on EVERY call (the dict is built before the lookup), leaking
        # an orphan PositionsModel row on every idempotent resave. Django
        # resolves callable defaults only when actually creating.
        from app.models import PositionsModel
        dota, dota_created = DotaUserProfile.objects.get_or_create(
            base_profile=self,
            defaults={"positions": lambda: PositionsModel.objects.create()},
        )
        deadlock, dl_created = DeadlockUserProfile.objects.get_or_create(base_profile=self)
        targets = []
        if dota_created:
            targets.append(dota)
        if dl_created:
            targets.append(deadlock)
        if targets:
            invalidate_after_commit(*targets)
```

Note: `DotaUserProfile`/`DeadlockUserProfile` are defined later in the same module — the references resolve at call time, not import time, so forward refs are fine. If a `NameError` appears at runtime, move the two model classes ABOVE `BaseUserProfile` or import lazily.

- [ ] **Step 4: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_game_auto_create user.tests.test_auto_create -v 2'`
Expected: PASS (both new tests + the T1 base auto-create tests still green).

- [ ] **Step 5: Commit**

```bash
git add backend/user/models.py backend/user/tests/test_game_auto_create.py
git commit -m "feat(user): auto-create Dota/Deadlock profiles on BaseUserProfile.save() (T2.2, epic #224)"
```

---

## Task 3: CACHEOPS entries + grep guardrail extension

**Files:**
- Modify: `backend/backend/settings.py` (CACHEOPS block)
- Modify: `backend/user/tests/test_cacheops.py` (SCAN_TARGETS / guardrail)
- Test: `backend/user/tests/test_cacheops.py` (existing + extended)

- [ ] **Step 1: Add CACHEOPS entries**

In `backend/backend/settings.py`, in the `CACHEOPS` dict (the non-DISABLE_CACHE branch), after `"user.baseuserprofile"`:

```python
        "user.dotauserprofile": {"ops": "all", "timeout": 60 * 60},
        "user.deadlockuserprofile": {"ops": "all", "timeout": 60 * 60},
```

Do NOT add `app.positionsmodel` — PositionsModel stays uncached; its `save()` is the only invalidation mechanism (Task 6).

- [ ] **Step 2: Extend the grep guardrail test**

Read `backend/user/tests/test_cacheops.py`. It greps `@cached_as(...CustomUser...)` blocks and asserts each also lists `BaseUserProfile`. Extend it so that any `@cached_as` block shipping POSITIONS (i.e. lists `CustomUser` and the view serializes positions) also lists `DotaUserProfile`. Concretely, add a test mirroring the existing one:

```python
    def test_every_customuser_cached_as_block_also_lists_dotauserprofile(self):
        """Any @cached_as(CustomUser, ...) site that ships positions must also
        depend on DotaUserProfile so a PATCH to /me/profile/game/dota/ evicts it.
        Positions ship on the same user-list/detail/org/league endpoints that T1
        guarded for BaseUserProfile, so the dependency set is identical."""
        offenders = []
        for path in self._cached_as_files():  # reuse existing helper
            for block in self._cached_as_blocks(path):  # reuse existing helper
                if "CustomUser" in block and "DotaUserProfile" not in block:
                    offenders.append((path, block[:80]))
        assert not offenders, f"@cached_as missing DotaUserProfile dep: {offenders}"
```

If the existing test file doesn't expose `_cached_as_files` / `_cached_as_blocks` helpers, factor the existing test's scanning logic into module-level helpers first, then write both the BaseUserProfile and DotaUserProfile assertions against them (DRY).

- [ ] **Step 3: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_cacheops -v 2'`
Expected: FAIL — every `@cached_as(CustomUser, BaseUserProfile, ...)` site in `backend/app/views_main.py` + `backend/app/functions/tournament.py` lacks `DotaUserProfile`.

- [ ] **Step 4: Add DotaUserProfile to every CustomUser `@cached_as` site**

For each offender from Step 3, add `DotaUserProfile` to the `@cached_as(...)` dependency list (import `from user.models import DotaUserProfile`). These are the same sites T1 updated for `BaseUserProfile` — `rg "@cached_as\(.*CustomUser" backend/app/ backend/user/`.

- [ ] **Step 5: Run, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_cacheops -v 2'`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/backend/settings.py backend/user/tests/test_cacheops.py backend/app/views_main.py backend/app/functions/tournament.py
git commit -m "feat(user): cacheops integration for Dota/Deadlock profiles + grep guardrail (T2.3, epic #224)"
```

---

## Task 4: Data migration — backfill game profiles from CustomUser

**Files:**
- Create: `backend/user/migrations/0004_backfill_game_profiles.py`
- Test: `backend/user/tests/test_game_migration.py`

- [ ] **Step 1: Write the failing migration test**

```python
# backend/user/tests/test_game_migration.py
import unittest
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as e:  # lesson #22: test image may predate the dev dep
    raise unittest.SkipTest("django-test-migrations not installed") from e


class BackfillGameProfilesTest(MigratorTestCase):
    migrate_from = ("user", "0003_dota_deadlock_user_profiles")
    migrate_to = ("user", "0004_backfill_game_profiles")

    def prepare(self):
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        pos = PositionsModel.objects.create(carry=4, mid=2)
        u = CustomUser.objects.create(
            username="mig", positions=pos,
            has_active_dota_mmr=True,
        )
        # T1 historical save does NOT auto-create base_profile (historical model);
        # create it explicitly so 0004 has a parent to attach to.
        BaseUserProfile.objects.get_or_create(user_id=u.pk)

    def test_dota_profile_backfilled_with_positions_and_mmr(self):
        DotaUserProfile = self.new_state.apps.get_model("user", "DotaUserProfile")
        DeadlockUserProfile = self.new_state.apps.get_model("user", "DeadlockUserProfile")
        dota = DotaUserProfile.objects.get(base_profile__user__username="mig")
        assert dota.positions.carry == 4
        assert dota.has_active_dota_mmr is True
        # every base profile also got a (empty) deadlock profile
        assert DeadlockUserProfile.objects.filter(
            base_profile__user__username="mig"
        ).exists()
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_game_migration -v 2'`
Expected: FAIL — migration `0004_backfill_game_profiles` does not exist.

- [ ] **Step 3: Write the data migration**

```python
# backend/user/migrations/0004_backfill_game_profiles.py
from django.db import migrations


def backfill_game_profiles(apps, schema_editor):
    # Defensive cache clear (mirrors T1 user/0002): django-redis hard-fails on
    # Redis-down, unlike cacheops which degrades. Wrap so cold-start / broken-
    # Redis CI doesn't fail the migration.
    from django.core.cache import cache
    try:
        cache.clear()
    except Exception:
        pass

    CustomUser = apps.get_model("app", "CustomUser")
    BaseUserProfile = apps.get_model("user", "BaseUserProfile")
    DotaUserProfile = apps.get_model("user", "DotaUserProfile")
    DeadlockUserProfile = apps.get_model("user", "DeadlockUserProfile")

    dota_to_create = []
    deadlock_to_create = []
    # CustomUser still has positions / has_active_dota_mmr / dota_mmr_last_verified
    # columns at this migration (they drop in app/0096, which depends on this).
    for user in CustomUser.objects.all().iterator(chunk_size=1000):
        bp, _ = BaseUserProfile.objects.get_or_create(user_id=user.pk)
        if not DotaUserProfile.objects.filter(base_profile_id=bp.pk).exists():
            dota_to_create.append(
                DotaUserProfile(
                    base_profile_id=bp.pk,
                    positions_id=user.positions_id,
                    has_active_dota_mmr=user.has_active_dota_mmr,
                    dota_mmr_last_verified=user.dota_mmr_last_verified,
                )
            )
        if not DeadlockUserProfile.objects.filter(base_profile_id=bp.pk).exists():
            deadlock_to_create.append(DeadlockUserProfile(base_profile_id=bp.pk))

    DotaUserProfile.objects.bulk_create(dota_to_create, ignore_conflicts=True)
    DeadlockUserProfile.objects.bulk_create(deadlock_to_create, ignore_conflicts=True)

    # bulk_create bypasses post_save signals — invalidate explicitly (lesson:
    # bulk_update/bulk_create invariant).
    try:
        from cacheops import invalidate_model
        invalidate_model(CustomUser)
        invalidate_model(BaseUserProfile)
        invalidate_model(DotaUserProfile)
        invalidate_model(DeadlockUserProfile)
    except ImportError:
        pass


def reverse_backfill(apps, schema_editor):
    # Copy positions/mmr back onto CustomUser before app/0096 re-adds the columns.
    CustomUser = apps.get_model("app", "CustomUser")
    DotaUserProfile = apps.get_model("user", "DotaUserProfile")
    for dota in DotaUserProfile.objects.all().select_related("base_profile").iterator(
        chunk_size=1000
    ):
        CustomUser.objects.filter(pk=dota.base_profile.user_id).update(
            positions_id=dota.positions_id,
            has_active_dota_mmr=dota.has_active_dota_mmr,
            dota_mmr_last_verified=dota.dota_mmr_last_verified,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0003_dota_deadlock_user_profiles"),
    ]
    operations = [
        migrations.RunPython(backfill_game_profiles, reverse_backfill),
    ]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_game_migration -v 2'`
Expected: PASS (1 test; the skip-guard imports `django_test_migrations`).

- [ ] **Step 5: Add idempotency + reverse tests** (lesson: migrations tested forward-once is insufficient)

Append two more test classes mirroring T1's `test_migration.py` structure: `BackfillIdempotencyTest` (re-run the forward func, assert row counts unchanged) and `BackfillReverseTest` (mutate DotaUserProfile post-migrate, run `reverse_backfill`, assert CustomUser columns reflect the new value). Use `importlib.import_module("user.migrations.0004_backfill_game_profiles")`.

- [ ] **Step 6: Run, verify pass, commit**

```bash
just test::run 'python manage.py test user.tests.test_game_migration -v 2'
git add backend/user/migrations/0004_backfill_game_profiles.py backend/user/tests/test_game_migration.py
git commit -m "feat(user): data migration backfills Dota/Deadlock profiles from CustomUser (T2.4, epic #224)"
```

---

## Task 5: Drop CustomUser positions/mmr columns + transitional `@property` shims

**Files:**
- Modify: `backend/app/models.py` (`CustomUser` — add shims, adjust `save()`)
- Create: `backend/app/migrations/0096_drop_customuser_positions_dota_mmr.py`
- Test: `backend/user/tests/test_positions_shim.py`

- [ ] **Step 1: Write the failing shim test**

```python
# backend/user/tests/test_positions_shim.py
from django.test import TestCase
from app.models import CustomUser, PositionsModel


class PositionsShimTests(TestCase):
    def test_positions_getter_reads_from_dota_profile(self):
        user = CustomUser.objects.create(username="g")
        user.dota_user_profile.positions = PositionsModel.objects.create(carry=5)
        user.dota_user_profile.save()
        assert user.positions.carry == 5

    def test_positions_setter_writes_to_dota_profile(self):
        user = CustomUser.objects.create(username="s")
        pos = PositionsModel.objects.create(mid=3)
        user.positions = pos  # transitional setter persists immediately
        user.base_profile.dota_user_profile.refresh_from_db()
        assert user.base_profile.dota_user_profile.positions_id == pos.pk

    def test_has_active_dota_mmr_shim_round_trip(self):
        user = CustomUser.objects.create(username="m")
        user.has_active_dota_mmr = True
        user.base_profile.dota_user_profile.refresh_from_db()
        assert user.base_profile.dota_user_profile.has_active_dota_mmr is True
        assert user.has_active_dota_mmr is True

    def test_positions_removed_from_meta(self):
        names = {f.name for f in CustomUser._meta.get_fields()}
        assert "positions" not in names  # column dropped; property remains
        assert "has_active_dota_mmr" not in names
        assert "dota_mmr_last_verified" not in names

    def test_objects_create_with_positions_uses_setter(self):
        # populate-style call shape (lesson: __init__ dispatches to the descriptor)
        pos = PositionsModel.objects.create(carry=2)
        user = CustomUser.objects.create(username="pc", positions=pos)
        user.base_profile.dota_user_profile.refresh_from_db()
        assert user.base_profile.dota_user_profile.positions_id == pos.pk
        assert not hasattr(user, "_pending_positions")
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_positions_shim -v 2'`
Expected: FAIL — `positions` is still a real field; setter doesn't proxy.

- [ ] **Step 3: Replace the column with shims in `CustomUser`**

In `backend/app/models.py`: delete the `positions = models.ForeignKey(...)` (line ~111), `has_active_dota_mmr` (97), `dota_mmr_last_verified` (98) field declarations. Add shims mirroring the nickname/avatar pattern (lines 135-185). Positions getter/setter:

```python
    @property
    def positions(self):
        """Transitional proxy — reads positions from dota_user_profile.
        Removed in a cleanup ticket once writers migrate to
        PATCH /api/users/me/profile/game/dota/."""
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.positions if dp else None

    @positions.setter
    def positions(self, value):
        from app.cache_utils import invalidate_after_commit
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        if dp is None:
            self._pending_positions = value
            return
        dp.positions = value
        dp.save(update_fields=["positions"])
        invalidate_after_commit(dp)

    @property
    def positions_id(self):
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.positions_id if dp else None

    @property
    def has_active_dota_mmr(self):
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.has_active_dota_mmr if dp else False

    @has_active_dota_mmr.setter
    def has_active_dota_mmr(self, value):
        from app.cache_utils import invalidate_after_commit
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        if dp is None:
            self._pending_has_active_dota_mmr = value
            return
        dp.has_active_dota_mmr = value
        dp.save(update_fields=["has_active_dota_mmr"])
        invalidate_after_commit(dp)

    @property
    def dota_mmr_last_verified(self):
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.dota_mmr_last_verified if dp else None

    @dota_mmr_last_verified.setter
    def dota_mmr_last_verified(self, value):
        from app.cache_utils import invalidate_after_commit
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        if dp is None:
            self._pending_dota_mmr_last_verified = value
            return
        dp.dota_mmr_last_verified = value
        dp.save(update_fields=["dota_mmr_last_verified"])
        invalidate_after_commit(dp)
```

- [ ] **Step 4: Adjust `CustomUser.save()` pending-flush**

The current `save()` auto-creates a `PositionsModel` when `not self.positions_id` and flushes `_pending_nickname`/`_pending_avatar`. Update it: (a) the positions auto-create now happens on the DotaUserProfile (it has `null=True` positions; auto-create a `PositionsModel` for a fresh dota profile if you want the prior default-positions behavior — do it in `BaseUserProfile.save()` Task 2's get_or_create defaults instead: `DotaUserProfile.objects.get_or_create(base_profile=self, defaults={"positions": PositionsModel.objects.create()})`). (b) After `BaseUserProfile` is ensured and game profiles auto-created, flush the three new pending buffers. Flush ordering per lesson #2: `del` only AFTER the child `save()` succeeds.

```python
        # 6. Flush pending positions/mmr buffered by the shims pre-pk.
        bp = self.base_profile
        dp = bp.dota_user_profile
        dota_fields = []
        if hasattr(self, "_pending_positions"):
            dp.positions = self._pending_positions
            dota_fields.append("positions")
        if hasattr(self, "_pending_has_active_dota_mmr"):
            dp.has_active_dota_mmr = self._pending_has_active_dota_mmr
            dota_fields.append("has_active_dota_mmr")
        if hasattr(self, "_pending_dota_mmr_last_verified"):
            dp.dota_mmr_last_verified = self._pending_dota_mmr_last_verified
            dota_fields.append("dota_mmr_last_verified")
        if dota_fields:
            from app.cache_utils import invalidate_after_commit
            dp.save(update_fields=dota_fields)
            invalidate_after_commit(dp)
            for attr in ("_pending_positions", "_pending_has_active_dota_mmr",
                         "_pending_dota_mmr_last_verified"):
                if hasattr(self, attr):
                    delattr(self, attr)
```

**Delete** the old `if not self.positions_id: PositionsModel.objects.create()` block (lines ~337-340) — default positions are now created in Task 2's `get_or_create(defaults={"positions": lambda: PositionsModel.objects.create()})`. If you don't delete it, the property setter fires mid-`save()` before `base_profile`/`dota_user_profile` exist (buffering into `_pending_positions`), which is wasteful and confusing.

**`save()` is INSERT-not-rewrite:** the steps above (steam 32/64-bit `steam_account_id`↔`steamid` sync — lesson #23 — and the `_pending_nickname`/`_pending_avatar` flush from T1) MUST be preserved verbatim. Only ADD the dota pending-flush block below; do not rewrite or drop the existing save() body.

- [ ] **Step 5: Generate the column-drop migration**

Run: `just db::makemigrations app`
Expected: `backend/app/migrations/0096_...` with `RemoveField` for positions, has_active_dota_mmr, dota_mmr_last_verified. **Edit it**: add `("user", "0004_backfill_game_profiles")` to `dependencies` so the drop cannot run before the backfill (lesson: T1 ordering). Rename file to `0096_drop_customuser_positions_dota_mmr.py` if makemigrations auto-named it differently — keep the migration class name Django generated.

- [ ] **Step 6: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_positions_shim user.tests.test_game_auto_create -v 2'`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/0096_drop_customuser_positions_dota_mmr.py backend/user/tests/test_positions_shim.py backend/user/models.py
git commit -m "feat(user): drop CustomUser positions/dota-mmr columns + transitional shims (T2.5, epic #224)"
```

---

## Task 6: Rewrite `PositionsModel.save()` invalidation walk

**Files:**
- Modify: `backend/app/models.py` (`PositionsModel.save()`, lines 43-48)
- Test: `backend/user/tests/test_positions_invalidation.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/user/tests/test_positions_invalidation.py
from unittest.mock import patch
from django.test import TestCase
from app.models import CustomUser, PositionsModel


class PositionsInvalidationTests(TestCase):
    def test_save_walks_dotauserprofile_set_not_customuser_set(self):
        user = CustomUser.objects.create(username="inv")
        pos = user.base_profile.dota_user_profile.positions
        assert pos is not None
        # save() must invalidate the owning dota profile + bubbled parents,
        # NOT raise AttributeError on the now-empty customuser_set.
        with patch("app.cache_utils.invalidate_after_commit") as mock_inv:
            pos.carry = 5
            pos.save()
            assert mock_inv.called
            invalidated = mock_inv.call_args.args
            # dota profile, base profile, and user all targeted
            assert user.base_profile.dota_user_profile in invalidated
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_positions_invalidation -v 2'`
Expected: FAIL — current `save()` walks `customuser_set` (empty after T2) so `invalidate_after_commit` is never called; assertion fails.

- [ ] **Step 3: Rewrite `PositionsModel.save()`**

Replace lines 43-48 in `backend/app/models.py`:

```python
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from app.cache_utils import invalidate_after_commit
        # T2: positions live on user.DotaUserProfile (default reverse accessor
        # dotauserprofile_set). Walk it + bubbled parents. Org positions are
        # pos_1..5 booleans on org.PlayerDotaProfile (no PositionsModel FK) —
        # cacheops auto-invalidates that model; not this loop. Org branch is T3.
        dota_profiles = list(
            self.dotauserprofile_set.select_related("base_profile__user")
        )
        targets = []
        for dp in dota_profiles:
            targets += [dp, dp.base_profile, dp.base_profile.user]
        if targets:
            invalidate_after_commit(*targets)
```

**No bespoke log here.** `invalidate_after_commit` already emits a `cache_invalidate` log (`system="cache", subsystem="invalidate"`) per target on commit — a `positions_invalidated` line would duplicate it, and `subsystem="cache"` isn't in the taxonomy (the `cache` system owns invalidation logging). This matches T1: its nickname/avatar shims add no bespoke cache log. (`log` already exists at `app/models.py:8,16` if any other log is ever needed — no import change required.) Remove the old `from app.cache_utils import invalidate_obj` import if now unused after this rewrite.

- [ ] **Step 4: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_positions_invalidation -v 2'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/user/tests/test_positions_invalidation.py
git commit -m "feat(user): rewrite PositionsModel.save() to walk dotauserprofile_set (T2.6, epic #224)"
```

---

## Task 7: Game profile serializers + `get_gameUser`

**Files:**
- Modify: `backend/user/serializers.py`
- Test: `backend/user/tests/test_game_serializers.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/user/tests/test_game_serializers.py
from django.test import TestCase
from app.models import CustomUser, PositionsModel
from user.serializers import UserProfileLayeredSerializer


class GameUserSerializerTests(TestCase):
    def test_layered_gameuser_has_dota_and_deadlock(self):
        user = CustomUser.objects.create(username="ser")
        user.dota_user_profile.positions = PositionsModel.objects.create(carry=4)
        user.dota_user_profile.save()
        dl = user.base_profile.deadlock_user_profile
        dl.rank = "Phantom"
        dl.save()

        data = UserProfileLayeredSerializer(user).data
        assert data["gameUser"]["dota"]["positions"]["carry"] == 4
        assert data["gameUser"]["dota"]["has_active_dota_mmr"] is False
        assert data["gameUser"]["deadlock"]["rank"] == "Phantom"
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_game_serializers -v 2'`
Expected: FAIL — `get_gameUser` returns `{}`.

- [ ] **Step 3: Add serializers + populate `get_gameUser`**

In `backend/user/serializers.py`:

```python
from app.serializers import PositionsSerializer  # existing carry/mid/... serializer
from .models import DotaUserProfile, DeadlockUserProfile


class DotaUserProfileSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(required=False, allow_null=True)

    class Meta:
        model = DotaUserProfile
        fields = ["positions", "has_active_dota_mmr", "dota_mmr_last_verified"]


class DeadlockUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeadlockUserProfile
        fields = ["rank", "rank_date"]
```

Update `UserProfileLayeredSerializer.get_gameUser`:

```python
    def get_gameUser(self, user: CustomUser) -> dict:
        bp = user.base_profile
        return {
            "dota": DotaUserProfileSerializer(bp.dota_user_profile).data,
            "deadlock": DeadlockUserProfileSerializer(bp.deadlock_user_profile).data,
        }
```

- [ ] **Step 4: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_game_serializers -v 2'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/user/serializers.py backend/user/tests/test_game_serializers.py
git commit -m "feat(user): Dota/Deadlock serializers + layered gameUser (T2.7, epic #224)"
```

---

## Task 8: `PATCH /api/users/me/profile/game/{game}/` endpoint

**Files:**
- Modify: `backend/user/views.py`, `backend/user/urls.py`
- Test: `backend/user/tests/test_game_views.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/user/tests/test_game_views.py
from django.test import TestCase
from rest_framework.test import APIClient
from app.models import CustomUser


class MeProfileGamePatchTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="gp")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_patch_dota_positions(self):
        r = self.client.patch(
            "/api/users/me/profile/game/dota/",
            data={"positions": {"carry": 5, "mid": 1, "offlane": 0,
                                "soft_support": 0, "hard_support": 0}},
            format="json",
        )
        assert r.status_code == 200, r.content
        self.user.base_profile.dota_user_profile.refresh_from_db()
        assert self.user.base_profile.dota_user_profile.positions.carry == 5

    def test_patch_deadlock_rank(self):
        r = self.client.patch(
            "/api/users/me/profile/game/deadlock/",
            data={"rank": "Ascendant"}, format="json",
        )
        assert r.status_code == 200, r.content
        self.user.base_profile.deadlock_user_profile.refresh_from_db()
        assert self.user.base_profile.deadlock_user_profile.rank == "Ascendant"

    def test_patch_deadlock_rank_blank_and_null(self):
        # DeadlockUserProfile.rank is null=True/blank=True, so a bare
        # ModelSerializer auto-infers allow_blank/allow_null (same as T1's
        # nickname). Clearing must NOT 400 (lesson #5).
        r1 = self.client.patch("/api/users/me/profile/game/deadlock/",
                               data={"rank": ""}, format="json")
        assert r1.status_code == 200, r1.content
        r2 = self.client.patch("/api/users/me/profile/game/deadlock/",
                               data={"rank": None}, format="json")
        assert r2.status_code == 200, r2.content

    def test_unknown_game_404(self):
        r = self.client.patch("/api/users/me/profile/game/chess/",
                              data={}, format="json")
        assert r.status_code == 404

    def test_patch_unauthenticated(self):
        c = APIClient()
        r = c.patch("/api/users/me/profile/game/dota/", data={}, format="json")
        assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run, verify it fails**

Run: `just test::run 'python manage.py test user.tests.test_game_views -v 2'`
Expected: FAIL — 404 (no route).

- [ ] **Step 3: Add the view**

In `backend/user/views.py` (mirror `MeProfileBasePatchView`):

```python
from .serializers import DotaUserProfileSerializer, DeadlockUserProfileSerializer

_GAME_MAP = {
    "dota": ("dota_user_profile", DotaUserProfileSerializer),
    "deadlock": ("deadlock_user_profile", DeadlockUserProfileSerializer),
}


class MeProfileGamePatchView(APIView):
    """PATCH /api/users/me/profile/game/<game>/ — updates a game profile."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, game):
        entry = _GAME_MAP.get(game)
        if entry is None:
            return Response({"detail": "unknown game"}, status=status.HTTP_404_NOT_FOUND)
        attr, serializer_cls = entry
        instance = getattr(request.user.base_profile, attr)
        serializer = serializer_cls(instance=instance, data=request.data, partial=True)
        if not serializer.is_valid():
            log.warning("profile_game_patch_invalid", system="user",
                        subsystem="profile", user_id=request.user.id,
                        game=game, errors=serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        log.info("profile_game_patched", system="user", subsystem="profile",
                 user_id=request.user.id, game=game,
                 fields_changed=sorted(serializer.validated_data.keys()))
        return Response(serializer.data, status=status.HTTP_200_OK)
```

`DotaUserProfileSerializer` has a nested `positions` writable serializer — add an `update()` to it that mutates the related `PositionsModel` (mirror `UserSerializer.update`'s positions handling at `app/serializers.py:1182-1189`): pop `positions`, `setattr` each field on `instance.positions` (create one if null), `instance.positions.save()`.

- [ ] **Step 4: Add the route**

In `backend/user/urls.py`:

```python
path("me/profile/game/<str:game>/", MeProfileGamePatchView.as_view(), name="me-profile-game"),
```

- [ ] **Step 5: Run tests, verify pass**

Run: `just test::run 'python manage.py test user.tests.test_game_views -v 2'`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/user/views.py backend/user/urls.py backend/user/serializers.py backend/user/tests/test_game_views.py
git commit -m "feat(user): PATCH /me/profile/game/<game>/ endpoint with structlog (T2.8, epic #224)"
```

---

## Task 9: Fix every post-shim positions breakage (select_related FieldError, save(update_fields), None-guards)

> **Two distinct breakage classes** appear the moment `positions` becomes a `@property` (after Task 5). The plan's first draft only saw the first. Both crash production paths.

**Files:**
- Modify (FieldError class): `backend/app/views_main.py`, `backend/app/serializers.py`, `backend/app/views/admin_team.py`
- Modify (save(update_fields) crash class): `backend/events/services.py`
- Modify (None-guard class): `backend/app/serializers.py` (`UserSerializer.update`), `backend/app/functions/user.py`
- Cross-app N+1 sweep: `backend/org/serializers.py`, `backend/league/serializers.py` (nested `source="user.positions"` keeps working via the property but their feeding querysets need the new select_related to avoid N+1)
- Test: broad backend suite + `events` suite

- [ ] **Step 1: FieldError class — replace dead `select_related` strings.**

After the column drops, `select_related("positions")` / `select_related("user__positions")` raise `FieldError: Invalid field name(s) given in select_related: 'positions'`. New reverse path: direct user queryset → `select_related("base_profile__dota_user_profile__positions")`; reverse-through OrgUser/LeagueUser → `select_related("user__base_profile__dota_user_profile__positions")`. Confirmed offending sites:
- `backend/app/views_main.py:174, 1133, 1282, 1327`
- `backend/app/serializers.py:124, 174`
- `backend/app/views/admin_team.py:75, 732`

Re-grep to confirm none missed: `rg -n 'select_related\([^)]*positions' backend --type py`.

- [ ] **Step 2: save(update_fields) crash class — delete the now-illegal writes.**

`user.save(update_fields=["positions"])` raises `ValueError: The following fields do not exist in this model: positions` (a property is not a concrete field). Sites (production):
- `backend/events/services.py:457` and `backend/events/services.py:663`

**Delete these `user.save(update_fields=["positions"])` lines entirely** — the Task 5 property setter (`user.positions = ...`) already persisted via `dp.save(update_fields=["positions"]) + invalidate_after_commit(dp)`. Leaving them crashes signup approval / `apply_signup_input`. Also fix test sites surfaced by the run: `backend/events/tests/test_signup_input.py:75,95,116` (same pattern).

- [ ] **Step 3: None-guard class — positions can now be `None` (SET_NULL).**

Old `CustomUser.positions` was `null=False`; new `DotaUserProfile.positions` is `null=True, on_delete=SET_NULL`, so the shim getter can return `None`. Guard the two writers that assume non-null:
- `backend/app/serializers.py:1184` (`UserSerializer.update`): `positions_instance = instance.positions` then `setattr(positions_instance, ...)`. If `instance.positions is None`, create one first: `if instance.positions is None: instance.positions = PositionsModel.objects.create()` (the setter persists it), then re-read `instance.positions`.
- `backend/app/functions/user.py:65`: `PositionsModel.objects.get(pk=user.positions.pk)` → `AttributeError` on None. Guard: `if user.positions is None: ...` (skip or create-on-demand to match prior behavior).
- (`backend/events/services.py:454` already guards `if user_positions is None` — leave it.)

- [ ] **Step 4: Run the broad suites, verify green.**

Run: `just test::run 'python manage.py test app user events -v 2'`
Expected: PASS. Fix any remaining `FieldError`/`ValueError` from a missed site by applying the matching fix above. Fix any test that set `user.positions` and asserted via the old column.

- [ ] **Step 5: Commit**

```bash
git add backend/app/serializers.py backend/app/views_main.py backend/app/views/admin_team.py backend/events/services.py backend/app/functions/user.py backend/events/tests/test_signup_input.py
git commit -m "fix(user): chase post-shim positions breakages — select_related, save(update_fields), None-guards (T2.9, epic #224)"
```

---

## Task 10: Expand edit-layer types + `selectPositions` selector over the list-populated `userCacheStore`

> **Architecture (revised):** `selectPositions` reads the **flat `_users[]` entity adapter** (`userCacheStore`, list-populated + indexed), NOT the modal-scoped `userProfileStore`. `UserEntry.positions` is the rendered-once flat field every roster/list load hydrates. The `userProfileStore` gameUser types still get expanded — they're the **edit-layer** shape the modal reads/writes.

**Files:**
- Modify: `frontend/app/store/userProfileTypes.ts` (edit-layer types), `frontend/app/store/userCacheTypes.ts` (confirm `UserEntry.positions` shape)
- Create: `frontend/app/store/selectPositions.ts` (selector over userCacheStore) — or co-locate in `userCacheStore.ts`
- Test: `frontend/app/store/userCacheStore.test.ts` (or the selectPositions test file)

- [ ] **Step 1: Confirm the flat field + write the failing Vitest**

Read `frontend/app/store/userCacheTypes.ts` — `UserEntry.positions` already carries the flat `{carry,mid,offlane,soft_support,hard_support}` (the rendered-once `_users[]` field). Write a test that seeds `userCacheStore` and reads via `selectPositions`:

```typescript
// in userCacheStore.test.ts (or a new selectPositions.test.ts)
import { useUserCacheStore } from '~/store/userCacheStore';
import { selectPositions } from '~/store/selectPositions';
import { GAME_TYPE } from '~/components/game/constants';

it('selectPositions reads positions off the list-populated userCacheStore for the dota id', () => {
  useUserCacheStore.getState().upsert({
    pk: 5, username: 'x',
    positions: { carry: 5, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
  } as any);
  const pos = selectPositions(useUserCacheStore.getState(), 5, GAME_TYPE.DOTA2);
  expect(pos?.carry).toBe(5);
});

it('selectPositions returns undefined for null/non-dota gameType', () => {
  expect(selectPositions(useUserCacheStore.getState(), 5, null)).toBeUndefined();
});
```

- [ ] **Step 2: Run, verify it fails** — `cd frontend && npx vitest run app/store/userCacheStore.test.ts` → FAIL (`selectPositions` not found).

- [ ] **Step 3: Expand the edit-layer types** (`userProfileTypes.ts`) — these are the modal's layered shape (still needed for the GET + Dota tab edit form):

```typescript
export interface PositionsValue {
  carry: number; mid: number; offlane: number;
  soft_support: number; hard_support: number;
}
export interface DotaUserProfile {
  positions?: PositionsValue | null;
  has_active_dota_mmr?: boolean;
  dota_mmr_last_verified?: string | null;
}
export interface DeadlockUserProfile {
  rank?: string | null;
  rank_date?: string | null;
}
```

- [ ] **Step 4a: Export the store state type.** `userCacheStore.ts:118` declares `interface UserCacheState extends EntityState<UserEntry>` with NO `export` — add `export` so `selectPositions.ts` can import it (else Task 10 won't compile). Confirmed missing in the live file.

- [ ] **Step 4b: Add `selectPositions` reading `userCacheStore`** (`frontend/app/store/selectPositions.ts`):

```typescript
import type { UserCacheState } from './userCacheStore';      // now exported (Step 4a)
import type { PositionsType } from './userCacheTypes';        // the store's positions type
import { GAME_TYPE } from '~/components/game/constants';
import type { GameTypeValue } from '~/components/game/constants';

/**
 * Read a user's positions from the list-populated, rendered-once flat
 * `_users[]` entity adapter (userCacheStore). gameType-gated so future games
 * resolve their own layer. orgUserId is a T3 parameter (org overrides) — pass
 * undefined in T2. Returns the stored reference (or undefined) — stable for
 * Zustand Object.is, no per-call allocation.
 */
export function selectPositions(
  state: UserCacheState,
  userPk: number,
  gameType: GameTypeValue | null,
  _orgUserId?: number,   // T3 only
): PositionsType | undefined {
  if (gameType !== GAME_TYPE.DOTA2) return undefined;
  return state.entities[userPk]?.positions ?? undefined;
}
```

Return type is `PositionsType` (what the store actually holds, `userCacheTypes.ts:22`), not the edit-layer `PositionsValue` — structurally compatible but annotate to the real type. `state.entities[userPk]` matches the live `createEntityAdapter` shape (entities keyed by pk).

- [ ] **Step 5: Run, verify pass, commit**

```bash
cd frontend && npx vitest run app/store/userCacheStore.test.ts
git add frontend/app/store/userProfileTypes.ts frontend/app/store/selectPositions.ts frontend/app/store/userCacheStore.test.ts
git commit -m "feat(user): selectPositions over list-populated userCacheStore + edit-layer types (T2.10, epic #224)"
```

---

## Task 11: `usePlayerPositions` hook (subscribes to `userCacheStore`)

**Files:**
- Create: `frontend/app/hooks/usePlayerPositions.ts`
- Test: `frontend/app/hooks/__tests__/usePlayerPositions.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/app/hooks/__tests__/usePlayerPositions.test.tsx
import { renderHook } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { usePlayerPositions } from '../usePlayerPositions';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useGameTypeStore } from '~/store/gameTypeStore';
import { GAME_TYPE } from '~/components/game/constants';

describe('usePlayerPositions', () => {
  beforeEach(() => { useUserCacheStore.getState().reset?.(); });

  it('returns dota positions when active game is dota, from the list-populated cache', () => {
    useUserCacheStore.getState().upsert({
      pk: 9, username: 'p',
      positions: { carry: 4, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    } as any);
    useGameTypeStore.setState({ currentGameType: GAME_TYPE.DOTA2 });
    const { result } = renderHook(() => usePlayerPositions(9));
    expect(result.current?.carry).toBe(4);
  });

  it('returns undefined when no active game', () => {
    useGameTypeStore.setState({ currentGameType: null });
    const { result } = renderHook(() => usePlayerPositions(9));
    expect(result.current).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run, verify it fails** — `cd frontend && npx vitest run app/hooks/__tests__/usePlayerPositions.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Implement the hook (over `userCacheStore`)**

```typescript
// frontend/app/hooks/usePlayerPositions.ts
import { useGameType } from '~/hooks/useGameType';
import { useUserCacheStore } from '~/store/userCacheStore';
import { selectPositions } from '~/store/selectPositions';
import type { PositionsValue } from '~/store/userProfileTypes';

/**
 * Reactive positions read for DISPLAY surfaces, off the list-populated flat
 * `_users[]` entity adapter (userCacheStore). Returns undefined when no active
 * game — never silently defaults to Dota. The Dota EDIT tab does NOT use this;
 * it reads positions off the modal's layered `profile.gameUser.dota.positions`.
 * Cannot be called inside `.map()` row callbacks (Rules of Hooks) — for per-row
 * reads in a list, call `selectPositions(useUserCacheStore.getState(), pk, gt)`
 * ONCE at the component top with a single store subscription, or subscribe the
 * whole row list. orgUserId is T3.
 */
export function usePlayerPositions(userPk: number): PositionsValue | undefined {
  const gameType = useGameType();
  return useUserCacheStore((s) => selectPositions(s, userPk, gameType));
}
```

- [ ] **Step 4: Run, verify pass, commit**

```bash
cd frontend && npx vitest run app/hooks/__tests__/usePlayerPositions.test.tsx
git add frontend/app/hooks/usePlayerPositions.ts frontend/app/hooks/__tests__/usePlayerPositions.test.tsx
git commit -m "feat(user): usePlayerPositions hook over list-populated userCacheStore (T2.11, epic #224)"
```

---

## Task 12: API client `patchGameProfile`

**Files:**
- Modify: `frontend/app/components/api/userProfileApi.ts`

- [ ] **Step 1: Add the function**

```typescript
export type DotaPatchPayload = {
  positions?: PositionsValue | null;
  has_active_dota_mmr?: boolean;
};
export type DeadlockPatchPayload = { rank?: string | null; rank_date?: string | null };

// OVERLOADS — without them the union return makes `updated.positions` a TS2339
// in DotaTab.onSuccess (DeadlockUserProfile has no `positions`). The overloads
// narrow the return per game so each tab's onSuccess is typed.
export async function patchGameProfile(
  game: 'dota', patch: DotaPatchPayload,
): Promise<DotaUserProfile>;
export async function patchGameProfile(
  game: 'deadlock', patch: DeadlockPatchPayload,
): Promise<DeadlockUserProfile>;
export async function patchGameProfile(
  game: 'dota' | 'deadlock',
  patch: DotaPatchPayload | DeadlockPatchPayload,
): Promise<DotaUserProfile | DeadlockUserProfile> {
  const res = await api.patch(`/users/me/profile/game/${game}/`, patch);
  return res.data;
}
```

Use the same `api` axios client + error handling that `patchBaseProfile` uses (read the existing function and mirror it exactly — auth, base URL, error shape). Import `PositionsValue`, `DotaUserProfile`, `DeadlockUserProfile` from `~/store/userProfileTypes`.

- [ ] **Step 2: Typecheck + commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep userProfileApi || echo "clean"
git add frontend/app/components/api/userProfileApi.ts
git commit -m "feat(user): patchGameProfile API client (T2.12, epic #224)"
```

---

## Task 13: Dota tab

**Files:**
- Create: `frontend/app/pages/user/EditProfileModal/tabs/DotaTab.tsx`
- Modify: `frontend/app/pages/user/EditProfileModal/schemas.ts`
- Test: covered by Playwright (Task 17) + manual

**Template:** `frontend/app/pages/user/EditProfileModal/tabs/BaseTab.tsx` is the exact pattern — shadcn `Form` + `zodResolver` + `useForm` + `useMutation` + `getLogger('user.editProfile.dota')`. Read BaseTab.tsx end to end and mirror its structure.

**Reuse the existing branded position picker — do NOT hand-roll number inputs.** Use **`PositionFormFields`** from `frontend/app/pages/profile/forms/position.tsx` — it's the **exported, purpose-built reusable** primitive (already consumed by EventSignupModal + the profile page), renders 5 branded role `<Select>`s bound to `name="positions.carry"` etc. with `position-choice-{role}` testids. (The other candidate, `PositionSelect` in `userCard/editForm.tsx`, has the `edit-user-{position}` testids + existing Playwright helpers BUT is **not exported** — re-review confirmed — so it can't be imported; don't use it.) Reusing `PositionFormFields` means: (a) the schema must be NESTED (`{ positions: {...} }`) to match `name="positions.*"`, (b) you get the semantic 0–5 preference labels (UX parity), (c) testids are `position-choice-{role}` — Task 17 drives those directly (the `setPositionField`/`readPositionField` helpers are keyed to `edit-user-*`, so they won't match `PositionFormFields`; the Dota spec interacts with `position-choice-*` selects directly, or you add a small helper). The component prop is **`form`** (pass `form={form}`), NOT `control`.

- [ ] **Step 1: Add the NESTED Dota schema to `schemas.ts`** (mirror `editUserSchema.ts`'s `PositionFieldSchema`)

```typescript
export const PositionFieldSchema = z.coerce.number().int().min(0).max(5);
export const DotaProfileFormSchema = z.object({
  positions: z.object({
    carry: PositionFieldSchema,
    mid: PositionFieldSchema,
    offlane: PositionFieldSchema,
    soft_support: PositionFieldSchema,
    hard_support: PositionFieldSchema,
  }),
});
export type DotaProfileFormValues = z.infer<typeof DotaProfileFormSchema>;
```
If `editUserSchema.ts` already exports a `PositionFieldSchema`/positions sub-schema, import and reuse it (DRY) rather than redefining.

- [ ] **Step 2: Implement `DotaTab.tsx`**

Mirror BaseTab. Key deltas:
- `useForm<z.input<typeof DotaProfileFormSchema>, unknown, DotaProfileFormValues>({ resolver: zodResolver(DotaProfileFormSchema), defaultValues })` — **3-generic** because of `z.coerce` (lesson #12). `defaultValues = { positions: { carry: profile.gameUser.dota?.positions?.carry ?? 0, ... } }`.
- Render the reused `<PositionFormFields form={form} />` (prop is `form`, not `control`) — NOT raw `<Input type=number>`.
- `mutationFn: (vals) => patchGameProfile('dota', vals)` — `vals` is already `{ positions: {...} }`, so pass it directly (NOT `{ positions: vals }`).
- **`onSuccess` DUAL-WRITE** (the load-bearing multi-write — display surfaces read `userCacheStore`, edit layer reads `userProfileStore`; `onClose()` unmounts before any refetch so both manual writes are required):
  ```ts
  // 1. list/display source — every roster/card/table reading selectPositions updates now
  const cached = useUserCacheStore.getState().getById?.(profile.pk);
  if (cached) {
    useUserCacheStore.getState().upsert({ ...cached, pk: profile.pk, positions: updated.positions });
  }
  // 2. edit layer — base on the `profile` prop (always full), NOT a getState() lookup that can be undefined
  useUserProfileStore.getState().upsert({
    ...profile,
    gameUser: { ...profile.gameUser, dota: { ...profile.gameUser?.dota, positions: updated.positions } },
    _fetchedAt: Date.now(),
  });
  // 3. refetch-on-next-mount
  queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });
  toast.success('Dota profile updated');
  onSave?.(); onClose();
  ```
  Read `userCacheStore.ts` for the exact upsert/getById API (it requires a `UserType` with `username` — spread the existing cached entry as BaseTab does; if no cached entry exists, skip the cache write — the invalidate covers it).
- `data-testid="edit-user-dota-save"` on submit. Position inputs come from `PositionFormFields` and carry its existing `position-choice-{role}` testids — do NOT invent new ones.
- Brand: `CancelButton`/`SubmitButton`, `flex flex-col gap-4`, no raw button, no `space-y-*`. **`export default`** (lazy import needs it). Do NOT add `form.watch` (no live preview here — would re-render per keystroke for nothing).

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "DotaTab|schemas" || echo clean`

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/user/EditProfileModal/tabs/DotaTab.tsx frontend/app/pages/user/EditProfileModal/schemas.ts
git commit -m "feat(user): DotaTab positions editor (T2.13, epic #224)"
```

---

## Task 14: Deadlock tab

**Files:**
- Create: `frontend/app/pages/user/EditProfileModal/tabs/DeadlockTab.tsx`
- Modify: `frontend/app/pages/user/EditProfileModal/schemas.ts`

- [ ] **Step 1: Add the Deadlock schema**

```typescript
export const DeadlockProfileFormSchema = z.object({
  rank: z.string().max(64).nullable().optional(),
  rank_date: z.string().nullable().optional(),
});
export type DeadlockProfileFormValues = z.infer<typeof DeadlockProfileFormSchema>;
```

- [ ] **Step 2: Implement `DeadlockTab.tsx`**

Mirror BaseTab (single text field for `rank`, optional date for `rank_date`). `getLogger('user.editProfile.deadlock')`. `mutationFn: (vals) => patchGameProfile('deadlock', vals)`. `onSuccess` upserts `gameUser.deadlock` into `userProfileStore` based on the **`profile` prop** (not a `getState()` lookup): `useUserProfileStore.getState().upsert({ ...profile, gameUser: { ...profile.gameUser, deadlock: { ...profile.gameUser?.deadlock, ...updated } }, _fetchedAt: Date.now() })` + `invalidateQueries(['userProfile', profile.pk])`. No `userCacheStore` write needed (deadlock rank is not a flat `_users[]` list-display field). `data-testid="edit-user-deadlock-rank"`, `data-testid="edit-user-deadlock-save"`. 3-generic `useForm` for consistency (harmless without coerce). **`export default`** (lazy import). No `form.watch`.

- [ ] **Step 3: Typecheck + commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "DeadlockTab|schemas" || echo clean
git add frontend/app/pages/user/EditProfileModal/tabs/DeadlockTab.tsx frontend/app/pages/user/EditProfileModal/schemas.ts
git commit -m "feat(user): DeadlockTab rank editor (T2.14, epic #224)"
```

---

## Task 15: Wire Dota + Deadlock tabs into EditProfileModal

**Files:**
- Modify: `frontend/app/pages/user/EditProfileModal.tsx`

- [ ] **Step 1: Lazy-import + add tabs**

Add `const DotaTab = lazy(() => import('./EditProfileModal/tabs/DotaTab'));` and same for Deadlock. Replace the `{/* T2 adds */}` placeholder:

```tsx
<TabsTrigger value="dota" data-testid="edit-user-tab-dota">Dota</TabsTrigger>
<TabsTrigger value="deadlock" data-testid="edit-user-tab-deadlock">Deadlock</TabsTrigger>
```

Add two `<TabsContent>` blocks mirroring the Base one, each wrapping its lazy tab in `<Suspense fallback={<ProfileSkeleton />}>`, passing `profile={data} onSave={onSave} onClose={onClose}`.

**Query-key sanity:** the modal's `useSuspenseQuery` is keyed `['userProfile', userPk]` while the tabs invalidate `['userProfile', profile.pk]`. These match only because `getUserProfile` ignores its arg (hits `/me/`) and the modal mounts only for the self user (`isOwnProfile`, `userPk={user.pk}`). Add a dev-time assertion in `EditProfileModalBody` — `if (import.meta.env.DEV && data.pk !== userPk) console.warn('userProfile key/pk mismatch', {userPk, dataPk: data.pk})` — so a future non-self mount surfaces the latent invalidate-miss instead of silently failing.

- [ ] **Step 2: Typecheck + commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep EditProfileModal || echo clean
git add frontend/app/pages/user/EditProfileModal.tsx
git commit -m "feat(user): wire Dota + Deadlock tabs into EditProfileModal (T2.15, epic #224)"
```

---

## Task 16: Route user-scoped positions reads through the gameType-aware selector

> **Revised approach (architecture decision above).** The 11 consumers already read positions from the list-populated `userCacheStore.UserEntry.positions` (directly or via `currentUser`/props). The migration is NOT "move to a different store" — the data stays on the flat `_users[]` entity (`UserEntry.positions`). It's "route reads through the gameType-aware `selectPositions`/`usePlayerPositions`" so positions resolve per active game (Dota today) and stay forward-compatible with T3 org overrides. **`UserEntry.positions` is NOT deprecated** — it's the rendered-once flat field the selector reads.
>
> **Rules-of-Hooks + reactivity (the trap the review caught):** `usePlayerPositions` is a hook — it CANNOT be called inside a `.map()` row callback, and `selectPositions(useUserCacheStore.getState(), …)` is a NON-reactive snapshot (won't re-render on change). For per-row list reads, subscribe ONCE at the component top to the rows you need (e.g. `useUserCacheStore(s => members.map(m => selectPositions(s, m.pk, gameType)))` with `useShallow`) so the component re-renders reactively, then index per row — do NOT sprinkle `getState()` in render. Genuinely non-reactive call sites (pure form-default builders, event handlers) may use `getState()`.

**Per-consumer classification (verify each against the file before editing):**

| File | Context | How to migrate |
|---|---|---|
| `user/positions/index.tsx` | single-user badge component (render path) | `usePlayerPositions(user.pk)` (reactive hook) |
| `user/userCard.tsx` | single-user card (render path) | `usePlayerPositions(user.pk)` |
| `user/UserStrip.tsx` | single-user strip (render path, useMemo dep) | `usePlayerPositions(user.pk)` then feed the memo |
| `teamdraft/TeamPositionCoverage.tsx` | reads `member.positions` (lines 73,128) inside the PURE fn `computeTeamPositionCoverage`, called via `useMemo` (line ~551) — no JSX `.map` to subscribe at | In `TeamPositionCoverageRow`, build `positionsByPk = useUserCacheStore(useShallow(s => new Map(members.map(m => [m.pk, selectPositions(s, m.pk, gt)]))))`, thread it into `computeTeamPositionCoverage(team, positionsByPk)`, replace the two `member.positions` reads with `positionsByPk.get(member.pk)`. (Genuine data-source switch, not a re-route.) |
| `teamdraft/sections/AvailablePlayersSection.tsx` | reads `user.positions` (line ~197) inside `filteredPlayers` useMemo over the DRAFT store `usersRemaining` (not the cache) | Subscribe a `positionsByPk` map at component top via `useUserCacheStore(useShallow(...))`, add it to the useMemo deps, look up by pk. (Also a data-source switch.) |
| `pages/tournament/hasErrors.tsx` | derivation inside a hook over entities | subscribe via the store hook (reactive), not getState |
| `user/userCard/editUserSchema.ts` | pure form-default builder (non-reactive) | `selectPositions(getState(), pk, DOTA2)` OK |
| `pages/profile/profile.tsx` | form seed from `currentUser` (reactive store) | read positions for the current user via the selector; keep write path |
| `EventSignupModal/schema.ts` | form schema/default builder | `getState()` snapshot OK (form init) |
| `EventSignupModal/toPatch.ts` | patch-diff builder (non-reactive) | `getState()` snapshot OK |
| `EventSignupModal.tsx` | form seed (reactive) | selector at component top |

For form defaults/patch that read AND write positions, **only the READ migrates** — keep the existing write path (backend `UserSerializer`/EventSignup shim still accepts `positions`). Migrate one file per step; `cd frontend && npx tsc --noEmit 2>&1 | grep <file> || echo clean` after each.

- [ ] **Step 1: Migrate render-path single-user readers** — `user/positions/index.tsx`, `user/userCard.tsx`, `user/UserStrip.tsx` via `usePlayerPositions(user.pk)`.

- [ ] **Step 2: Migrate render-path per-row `.map` readers** — `teamdraft/TeamPositionCoverage.tsx`, `teamdraft/sections/AvailablePlayersSection.tsx`, `pages/tournament/hasErrors.tsx` via the `positionsByPk`-map-at-top pattern (NEVER `getState()` in a render-path `.map`).

  **CRITICAL gameType-gate check (do this FIRST, before migrating teamdraft):** `selectPositions` returns `undefined` unless `currentGameType === GAME_TYPE.DOTA2`. Today teamdraft/coverage/available-players ALWAYS show positions regardless of active game. Verify `currentGameType` is actually set to DOTA2 when these routes mount — `rg -n "setCurrentGameType|currentGameType" frontend/app/pages/tournament frontend/app/components/teamdraft frontend/app/routes`. If teamdraft/tournament routes do NOT set `currentGameType=DOTA2`, the gate makes positions vanish there — a regression. If unset, either (a) pass an explicit `GAME_TYPE.DOTA2` to `selectPositions` at these Dota-only teamdraft sites instead of the ambient gameType (these surfaces are inherently Dota), OR (b) ensure the route sets `currentGameType`. Prefer (a) for teamdraft (it's Dota-specific). Confirm the chosen approach renders positions before moving on.

- [ ] **Step 3: Migrate form readers (non-reactive `getState()` acceptable)** — `user/userCard/editUserSchema.ts`, `pages/profile/profile.tsx`, `EventSignupModal/schema.ts`, `EventSignupModal/toPatch.ts`, `EventSignupModal.tsx`.

- [ ] **Step 4: Do NOT deprecate `UserEntry.positions`** — it is the flat `_users[]` field the selector reads. Add a one-line comment in `userCacheTypes.ts`: `/** Flat rendered-once positions; read via selectPositions/usePlayerPositions for gameType-awareness. */`. Then confirm no remaining RAW `user.positions` reads outside the leave-alone set: `rg "\.positions" frontend/app --include="*.ts" --include="*.tsx"` — every hit must be (a) the leave-alone set [`EventSignupModal/evaluateSignupGap.ts`, `events/games/dota2/Dota2RankSignalsCard.tsx`, `CSVImportModal.tsx`, `csvParser.ts`, `UserEventStrip.tsx`], (b) inside `selectPositions`/the picker primitive, or (c) a `PositionsValue`/form-local read.

- [ ] **Step 5: Full typecheck + vitest**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -v node_modules | grep "error TS" | head; npx vitest run`
Expected: no NEW tsc errors vs main baseline; all vitest pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/app
git commit -m "refactor(user): route positions reads through gameType-aware selectPositions (T2.16, epic #224)"
```

---

## Task 17: Playwright spec + cacheops integration test (shipped skipped)

**Files:**
- Create: `frontend/tests/playwright/e2e/15-edit-user/11-dota-tab-positions.spec.ts` (NEW file — `08-position-persistence.spec.ts` ALREADY EXISTS and guards the legacy userCard `/users/<id>/` shim path; do NOT overwrite it — it's now a valuable Task-9 shim regression test)
- Create: `backend/user/tests/test_game_cacheops_integration.py` (shipped `@unittest.skip`, lesson #24)

- [ ] **Step 1: Playwright — Dota positions persist + reflect**

Mirror `06-profile-edit.spec.ts`. **Log in via the `n` fixture: `await n(2057)`** (`edit_user_positions`, `backend/tests/data/users.py:545`; the per-user login fixture is `n(userPk)` in `fixtures/auth.ts` — there is NO `loginAsUser`; `loginAdmin` is admin-only and wrong here since the `/profile` Dota tab edits the logged-in user). Capture the original positions first. Open `/profile` → EditProfileModal → Dota tab; set a position by driving the `PositionFormFields` `position-choice-{role}` `<Select>` directly (the `setPositionField`/`readPositionField` helpers are keyed to `edit-user-*` and won't match `PositionFormFields` — interact with the `position-choice-*` testids, or add a small helper); save; assert toast.

**Reflect-assertion caveat:** `/profile` has no active game, so `currentGameType === null` and any `usePlayerPositions` display there returns `undefined`. Assert the persisted change by **re-opening the modal** and reading the field back (as existing `08` does), NOT by expecting a profile-page badge to update. Restore the original in `finally`. Add an error-path test (`page.route` 500 on `**/api/users/me/profile/game/dota/`, assert error toast + modal stays open + `page.unroute`).

- [ ] **Step 2: Cacheops integration test (skipped)**

Mirror `test_cacheops_integration.py`: `TransactionTestCase` (lesson: on_commit), `_redis_reachable()` skip-guard, AND a top-level `@unittest.skip("inherits T1 keep_fresh/eviction deferral — lesson #24")`. Warms a cached user-list endpoint, PATCHes `/me/profile/game/dota/`, asserts new positions. Shipped skipped — the grep guardrail (Task 3) is the live gate.

- [ ] **Step 3: Run targeted**

Run: `just test::pw::spec 15-edit-user` and `just test::run 'python manage.py test user.tests.test_game_cacheops_integration -v 2'` (latter all-skipped).

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/15-edit-user/11-dota-tab-positions.spec.ts backend/user/tests/test_game_cacheops_integration.py
git commit -m "test(user): Dota tab Playwright spec + skipped cacheops integration (T2.17, epic #224)"
```

---

## Final verification (after all tasks)

- [ ] `just test::run 'python manage.py test app user events -v 2'` — full backend green (positions shim keeps app + events suites passing).
- [ ] `cd frontend && npx vitest run` — all vitest green.
- [ ] `cd frontend && npx tsc --noEmit` — no new errors vs main baseline.
- [ ] `just test::pw::spec 15-edit-user` — edit-user E2E green.
- [ ] Grep guardrails: `rg "@cached_as\(.*CustomUser" backend/app backend/user | rg -v "DotaUserProfile"` → zero lines. `rg "related_name=" backend/user/models.py` → no `related_name` on the `positions` FK.
- [ ] `rg "\.positions" frontend/app --include="*.ts" --include="*.tsx"` → every hit is leave-alone-set, inside `selectPositions`/the picker primitive, or a `PositionsValue`/form-local read.
- [ ] Migration safety: `just db::migrate::all` on a populated DB → no errors; `app/0096` runs after `user/0004`.
- [ ] **Populate smoke** (lesson: T1 had this; the positions shim must not break populate): `just db::populate::all` → completes; spot-check a populated user has `user.base_profile.dota_user_profile.positions` set. Confirms `objects.create(positions=…)` + the `user.positions = …` setter still flow through the shim.
- [ ] **Brand grep gate** for the new tabs: `rg "from '~/components/ui/button'" frontend/app/pages/user/EditProfileModal/tabs/DotaTab.tsx frontend/app/pages/user/EditProfileModal/tabs/DeadlockTab.tsx` → zero (use CancelButton/SubmitButton); `rg "space-y-|<button" frontend/app/pages/user/EditProfileModal/tabs/` → zero.
- [ ] Demo recording if any of `frontend/app/components/herodraft|draft|bracket` changed (none expected in T2 — skip).

---

## Spec

`docs/plans/2026-05-17-user-profile-entity-adapter-epic-design.md` §T2 + "Patterns from T1" (24 lessons).

**Justified divergences from §T2 (found in plan review):**
- **Positions read source.** §T2 said consumers migrate to `usePlayerPositions` over `userProfileStore` and `UserEntry.positions` is deprecated. That's infeasible — `userProfileStore` is modal-scoped, not list-populated. Revised: `selectPositions`/`usePlayerPositions` read the rendered-once flat `_users[]` entity adapter (`userCacheStore`); `UserEntry.positions` stays. (See "Architecture decision" above.)
- **`positions_invalidated` log dropped.** §T2 acceptance lists it; it duplicates `invalidate_after_commit`'s built-in `cache_invalidate` log and uses a non-taxonomy subsystem. Omitted (matches T1, which added no bespoke cache log).
- **Legacy `profile_update`/UpdateProfile positions path** is kept working via the shim (covered-by-shim), not removed — same approach T1 took for nickname/avatar. Retirement deferred to cleanup.

## Follow-ups (deferred, real)

- **T3:** OrgUserProfile + OrgDotaUserProfile/OrgDeadlockUserProfile (rename PlayerDotaProfile/PlayerDeadlockProfile, rewire FKs to OrgUserProfile), per-org tabs, `useRouteOrgUserId()` route helper, `orgUserId` selector arg wired through `selectPositions` (org override → user-wide → undefined), `PositionsModel.save()` gains the `orgdotauserprofile_set` branch.
- **Cleanup:** remove `CustomUser.positions`/`has_active_dota_mmr`/`dota_mmr_last_verified` transitional shims; retire the legacy `profile_update` positions path; re-enable the live-Redis cacheops behavioral tests once T1's keep_fresh/eviction root cause is fixed (lesson #24). (`UserEntry.positions` is NOT removed — it's the flat `_users[]` field the selector reads.)
