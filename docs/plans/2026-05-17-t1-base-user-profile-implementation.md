# T1 — BaseUserProfile End-to-End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the BaseUserProfile layer end-to-end — extend the existing `user` Django app (created in commit `1ceeb9f9`) with the `BaseUserProfile` model, data migration moving `nickname`/`avatar` off `CustomUser`, transitional setter properties on `CustomUser` so populate fixtures keep working unchanged, layered profile API endpoints with structlog logging, frontend `userProfileEntityAdapter` scaffold, and a new tabbed Edit Profile modal whose Base tab edits the new fields via shadcn Form + Zod + `useMutation` + `<ErrorBoundary>`/`<Suspense>` + `useSuspenseQuery`.

**Architecture:** Vertical slice per spec `2026-05-17-user-profile-entity-adapter-epic-design.md` §T1. The existing `backend/user/` Django app gains `BaseUserProfile` (OneToOne FK → `app.CustomUser`). Data migration creates one row per existing user, copies `nickname`+`avatar`, drops the columns from `CustomUser`. `CustomUser.nickname` / `.avatar` become transitional read/write proxy properties so populate helpers and any incidental writers keep working. Frontend grows `userProfileStore.ts` mirroring `userCacheStore.ts`. New `EditProfileModal.tsx` + sibling `EditProfileModal/` directory uses `<ErrorBoundary>` → `<Suspense>` → `useSuspenseQuery` to fetch; PATCH uses `useMutation` with `onSuccess` dual-write to `userAdapter` + `queryClient.invalidateQueries`. Old `EditProfileModal.tsx` content replaced atomically.

**Pre-existing state (from commit `1ceeb9f9`, assumed merged to the T1 branch base):**
- `backend/user/` exists with `apps.py` (`UserConfig`), `__init__.py`, `internal/avatar.py` (avatar-related internal views moved from `backend/app/views/internal.py`), and `migrations/`.
- `user.apps.UserConfig` is already in `INSTALLED_APPS` (`backend/backend/settings.py`).
- `backend/tasks.py` `db_makemigrations` already includes `"user"` in its app tuple.
- T1 extends this: adds `models.py`, `admin.py`, `serializers.py`, `views.py` (new file separate from `user/internal/avatar.py`), `urls.py`, `migrations/`, `tests/`. Task 1 validates the baseline and wires what's missing rather than scaffolding from scratch.

**Tech Stack:** Django 5 + DRF + django-cacheops + structlog on the backend; React 19 + Vite + Zustand + TanStack Query 5.90 + shadcn Form + react-hook-form + Zod + sonner on the frontend; Playwright for E2E; Vitest for FE unit tests.

**Spec reference:** `docs/plans/2026-05-17-user-profile-entity-adapter-epic-design.md`

---

## File structure

### Backend — new files

- `backend/user/__init__.py`
- `backend/user/apps.py` — `UsersConfig`
- `backend/user/models.py` — `BaseUserProfile`
- `backend/user/admin.py` — `BaseUserProfileAdmin`
- `backend/user/serializers.py` — `BaseUserProfileSerializer`, `UserProfileLayeredSerializer`
- `backend/user/views.py` — `MeProfileView`, `MeProfileBasePatchView`
- `backend/user/urls.py` — `/api/users/me/profile/*` URL conf
- `backend/user/migrations/0001_initial.py` — auto-generated
- `backend/user/migrations/0002_backfill_base_profiles.py` — data migration (RunPython)
- `backend/user/tests/__init__.py`
- `backend/user/tests/test_app_registration.py`
- `backend/user/tests/test_models.py`
- `backend/user/tests/test_auto_create.py`
- `backend/user/tests/test_migration.py`
- `backend/user/tests/test_transitional_setters.py`
- `backend/user/tests/test_serializers.py`
- `backend/user/tests/test_views.py`
- `backend/user/tests/test_cacheops.py`

### Backend — modified files

- `backend/backend/settings.py` — `INSTALLED_APPS` += `user.apps.UserConfig`; `CACHEOPS` += `user.baseuserprofile`.
- `backend/backend/urls.py` — `path("api/users/", include("user.urls"))`.
- `backend/app/models.py:92-140` (`CustomUser`): drop `nickname` + `avatar` field declarations; add transitional `nickname`/`avatar` `@property` (getter + setter both proxy to `base_profile`, setter calls `invalidate_after_commit`); extend `save()` to auto-create `BaseUserProfile`.
- `backend/app/migrations/00XX_drop_user_nickname_avatar.py` — depends on `user.0002`; removes the columns.
- `backend/app/views_main.py` — every `@cached_as(...)` site that ships `nickname`/`avatar` gains a `BaseUserProfile` dep.
- `backend/app/functions/tournament.py:456` — same `@cached_as` update.
- `backend/app/serializers.py` — every user-identity serializer sources `nickname`/`avatar` from `base_profile`.
- `pyproject.toml` — `[tool.poetry.group.dev.dependencies]` += `django-test-migrations`.

### Frontend — new files

- `frontend/app/store/userProfileTypes.ts` — `UserProfileEntry`, `BaseProfile`, related types.
- `frontend/app/store/userProfileStore.ts` — Zustand store + adapter instance.
- `frontend/app/store/userProfileStore.test.ts` — Vitest unit tests.
- `frontend/app/components/api/userProfileApi.ts` — `getUserProfile(userPk)`, `patchBaseProfile(patch)`.
- `frontend/app/pages/user/EditProfileModal/schemas.ts` — Zod schemas.
- `frontend/app/pages/user/EditProfileModal/ProfileSkeleton.tsx` — Suspense fallback.
- `frontend/app/pages/user/EditProfileModal/ProfileErrorFallback.tsx` — ErrorBoundary fallback.
- `frontend/app/pages/user/EditProfileModal/tabs/BaseTab.tsx` — Base tab form.

### Frontend — modified files

- `frontend/app/pages/user/EditProfileModal.tsx` — REWRITTEN ATOMICALLY (same path; no `V2` suffix).
- `frontend/app/routes/editProfile.tsx` — mount new modal API (`userPk` prop).
- `frontend/app/pages/user/UserProfilePage.tsx:20,181` — pass `userPk` to the new modal.
- `frontend/app/store/userStore.ts` (or logout handler location) — wire `useUserProfileStore.getState().reset()` to logout.

### Playwright — modified files

- `frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts` — REWRITTEN to drive the new tabbed modal.

---

## Task 1 — Validate `user` Django app baseline + wire profile URL routes

The `user` app already exists from commit `1ceeb9f9` (registered in `INSTALLED_APPS` as `user.apps.UserConfig`, with `backend/user/internal/avatar.py`). T1 extends it. This task validates the baseline, fills in any missing stub files for downstream tasks, and wires the profile URL include (which is NOT yet present — `1ceeb9f9` only wired the avatar internal endpoints separately).

**Files:**
- Verify / create as missing: `backend/user/__init__.py`, `backend/user/apps.py`, `backend/user/models.py`, `backend/user/admin.py`, `backend/user/views.py`, `backend/user/urls.py`, `backend/user/tests/__init__.py`
- Create: `backend/user/tests/test_app_registration.py`
- Modify: `backend/backend/urls.py` (add the profile URL include)

- [ ] **Step 1: Verify the baseline**

```bash
ls -la backend/user/
cat backend/user/apps.py 2>/dev/null || echo "apps.py MISSING — Step 3 recreates"
cat backend/user/__init__.py 2>/dev/null || echo "__init__.py MISSING — Step 3 recreates"
grep -n "user.apps.UserConfig" backend/backend/settings.py
grep -n 'include("user.urls")' backend/backend/urls.py || echo "URL include NOT yet wired — Step 5 adds it"
```

Expected:
- `backend/user/` directory exists.
- `apps.py` exists with `class UserConfig(AppConfig)` and `name = "user"`. (If missing, Step 3 creates it.)
- `user.apps.UserConfig` already in `INSTALLED_APPS` (one match).
- `include("user.urls")` likely NOT yet wired (zero matches) — Step 5 adds it.

- [ ] **Step 2: Write the baseline test**

Create `backend/user/tests/__init__.py` (empty) if it doesn't exist.

Create `backend/user/tests/test_app_registration.py`:

```python
from django.apps import apps
from django.test import SimpleTestCase
from django.urls import resolve


class UserAppRegistrationTests(SimpleTestCase):
    def test_app_is_installed(self):
        assert apps.is_installed("user")

    def test_app_config_name(self):
        config = apps.get_app_config("user")
        assert config.name == "user"

    def test_placeholder_url_resolves(self):
        # Placeholder URL until Task 8 lands the real views.
        match = resolve("/api/users/me/profile/ping/")
        assert match.url_name == "me-profile-ping"
```

- [ ] **Step 3: Run test, expect partial failure**

```bash
just test::run 'python manage.py test user.tests.test_app_registration -v 2'
```

Expected: `test_app_is_installed` and `test_app_config_name` pass (app already registered by `1ceeb9f9`). `test_placeholder_url_resolves` fails with `Resolver404` — URL include not yet wired.

If `apps.py` or `__init__.py` were reported missing in Step 1, those tests fail too. Create them now:

`backend/user/__init__.py` (empty file).

`backend/user/apps.py`:
```python
from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "user"
    verbose_name = "User (profile layer)"
```

Skip this sub-step if both files exist.

- [ ] **Step 4: Create stub files for Tasks 2/7/8**

These let downstream tasks add real content without "module not found" surprises. Skip any file that already exists (do NOT overwrite existing content from `1ceeb9f9`).

`backend/user/models.py`:
```python
# BaseUserProfile lands in Task 2.
```

`backend/user/admin.py`:
```python
# Admin registration lands in Task 2.
```

`backend/user/views.py` (do NOT confuse with `backend/user/internal/avatar.py` — this file is for the public profile views from Task 8):
```python
from django.http import JsonResponse


def ping(request):
    """Placeholder to verify URL wiring. Replaced by MeProfileView in Task 8."""
    return JsonResponse({"ok": True})
```

`backend/user/urls.py` — if this file does NOT exist yet, create it:
```python
from django.urls import path

from .views import ping

urlpatterns = [
    path("me/profile/ping/", ping, name="me-profile-ping"),
]
```

If `backend/user/urls.py` already exists (e.g. wires the avatar internal endpoints), do NOT overwrite. Instead, APPEND the `path("me/profile/ping/", ...)` entry to the existing `urlpatterns` list and the corresponding `from .views import ping` import.

- [ ] **Step 5: Wire the URL include**

`backend/backend/urls.py` — add the include alongside other top-level `path(...)` entries:

```python
urlpatterns = [
    # ... existing ...
    path("api/users/", include("user.urls")),
]
```

Verify `include` is in the imports (`from django.urls import include, path`).

NOTE: the avatar internal endpoints from `1ceeb9f9` were wired separately at a different URL path; this include is for the public profile API.

- [ ] **Step 6: Run tests, expect pass**

```bash
just test::run 'python manage.py test user.tests.test_app_registration -v 2'
```

Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/user/ backend/backend/urls.py
git commit -m "feat(user): baseline test + wire profile URL include"
```

---

## Task 2 — `BaseUserProfile` model + admin + initial migration

**Files:**
- Modify: `backend/user/models.py`, `backend/user/admin.py`
- Create: `backend/user/migrations/0001_initial.py` (auto-generated), `backend/user/tests/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `backend/user/tests/test_models.py`:

```python
from django.db import IntegrityError
from django.test import TestCase

from app.models import CustomUser
from user.models import BaseUserProfile


class BaseUserProfileModelTests(TestCase):
    def test_create_profile_with_user(self):
        user = CustomUser.objects.create(username="alice")
        profile = BaseUserProfile.objects.create(
            user=user,
            nickname="Alice Wonderland",
            avatar="https://example.com/alice.png",
        )
        assert profile.user == user
        assert profile.nickname == "Alice Wonderland"
        assert profile.avatar == "https://example.com/alice.png"

    def test_one_to_one_constraint(self):
        # Auto-create from Task 3 makes the first BaseUserProfile; the second
        # explicit create must violate uniqueness.
        user = CustomUser.objects.create(username="bob")
        BaseUserProfile.objects.filter(user=user).delete()  # clear if auto-created
        BaseUserProfile.objects.create(user=user, nickname="Bob")
        with self.assertRaises(IntegrityError):
            BaseUserProfile.objects.create(user=user, nickname="Bob 2")

    def test_str_includes_username(self):
        user = CustomUser.objects.create(username="carol")
        profile = BaseUserProfile.objects.filter(user=user).first()
        # Tolerant of auto-create from Task 3
        if profile is None:
            profile = BaseUserProfile.objects.create(user=user, nickname="Carol")
        assert "carol" in str(profile)

    def test_reverse_accessor_named_base_profile(self):
        user = CustomUser.objects.create(username="dave")
        # Either created in setUp helper or by auto-create
        BaseUserProfile.objects.get_or_create(user=user)
        user.refresh_from_db()
        assert hasattr(user, "base_profile")
```

- [ ] **Step 2: Run tests, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_models -v 2'
```

Expected: `ImportError: cannot import name 'BaseUserProfile'`.

- [ ] **Step 3: Implement the model**

`backend/user/models.py`:
```python
from cacheops import invalidate_obj
from django.db import models


class BaseUserProfile(models.Model):
    """User-global, single-value profile data.

    Owns fields that are true for the user regardless of game or org —
    nickname, avatar, future display-only fields. Game-specific data
    lives on DotaUserProfile / DeadlockUserProfile (T2); org-scoped
    data lives on OrgUserProfile (T3).
    """

    user = models.OneToOneField(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="base_profile",
        db_index=True,
    )
    nickname = models.TextField(null=True, blank=True)
    avatar = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Base User Profile"

    def __str__(self):
        return f"BaseUserProfile({self.user.username or self.user_id})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_obj(self.user)
```

- [ ] **Step 4: Register the admin**

`backend/user/admin.py`:
```python
from django.contrib import admin

from .models import BaseUserProfile


@admin.register(BaseUserProfile)
class BaseUserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nickname", "avatar")
    search_fields = ("user__username", "nickname")
    raw_id_fields = ("user",)
```

- [ ] **Step 5: Generate the migration**

```bash
just db::makemigrations user
```

Verify `backend/user/migrations/0001_initial.py` is created.

- [ ] **Step 6: Run tests, expect pass**

```bash
just db::migrate::test
just test::run 'python manage.py test user.tests.test_models -v 2'
```

Expected: 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/user/models.py backend/user/admin.py backend/user/migrations/0001_initial.py backend/user/tests/test_models.py
git commit -m "feat(user): BaseUserProfile model + admin + initial migration"
```

---

## Task 3 — Auto-create `BaseUserProfile` on `CustomUser.save()`

**Files:**
- Modify: `backend/app/models.py:141-160` (`CustomUser.save()`)
- Create: `backend/user/tests/test_auto_create.py`

- [ ] **Step 1: Write failing tests**

Create `backend/user/tests/test_auto_create.py`:

```python
from django.test import TestCase

from app.models import CustomUser
from user.models import BaseUserProfile


class CustomUserAutoCreateTests(TestCase):
    def test_new_user_gets_base_profile(self):
        user = CustomUser.objects.create(username="eve")
        assert BaseUserProfile.objects.filter(user=user).exists()

    def test_idempotent_on_resave(self):
        user = CustomUser.objects.create(username="frank")
        original_pk = user.base_profile.pk
        user.save()
        user.refresh_from_db()
        assert user.base_profile.pk == original_pk
```

- [ ] **Step 2: Run test, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_auto_create -v 2'
```

Expected: `BaseUserProfile.DoesNotExist` or similar.

- [ ] **Step 3: Update `CustomUser.save()`**

`backend/app/models.py` — extend the existing `save()` (around line 141-160):

```python
def save(self, *args, **kwargs):
    """Keep steam_account_id (32-bit) and steamid (64-bit) in sync, and
    ensure every user has a BaseUserProfile after save.
    """
    if self.steam_account_id is not None:
        self.steamid = self.steam_account_id + self.STEAM_ID_64_BASE
    elif self.steamid is not None:
        self.steam_account_id = self.steamid - self.STEAM_ID_64_BASE

    super().save(*args, **kwargs)

    # Auto-create BaseUserProfile if missing. Idempotent via get_or_create.
    # Local import avoids the circular: user.models -> app.CustomUser.
    from user.models import BaseUserProfile
    BaseUserProfile.objects.get_or_create(user=self)
```

- [ ] **Step 4: Run tests, expect pass**

```bash
just test::run 'python manage.py test user.tests.test_auto_create -v 2'
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/user/tests/test_auto_create.py
git commit -m "feat(user): auto-create BaseUserProfile on CustomUser.save()"
```

---

## Task 4 — Data migration: copy `nickname`/`avatar` to `BaseUserProfile`

**Files:**
- Create: `backend/user/migrations/0002_backfill_base_profiles.py`, `backend/user/tests/test_migration.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `django-test-migrations` to poetry dev deps**

```bash
cd backend && poetry add --group dev django-test-migrations
```

Verify `pyproject.toml` shows the new dep under `[tool.poetry.group.dev.dependencies]`.

Rebuild the test container so the dep is available:

```bash
just test::setup
```

- [ ] **Step 2: Write failing migration test**

Create `backend/user/tests/test_migration.py`:

```python
from django_test_migrations.contrib.unittest_case import MigratorTestCase


class BackfillBaseProfilesMigrationTest(MigratorTestCase):
    migrate_from = ("users", "0001_initial")
    migrate_to = ("user", "0002_backfill_base_profiles")

    def prepare(self):
        # Bypass auto-create signal by using the historical model from old_state.
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        CustomUser.objects.create(
            username="alice",
            nickname="Alice Old",
            avatar="https://example.com/alice.png",
        )
        CustomUser.objects.create(username="bob", nickname=None, avatar=None)

    def test_each_user_gets_base_profile_with_copied_values(self):
        BaseUserProfile = self.new_state.apps.get_model("users", "BaseUserProfile")
        alice = BaseUserProfile.objects.get(user__username="alice")
        bob = BaseUserProfile.objects.get(user__username="bob")
        assert alice.nickname == "Alice Old"
        assert alice.avatar == "https://example.com/alice.png"
        assert bob.nickname is None
        assert bob.avatar is None
```

- [ ] **Step 3: Run test, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_migration -v 2'
```

Expected: migration `0002_backfill_base_profiles` does not exist.

- [ ] **Step 4: Look up the current latest `app` migration name**

```bash
ls backend/app/migrations/ | grep -v __pycache__ | sort | tail -3
```

Note the most recent migration filename (e.g. `0042_something.py`); use its base name (`0042_something`) in the dependency below.

- [ ] **Step 5: Create the migration**

`backend/user/migrations/0002_backfill_base_profiles.py`:

```python
from django.core.cache import cache
from django.db import migrations


def copy_nickname_avatar_to_base_profile(apps, schema_editor):
    """Backfill BaseUserProfile rows from CustomUser.nickname / .avatar.

    Disables cacheops during the bulk write to avoid mid-migration cache
    poisoning, then explicitly invalidates the affected models at end.
    """
    CustomUser = apps.get_model("app", "CustomUser")
    BaseUserProfile = apps.get_model("users", "BaseUserProfile")

    cache.clear()  # Clear any existing cacheops state

    to_create = []
    seen = set()
    for user in CustomUser.objects.all().iterator():
        if user.pk in seen:
            continue
        seen.add(user.pk)
        to_create.append(
            BaseUserProfile(
                user_id=user.pk,
                nickname=user.nickname,
                avatar=user.avatar,
            )
        )

    BaseUserProfile.objects.bulk_create(to_create, ignore_conflicts=True)

    # Bulk_create bypasses post_save signals, so invalidate models explicitly.
    # (At migration time these models may not be registered with cacheops yet —
    # invalidate_model is safe regardless.)
    try:
        from cacheops import invalidate_model
        invalidate_model(CustomUser)
        invalidate_model(BaseUserProfile)
    except ImportError:
        pass


def reverse_copy(apps, schema_editor):
    """Reverse: copy BaseUserProfile nickname/avatar back onto CustomUser.

    Only used in tests / rollback. Production reverses by re-adding the
    columns and re-running this reverse path; see migration 00XX in
    backend/app/migrations/.
    """
    CustomUser = apps.get_model("app", "CustomUser")
    BaseUserProfile = apps.get_model("users", "BaseUserProfile")

    for profile in BaseUserProfile.objects.all().iterator():
        CustomUser.objects.filter(pk=profile.user_id).update(
            nickname=profile.nickname,
            avatar=profile.avatar,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
        ("app", "REPLACE_WITH_LATEST_APP_MIGRATION_BASE_NAME"),
    ]

    operations = [
        migrations.RunPython(
            copy_nickname_avatar_to_base_profile,
            reverse_copy,
        ),
    ]
```

Replace `REPLACE_WITH_LATEST_APP_MIGRATION_BASE_NAME` with the value from Step 4 (e.g. `"0042_something"`).

- [ ] **Step 6: Run test, expect pass**

```bash
just test::run 'python manage.py test user.tests.test_migration -v 2'
```

Expected: 1 test passes.

- [ ] **Step 7: Run all `users` tests to confirm nothing regressed**

```bash
just test::run 'python manage.py test user -v 2'
```

- [ ] **Step 8: Commit**

```bash
git add backend/user/migrations/0002_backfill_base_profiles.py backend/user/tests/test_migration.py pyproject.toml poetry.lock
git commit -m "feat(user): data migration backfills BaseUserProfile from CustomUser"
```

---

## Task 5 — Drop `nickname`/`avatar` columns from `CustomUser` + add transitional setter properties

**Files:**
- Modify: `backend/app/models.py:92-140` (`CustomUser`)
- Create: `backend/app/migrations/00XX_drop_user_nickname_avatar.py`, `backend/user/tests/test_transitional_setters.py`

- [ ] **Step 1: Write failing tests**

Create `backend/user/tests/test_transitional_setters.py`:

```python
from django.test import TestCase

from app.models import CustomUser


class CustomUserTransitionalSettersTests(TestCase):
    def test_nickname_getter_reads_from_base_profile(self):
        user = CustomUser.objects.create(username="gina")
        user.base_profile.nickname = "Gina Display"
        user.base_profile.save()
        # Read via the property
        assert user.nickname == "Gina Display"

    def test_nickname_setter_writes_to_base_profile(self):
        user = CustomUser.objects.create(username="hans")
        user.nickname = "Hans New"  # transitional setter
        # NOTE: setter is not committed until base_profile.save() is called
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Hans New"

    def test_avatar_round_trip(self):
        user = CustomUser.objects.create(username="ida")
        user.avatar = "https://example.com/ida.png"
        user.base_profile.refresh_from_db()
        assert user.base_profile.avatar == "https://example.com/ida.png"
        assert user.avatar == "https://example.com/ida.png"

    def test_fields_removed_from_meta(self):
        # The actual model field is gone; only the property remains.
        field_names = {f.name for f in CustomUser._meta.get_fields()}
        assert "nickname" not in field_names
        assert "avatar" not in field_names

    def test_populate_style_create_keeps_working(self):
        # Mirror the populate-helper call shape: CustomUser(nickname=..., avatar=..., ...)
        user = CustomUser.objects.create(
            username="jake",
            nickname="Jake Initial",
            avatar="https://example.com/jake.png",
        )
        # base_profile is auto-created; transitional setter fired during __init__/save
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Jake Initial"
        assert user.base_profile.avatar == "https://example.com/jake.png"
```

- [ ] **Step 2: Run tests, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_transitional_setters -v 2'
```

Expected: tests pass for any existing field access path (nickname is still a model field), but `test_fields_removed_from_meta` fails (fields still present) and the populate-style test may behave inconsistently. Some tests will fail with `AttributeError` once we make the property changes.

- [ ] **Step 3: Remove fields from `CustomUser` and add transitional properties**

`backend/app/models.py` — find the `CustomUser` field block (around lines 100, 124). Replace the `nickname` and `avatar` field declarations with `@property` definitions:

```python
# Remove these lines:
# nickname = models.TextField(null=True, blank=True)   ← DELETE
# avatar = models.TextField(null=True, blank=True)     ← DELETE
```

Below the field declarations (after `default_organization = ...`), and **before** the existing `save()` method, add:

```python
@property
def nickname(self):
    """Transitional proxy — reads nickname from base_profile.

    Removed in a follow-up cleanup ticket once all writers migrate to
    PATCH /api/users/me/profile/base/.
    """
    bp = getattr(self, "base_profile", None)
    return bp.nickname if bp else None

@nickname.setter
def nickname(self, value):
    """Transitional setter — writes through to base_profile.nickname.

    Persists immediately so populate fixtures and incidental writers
    behave as if the field were still on CustomUser. Invalidates the
    base_profile cacheops row on commit.
    """
    # Use a local import to avoid the circular at module load.
    from user.models import BaseUserProfile
    from app.cache_utils import invalidate_after_commit
    bp = getattr(self, "base_profile", None)
    if bp is None:
        # User hasn't been saved yet (no pk) — buffer the value and apply
        # in save() after auto-create.
        self._pending_nickname = value
        return
    bp.nickname = value
    bp.save(update_fields=["nickname"])
    invalidate_after_commit(bp)

@property
def avatar(self):
    bp = getattr(self, "base_profile", None)
    return bp.avatar if bp else None

@avatar.setter
def avatar(self, value):
    from user.models import BaseUserProfile
    from app.cache_utils import invalidate_after_commit
    bp = getattr(self, "base_profile", None)
    if bp is None:
        self._pending_avatar = value
        return
    bp.avatar = value
    bp.save(update_fields=["avatar"])
    invalidate_after_commit(bp)
```

Also extend `save()` to apply any pending values after auto-create. Replace the existing `save()` (Task 3 modified it) with:

```python
def save(self, *args, **kwargs):
    """Keep steam ids in sync, auto-create BaseUserProfile, flush pending
    nickname/avatar values buffered before the user had a pk.
    """
    if self.steam_account_id is not None:
        self.steamid = self.steam_account_id + self.STEAM_ID_64_BASE
    elif self.steamid is not None:
        self.steam_account_id = self.steamid - self.STEAM_ID_64_BASE

    super().save(*args, **kwargs)

    from user.models import BaseUserProfile
    bp, _ = BaseUserProfile.objects.get_or_create(user=self)

    pending_nickname = getattr(self, "_pending_nickname", None)
    pending_avatar = getattr(self, "_pending_avatar", None)
    fields_to_update = []
    if pending_nickname is not None:
        bp.nickname = pending_nickname
        fields_to_update.append("nickname")
        del self._pending_nickname
    if pending_avatar is not None:
        bp.avatar = pending_avatar
        fields_to_update.append("avatar")
        del self._pending_avatar
    if fields_to_update:
        bp.save(update_fields=fields_to_update)
```

- [ ] **Step 4: Generate the column-drop migration**

```bash
just db::makemigrations app
```

Verify a new migration appears in `backend/app/migrations/` (named something like `00XX_remove_customuser_nickname_avatar.py`).

Edit the generated migration's `dependencies` list to depend on the backfill:

```python
dependencies = [
    ("app", "00XX_previous"),                       # auto-generated previous
    ("user", "0002_backfill_base_profiles"),       # ADD THIS LINE
]
```

- [ ] **Step 5: Run tests, expect pass**

```bash
just db::migrate::test
just test::run 'python manage.py test user.tests.test_transitional_setters -v 2'
```

Expected: 5 tests pass.

- [ ] **Step 6: Smoke-test that populate fixtures still work**

```bash
just db::reset-test
just db::populate::all
```

Expected: populate completes without errors. Spot-check one user (e.g. `ADMIN_USER` pk=1001):

```bash
just test::run 'python -c "
from app.models import CustomUser
u = CustomUser.objects.get(pk=1001)
print(f\"nickname={u.nickname!r} avatar={u.avatar!r} base_profile.pk={u.base_profile.pk}\")
"'
```

Expected: nickname/avatar non-empty, base_profile pk reported.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat(user): drop nickname/avatar columns from CustomUser + transitional setter properties"
```

---

## Task 6 — Update existing serializers to read from `BaseUserProfile`

**Files:**
- Modify: `backend/app/serializers.py` (every serializer that exposes `nickname` or `avatar`)
- Create: `backend/user/tests/test_existing_serializer_compat.py`

- [ ] **Step 1: Identify call sites**

```bash
rg -n '"nickname"|"avatar"' backend/app/serializers.py
```

Note every serializer that lists these fields. Each needs the field declaration to source from `base_profile`.

- [ ] **Step 2: Write failing compatibility test**

Create `backend/user/tests/test_existing_serializer_compat.py`:

```python
from django.test import TestCase

from app.models import CustomUser
from app.serializers import UserSerializer


class UserSerializerNicknameAvatarTests(TestCase):
    def test_nickname_in_payload(self):
        user = CustomUser.objects.create(username="kara")
        user.base_profile.nickname = "Kara Display"
        user.base_profile.avatar = "https://example.com/kara.png"
        user.base_profile.save()

        data = UserSerializer(user).data
        assert data["nickname"] == "Kara Display"
        assert data["avatar"] == "https://example.com/kara.png"
```

Adjust `UserSerializer` import to whichever serializer in `backend/app/serializers.py` is the primary user identity serializer. If multiple, add one test per.

- [ ] **Step 3: Run test, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_existing_serializer_compat -v 2'
```

Expected: `KeyError` or empty/None values for the fields (since the model fields are gone).

- [ ] **Step 4: Update serializers**

For each affected serializer in `backend/app/serializers.py`, change the field declarations to source from `base_profile`:

```python
class UserSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(
        source="base_profile.nickname",
        read_only=True,
        allow_null=True,
    )
    avatar = serializers.CharField(
        source="base_profile.avatar",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = CustomUser
        fields = [...]  # keep existing fields list; nickname/avatar now sourced via above
```

Apply the same change to every serializer found in Step 1.

- [ ] **Step 5: Run tests, expect pass**

```bash
just test::run 'python manage.py test user.tests.test_existing_serializer_compat -v 2'
just test::run 'python manage.py test app -v 2'
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/serializers.py backend/user/tests/test_existing_serializer_compat.py
git commit -m "feat(user): source nickname/avatar from base_profile in existing serializers"
```

---

## Task 7 — `BaseUserProfileSerializer` + `UserProfileLayeredSerializer`

**Files:**
- Create: `backend/user/serializers.py`, `backend/user/tests/test_serializers.py`

- [ ] **Step 1: Write failing serializer tests**

Create `backend/user/tests/test_serializers.py`:

```python
from django.test import TestCase

from app.models import CustomUser
from user.serializers import (
    BaseUserProfileSerializer,
    UserProfileLayeredSerializer,
)


class BaseUserProfileSerializerTests(TestCase):
    def test_serialize(self):
        user = CustomUser.objects.create(username="hans")
        user.base_profile.nickname = "Hans"
        user.base_profile.avatar = "https://example.com/h.png"
        user.base_profile.save()
        data = BaseUserProfileSerializer(user.base_profile).data
        assert data["nickname"] == "Hans"
        assert data["avatar"] == "https://example.com/h.png"

    def test_partial_update(self):
        user = CustomUser.objects.create(username="ida")
        serializer = BaseUserProfileSerializer(
            instance=user.base_profile,
            data={"nickname": "Ida New"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Ida New"


class UserProfileLayeredSerializerTests(TestCase):
    def test_layered_shape(self):
        user = CustomUser.objects.create(username="jake")
        user.base_profile.nickname = "Jake"
        user.base_profile.save()
        data = UserProfileLayeredSerializer(user).data
        assert data["pk"] == user.pk
        assert data["base"]["nickname"] == "Jake"
        assert data["gameUser"] == {}
        assert data["orgProfiles"] == {}
```

- [ ] **Step 2: Run tests, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_serializers -v 2'
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the serializers**

`backend/user/serializers.py`:
```python
from rest_framework import serializers

from app.models import CustomUser

from .models import BaseUserProfile


class BaseUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseUserProfile
        fields = ["nickname", "avatar"]


class UserProfileLayeredSerializer(serializers.Serializer):
    """Layered profile shape consumed by userProfileEntityAdapter on the frontend.

    T1 ships only `base` populated; `gameUser` and `orgProfiles` are placeholders
    that fill in during T2 and T3.
    """

    pk = serializers.IntegerField(read_only=True)
    base = BaseUserProfileSerializer(source="base_profile", read_only=True)
    gameUser = serializers.SerializerMethodField()
    orgProfiles = serializers.SerializerMethodField()

    def get_gameUser(self, user: CustomUser) -> dict:
        return {}  # T2 populates

    def get_orgProfiles(self, user: CustomUser) -> dict:
        return {}  # T3 populates
```

- [ ] **Step 4: Run tests, expect pass**

```bash
just test::run 'python manage.py test user.tests.test_serializers -v 2'
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/user/serializers.py backend/user/tests/test_serializers.py
git commit -m "feat(user): BaseUserProfile + UserProfileLayered serializers"
```

---

## Task 8 — `MeProfileView` (GET layered) + `MeProfileBasePatchView` + URL routes + structlog logging

**Files:**
- Modify: `backend/user/views.py`, `backend/user/urls.py`, `backend/user/tests/test_app_registration.py`
- Create: `backend/user/tests/test_views.py`

- [ ] **Step 1: Write failing view tests**

Create `backend/user/tests/test_views.py`:

```python
from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser


class MeProfileViewTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="kara")
        self.user.set_password("pw")
        self.user.save()
        self.user.base_profile.nickname = "Kara"
        self.user.base_profile.save()
        self.client = APIClient()

    def test_unauthenticated_get_returns_401_or_403(self):
        response = self.client.get("/api/users/me/profile/")
        assert response.status_code in (401, 403)

    def test_authenticated_get_returns_layered_shape(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/users/me/profile/")
        assert response.status_code == 200
        body = response.json()
        assert body["pk"] == self.user.pk
        assert body["base"]["nickname"] == "Kara"
        assert body["gameUser"] == {}
        assert body["orgProfiles"] == {}

    def test_patch_base_updates_only_sent_fields(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            "/api/users/me/profile/base/",
            data={"nickname": "Kara Renamed"},
            format="json",
        )
        assert response.status_code == 200
        self.user.base_profile.refresh_from_db()
        assert self.user.base_profile.nickname == "Kara Renamed"
        assert self.user.base_profile.avatar is None

    def test_patch_base_unauthenticated(self):
        response = self.client.patch(
            "/api/users/me/profile/base/",
            data={"nickname": "x"},
            format="json",
        )
        assert response.status_code in (401, 403)
```

- [ ] **Step 2: Run tests, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_views -v 2'
```

Expected: 404s (ping URL doesn't cover these routes).

- [ ] **Step 3: Implement the views with structlog logging**

Replace `backend/user/views.py`:

```python
import structlog
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import BaseUserProfileSerializer, UserProfileLayeredSerializer


log = structlog.get_logger(__name__)


class MeProfileView(APIView):
    """GET /api/users/me/profile/ — returns the layered profile shape."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        log.debug(
            "profile_fetched",
            system="user",
            subsystem="profile",
            user_id=request.user.id,
        )
        data = UserProfileLayeredSerializer(request.user).data
        return Response(data)


class MeProfileBasePatchView(APIView):
    """PATCH /api/users/me/profile/base/ — updates BaseUserProfile fields."""

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = BaseUserProfileSerializer(
            instance=request.user.base_profile,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            log.warning(
                "profile_base_patch_invalid",
                system="user",
                subsystem="profile",
                user_id=request.user.id,
                errors=serializer.errors,
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        log.info(
            "profile_base_patched",
            system="user",
            subsystem="profile",
            user_id=request.user.id,
            fields_changed=sorted(serializer.validated_data.keys()),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
```

- [ ] **Step 4: Update URL conf**

Replace `backend/user/urls.py`:

```python
from django.urls import path

from .views import MeProfileBasePatchView, MeProfileView

urlpatterns = [
    path("me/profile/", MeProfileView.as_view(), name="me-profile"),
    path("me/profile/base/", MeProfileBasePatchView.as_view(), name="me-profile-base"),
]
```

Update `test_app_registration.py`'s third test — change `me-profile-ping` to `me-profile`:

```python
def test_placeholder_url_resolves(self):
    match = resolve("/api/users/me/profile/")
    assert match.url_name == "me-profile"
```

- [ ] **Step 5: Run tests, expect pass**

```bash
just test::run 'python manage.py test user -v 2'
```

Expected: all `users` tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/user/views.py backend/user/urls.py backend/user/tests/test_views.py backend/user/tests/test_app_registration.py
git commit -m "feat(user): MeProfile GET + Base PATCH views with structlog logging"
```

---

## Task 9 — Cacheops integration: CACHEOPS entry + `@cached_as` updates + grep guardrail

**Files:**
- Modify: `backend/backend/settings.py` (`CACHEOPS` block), `backend/app/views_main.py` (every `@cached_as` site shipping nickname/avatar), `backend/app/functions/tournament.py:456`
- Create: `backend/user/tests/test_cacheops.py`

- [ ] **Step 1: Survey `@cached_as` call sites**

```bash
rg -nB1 -A6 '@cached_as' backend/app/views_main.py backend/app/functions/tournament.py
```

Note every decorator whose cached response includes `nickname` or `avatar` in the payload. These all need `BaseUserProfile` added to the model-dependency list.

- [ ] **Step 2: Write failing cacheops integration test**

Create `backend/user/tests/test_cacheops.py`:

```python
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from tests.populate.user_edit import populate_user_edit_data
from tests.data.users import USER_EDIT_USERS


@override_settings(CACHEOPS_ENABLED=True)
class BaseUserProfileCacheInvalidationTests(TestCase):
    """Verify @cached_as decorators that ship nickname/avatar invalidate
    when BaseUserProfile changes. Uses feature-isolated USER_EDIT_USERS
    (pks 2050-2052) to avoid cross-test pollution.
    """

    def setUp(self):
        populate_user_edit_data()
        cache.clear()
        self.user = CustomUser.objects.get(pk=USER_EDIT_USERS[0].pk)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        from cacheops import invalidate_all
        invalidate_all()

    def test_nickname_change_invalidates_cached_user_list(self):
        # Step 5 in the survey above will tell you which cached endpoint to hit.
        # Replace the URL below with one whose response ships nickname/avatar
        # and is decorated with @cached_as(CustomUser, ...) — e.g. an org
        # roster or a tournament participants list.
        url = "REPLACE_WITH_CACHED_LIST_ENDPOINT_URL"

        first = self.client.get(url).json()

        self.user.base_profile.nickname = f"Renamed-{self.user.pk}"
        self.user.base_profile.save()

        second = self.client.get(url).json()

        # Find the user in both responses and assert nickname updated
        def find_self(body):
            users = body if isinstance(body, list) else body.get("users", body)
            return next(u for u in users if u["pk"] == self.user.pk)

        assert find_self(first)["nickname"] != find_self(second)["nickname"]
        assert find_self(second)["nickname"] == f"Renamed-{self.user.pk}"
```

The exact endpoint URL depends on which cached view is most convenient. Pick one from Step 1's survey and replace `REPLACE_WITH_CACHED_LIST_ENDPOINT_URL`.

- [ ] **Step 3: Run test, expect failure**

```bash
just test::run 'python manage.py test user.tests.test_cacheops -v 2'
```

Expected: second response still shows the old nickname (cache not invalidated because `BaseUserProfile` isn't a dependency yet).

- [ ] **Step 4: Add `user.baseuserprofile` to CACHEOPS**

`backend/backend/settings.py` — find the `CACHEOPS = {...}` block and add:

```python
CACHEOPS = {
    # ... existing entries ...
    "user.baseuserprofile": {"ops": "all", "timeout": 60 * 60},
}
```

- [ ] **Step 5: Update `@cached_as` decorators**

For every `@cached_as(...)` from Step 1's survey, add `BaseUserProfile` to the model list:

```python
from user.models import BaseUserProfile  # add to imports at top of file

@cached_as(
    CustomUser,
    BaseUserProfile,    # ADD this
    # ... existing model deps ...
)
def some_user_listing_view(request):
    ...
```

- [ ] **Step 6: Verify the grep guardrail acceptance criterion**

```bash
rg "@cached_as\(.*CustomUser" backend/app/ backend/user/ | rg -v "BaseUserProfile"
```

Expected: zero lines. Any line returned is a site that still depends on `CustomUser` without also depending on `BaseUserProfile` — those will silently serve stale nickname/avatar after a PATCH.

- [ ] **Step 7: Run tests, expect pass**

```bash
just test::run 'python manage.py test user.tests.test_cacheops -v 2'
just test::run 'python manage.py test user -v 2'
just test::run 'python manage.py test app -v 2'
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/backend/settings.py backend/app/views_main.py backend/app/functions/tournament.py backend/user/tests/test_cacheops.py
git commit -m "feat(user): cacheops integration for BaseUserProfile (@cached_as updates + grep guardrail)"
```

---

## Task 10 — Frontend types (`userProfileTypes.ts`)

**Files:**
- Create: `frontend/app/store/userProfileTypes.ts`

- [ ] **Step 1: Write the type module**

`frontend/app/store/userProfileTypes.ts`:
```ts
import { z } from 'zod';

export const BaseProfileSchema = z.object({
  nickname: z.string().nullable().optional(),
  avatar: z.string().nullable().optional(),
});

export type BaseProfile = z.infer<typeof BaseProfileSchema>;

// Placeholders for T2/T3 — kept as empty objects in T1 so the type shape
// is stable across the epic and no consumer breaks when later tickets
// fill them in.
export type DotaUserProfile = Record<string, never>;
export type DeadlockUserProfile = Record<string, never>;
export type OrgUserProfile = Record<string, never>;
export type OrgDotaUserProfile = Record<string, never>;
export type OrgDeadlockUserProfile = Record<string, never>;

export interface UserProfileEntry {
  pk: number;
  base: BaseProfile;
  gameUser: {
    dota?: DotaUserProfile;
    deadlock?: DeadlockUserProfile;
  };
  orgProfiles: Record<number, {
    orgUser: OrgUserProfile;
    dota?: OrgDotaUserProfile;
    deadlock?: OrgDeadlockUserProfile;
  }>;
  _fetchedAt: number;
}
```

- [ ] **Step 2: Verify TypeScript builds**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/store/userProfileTypes.ts
git commit -m "feat(user): userProfileTypes scaffold (T1 ships only Base layer)"
```

---

## Task 11 — Frontend Zustand store (`userProfileStore.ts`)

**Files:**
- Create: `frontend/app/store/userProfileStore.ts`, `frontend/app/store/userProfileStore.test.ts`
- Modify: logout handler (location varies; see Step 5)

- [ ] **Step 1: Write failing store tests**

Create `frontend/app/store/userProfileStore.test.ts`:

```ts
import { describe, expect, it, beforeEach } from 'vitest';

import { useUserProfileStore } from './userProfileStore';
import type { UserProfileEntry } from './userProfileTypes';

function entry(pk: number, nickname: string | null = 'X'): UserProfileEntry {
  return {
    pk,
    base: { nickname, avatar: null },
    gameUser: {},
    orgProfiles: {},
    _fetchedAt: Date.now(),
  };
}

describe('userProfileStore', () => {
  beforeEach(() => {
    useUserProfileStore.getState().reset();
  });

  it('starts empty', () => {
    expect(useUserProfileStore.getState().entities).toEqual({});
  });

  it('upserts a profile entry', () => {
    useUserProfileStore.getState().upsert(entry(1, 'Alice'));
    expect(useUserProfileStore.getState().entities[1]?.base.nickname).toBe('Alice');
  });

  it('selectBase returns the base profile', () => {
    useUserProfileStore.getState().upsert(entry(2, 'Bob'));
    const base = useUserProfileStore.getState().selectBase(2);
    expect(base).toEqual({ nickname: 'Bob', avatar: null });
  });

  it('upsert returns same identity when nothing changed', () => {
    const e = entry(3, 'Carol');
    useUserProfileStore.getState().upsert(e);
    const first = useUserProfileStore.getState().entities[3];
    useUserProfileStore.getState().upsert({ ...e });   // same content
    const second = useUserProfileStore.getState().entities[3];
    expect(second).toBe(first);   // referential equality preserved
  });

  it('reset clears all entries', () => {
    useUserProfileStore.getState().upsert(entry(4, 'D'));
    useUserProfileStore.getState().reset();
    expect(useUserProfileStore.getState().entities).toEqual({});
  });
});
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd frontend && npx vitest run app/store/userProfileStore.test.ts
```

Expected: `Cannot find module './userProfileStore'`.

- [ ] **Step 3: Implement the store**

`frontend/app/store/userProfileStore.ts`:
```ts
import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import type { BaseProfile, UserProfileEntry } from './userProfileTypes';

interface UserProfileState {
  entities: Record<number, UserProfileEntry>;

  upsert: (entry: UserProfileEntry) => void;
  reset: () => void;
  selectBase: (userPk: number) => BaseProfile | undefined;
}

function sameBase(a: BaseProfile, b: BaseProfile): boolean {
  return a.nickname === b.nickname && a.avatar === b.avatar;
}

function sameGameUser(
  a: UserProfileEntry['gameUser'],
  b: UserProfileEntry['gameUser'],
): boolean {
  return a.dota === b.dota && a.deadlock === b.deadlock;
}

function sameOrgProfiles(
  a: UserProfileEntry['orgProfiles'],
  b: UserProfileEntry['orgProfiles'],
): boolean {
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (a[Number(k)] !== b[Number(k)]) return false;
  }
  return true;
}

/**
 * Custom hasChanged: compare base + gameUser + orgProfiles slots.
 * Default schema-only equality would silently drop nested updates.
 * Mirrors userCacheStore.ts:41-60 (hasScopedChanged).
 */
function hasChanged(existing: UserProfileEntry, incoming: UserProfileEntry): boolean {
  return (
    !sameBase(existing.base, incoming.base) ||
    !sameGameUser(existing.gameUser, incoming.gameUser) ||
    !sameOrgProfiles(existing.orgProfiles, incoming.orgProfiles)
  );
}

export const useUserProfileStore = create<UserProfileState>()(
  devtools(
    (set, get) => ({
      entities: {},

      upsert: (entry) =>
        set(
          (state) => {
            const existing = state.entities[entry.pk];
            if (existing && !hasChanged(existing, entry)) {
              // Identity preserved — no re-render trigger for unchanged content.
              return state;
            }
            return {
              entities: { ...state.entities, [entry.pk]: entry },
            };
          },
          false,
          'userProfile/upsert',
        ),

      reset: () => set({ entities: {} }, false, 'userProfile/reset'),

      selectBase: (userPk) => get().entities[userPk]?.base,
    }),
    { name: 'userProfileStore' },
  ),
);
```

(No `immer` middleware here — `frontend/package.json` doesn't include `immer` today; T2 can adopt it if `orgProfiles` nested writes become painful.)

- [ ] **Step 4: Run tests, expect pass**

```bash
cd frontend && npx vitest run app/store/userProfileStore.test.ts
```

Expected: 5 tests pass.

- [ ] **Step 5: Wire `reset()` to the logout flow**

Find the logout handler:
```bash
grep -rnE "(logout|logOut|signOut)" frontend/app/store/userStore.ts frontend/app/components/
```

Add `useUserProfileStore.getState().reset()` alongside the existing user-cache reset (likely `useUserCacheStore.getState().reset()`). If no existing reset exists, add both there.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/store/userProfileStore.ts frontend/app/store/userProfileStore.test.ts
# Also commit the logout-wiring change (path varies):
git add frontend/app/store/userStore.ts  # or whichever file you modified
git commit -m "feat(user): userProfileStore (Zustand + custom hasChanged + reset on logout)"
```

---

## Task 12 — Frontend API client functions

**Files:**
- Create: `frontend/app/components/api/userProfileApi.ts`

- [ ] **Step 1: Inspect existing API client conventions**

```bash
head -40 frontend/app/components/api/api.ts
```

Note the request shape (e.g. `apiClient.get('/users/me/')`) and auth/CSRF handling.

- [ ] **Step 2: Write the API client**

`frontend/app/components/api/userProfileApi.ts`:
```ts
import type { UserProfileEntry } from '~/store/userProfileTypes';

import { apiClient } from './api';   // adjust to the actual import name

export interface BasePatchPayload {
  nickname?: string | null;
  avatar?: string | null;
}

export interface BasePatchResponse {
  nickname?: string | null;
  avatar?: string | null;
}

/**
 * Fetch the current user's layered profile. T1 returns base only;
 * gameUser and orgProfiles are present but empty.
 */
export async function getUserProfile(_userPk: number): Promise<UserProfileEntry> {
  const response = await apiClient.get('/users/me/profile/');
  return {
    ...response.data,
    _fetchedAt: Date.now(),
  };
}

/**
 * PATCH /api/users/me/profile/base/ — partial update of BaseUserProfile fields.
 */
export async function patchBaseProfile(
  patch: BasePatchPayload,
): Promise<BasePatchResponse> {
  const response = await apiClient.patch('/users/me/profile/base/', patch);
  return response.data;
}
```

Adjust the `apiClient` import + method signatures to match `frontend/app/components/api/api.ts`'s existing client.

- [ ] **Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/api/userProfileApi.ts
git commit -m "feat(user): API client functions for layered profile GET + base PATCH"
```

---

## Task 13 — Modal shell (`<ErrorBoundary>` → `<Suspense>` → `useSuspenseQuery`) + Tabs scaffold

**Files:**
- Create: `frontend/app/pages/user/EditProfileModal/schemas.ts`, `frontend/app/pages/user/EditProfileModal/ProfileSkeleton.tsx`, `frontend/app/pages/user/EditProfileModal/ProfileErrorFallback.tsx`
- Rewrite: `frontend/app/pages/user/EditProfileModal.tsx` (atomically replace old content)

- [ ] **Step 1: Define the Zod schema**

`frontend/app/pages/user/EditProfileModal/schemas.ts`:
```ts
import { z } from 'zod';

export const BaseProfileFormSchema = z.object({
  nickname: z.string().min(0).max(100).nullable().optional(),
  avatar: z.string().url().nullable().optional().or(z.literal('')),
});

export type BaseProfileFormValues = z.infer<typeof BaseProfileFormSchema>;
```

- [ ] **Step 2: Skeleton fallback**

`frontend/app/pages/user/EditProfileModal/ProfileSkeleton.tsx`:
```tsx
export function ProfileSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="h-6 w-1/3 animate-pulse rounded bg-base-200" />
      <div className="h-10 w-full animate-pulse rounded bg-base-200" />
      <div className="h-10 w-full animate-pulse rounded bg-base-200" />
    </div>
  );
}
```

- [ ] **Step 3: ErrorBoundary fallback**

`frontend/app/pages/user/EditProfileModal/ProfileErrorFallback.tsx`:
```tsx
interface ProfileErrorFallbackProps {
  error?: Error;
  resetErrorBoundary?: () => void;
}

export function ProfileErrorFallback({ error, resetErrorBoundary }: ProfileErrorFallbackProps) {
  return (
    <div className="p-4 space-y-2">
      <p className="text-sm text-base-content">
        Could not load profile. {error?.message}
      </p>
      {resetErrorBoundary && (
        <button
          type="button"
          onClick={resetErrorBoundary}
          className="underline text-sm"
        >
          Retry
        </button>
      )}
    </div>
  );
}
```

(Acceptable raw `<button>` here because this is the error-fallback path — not the primary CTA. If the project has a `<TextButton>` brand primitive, swap it in.)

- [ ] **Step 4: Modal shell**

Replace `frontend/app/pages/user/EditProfileModal.tsx` (atomically replaces the old flat-form modal):

```tsx
import { lazy, Suspense, useEffect } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import { useSuspenseQuery } from '@tanstack/react-query';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { getUserProfile } from '~/components/api/userProfileApi';
import { useUserProfileStore } from '~/store/userProfileStore';

import { ProfileSkeleton } from './EditProfileModal/ProfileSkeleton';
import { ProfileErrorFallback } from './EditProfileModal/ProfileErrorFallback';

const BaseTab = lazy(() => import('./EditProfileModal/tabs/BaseTab'));

interface EditProfileModalProps {
  userPk: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: () => void;
}

export function EditProfileModal({
  userPk,
  open,
  onOpenChange,
  onSave,
}: EditProfileModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto flex flex-col">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
          <DialogDescription>Update your profile information</DialogDescription>
        </DialogHeader>

        <ErrorBoundary FallbackComponent={ProfileErrorFallback}>
          <Suspense fallback={<ProfileSkeleton />}>
            <EditProfileModalBody
              userPk={userPk}
              onSave={onSave}
              onClose={() => onOpenChange(false)}
            />
          </Suspense>
        </ErrorBoundary>
      </DialogContent>
    </Dialog>
  );
}

function EditProfileModalBody({
  userPk,
  onSave,
  onClose,
}: {
  userPk: number;
  onSave?: () => void;
  onClose: () => void;
}) {
  const { data } = useSuspenseQuery({
    queryKey: ['userProfile', userPk],
    queryFn: () => getUserProfile(userPk),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  // Write-through to Zustand — NOT inside select (select must be pure).
  useEffect(() => {
    useUserProfileStore.getState().upsert(data);
  }, [data]);

  return (
    <Tabs defaultValue="base">
      <TabsList>
        <TabsTrigger value="base" data-testid="edit-user-tab-base">
          Base
        </TabsTrigger>
        {/* T2 adds: <TabsTrigger value="dota">Dota</TabsTrigger> etc. */}
      </TabsList>
      <TabsContent value="base">
        <Suspense fallback={<ProfileSkeleton />}>
          <BaseTab profile={data} onSave={onSave} onClose={onClose} />
        </Suspense>
      </TabsContent>
    </Tabs>
  );
}
```

If `react-error-boundary` is not yet in `frontend/package.json`, install it:

```bash
cd frontend && npm install react-error-boundary
```

(Verify first with `grep "react-error-boundary" frontend/package.json` — if it's already there, skip the install.)

- [ ] **Step 5: Typecheck (BaseTab not implemented yet — expected compile failure)**

```bash
cd frontend && npx tsc --noEmit
```

Expected: error about `./EditProfileModal/tabs/BaseTab` module not found. Task 14 fixes it.

- [ ] **Step 6: Commit (compile error is acceptable — next task fixes it)**

```bash
git add frontend/app/pages/user/EditProfileModal.tsx frontend/app/pages/user/EditProfileModal/schemas.ts frontend/app/pages/user/EditProfileModal/ProfileSkeleton.tsx frontend/app/pages/user/EditProfileModal/ProfileErrorFallback.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(user): EditProfileModal shell with ErrorBoundary + Suspense + useSuspenseQuery"
```

---

## Task 14 — Base tab implementation (shadcn Form + Zod + `useMutation` + brand primitives + dual-write)

**Files:**
- Create: `frontend/app/pages/user/EditProfileModal/tabs/BaseTab.tsx`

- [ ] **Step 1: Check existing brand primitives**

```bash
ls frontend/app/components/ui/buttons/
ls frontend/app/components/user/ | grep -i avatar
```

Confirm `CancelButton`, `SubmitButton`, `EditButton`, `UserAvatar` exist and note their import paths + props.

- [ ] **Step 2: Implement BaseTab**

`frontend/app/pages/user/EditProfileModal/tabs/BaseTab.tsx`:

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import * as Sentry from '@sentry/react';
import { toast } from 'sonner';

import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { CancelButton } from '~/components/ui/buttons/CancelButton';
import { SubmitButton } from '~/components/ui/buttons/SubmitButton';
import { EditButton } from '~/components/ui/buttons/EditButton';
import { UserAvatar } from '~/components/user/UserAvatar';
import { patchBaseProfile, type BasePatchPayload } from '~/components/api/userProfileApi';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserProfileStore } from '~/store/userProfileStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';

import { BaseProfileFormSchema, type BaseProfileFormValues } from '../schemas';

const log = {
  debug: (...args: unknown[]) => console.debug('[user.editProfile.base]', ...args),
  warn: (...args: unknown[]) => console.warn('[user.editProfile.base]', ...args),
  error: (...args: unknown[]) => console.error('[user.editProfile.base]', ...args),
};

interface BaseTabProps {
  profile: UserProfileEntry;
  onSave?: () => void;
  onClose: () => void;
}

export default function BaseTab({ profile, onSave, onClose }: BaseTabProps) {
  const queryClient = useQueryClient();

  const form = useForm<BaseProfileFormValues>({
    resolver: zodResolver(BaseProfileFormSchema),
    defaultValues: {
      nickname: profile.base.nickname ?? '',
      avatar: profile.base.avatar ?? '',
    },
  });

  const mutation = useMutation({
    mutationFn: (patch: BasePatchPayload) => patchBaseProfile(patch),
    onSuccess: (updated) => {
      // 1. Dual-write to userAdapter so UserCard refreshes in the same microtask.
      useUserCacheStore.getState().upsert({
        pk: profile.pk,
        nickname: updated.nickname ?? null,
        avatar: updated.avatar ?? null,
      });
      // 2. Mark the profile query stale so the next read refetches.
      queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });
      // 3. Mirror the change into the profile store immediately for any
      //    consumers reading via the adapter rather than the query.
      useUserProfileStore.setState((state) => ({
        entities: {
          ...state.entities,
          [profile.pk]: {
            ...state.entities[profile.pk],
            base: { ...state.entities[profile.pk]?.base, ...updated },
            _fetchedAt: Date.now(),
          } as UserProfileEntry,
        },
      }));
      log.debug('base_patch_success', { userPk: profile.pk, updated });
      toast.success('Profile updated');
      onSave?.();
      onClose();
    },
    onError: (err) => {
      log.error('base_patch_failed', { userPk: profile.pk, error: String(err) });
      Sentry.captureException(err, {
        tags: { system: 'users', subsystem: 'profile' },
        extra: { userPk: profile.pk },
      });
      toast.error('Failed to update profile');
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    // Only send dirty fields — dirtyFields semantics per react-hook-form.
    const { dirtyFields } = form.formState;
    const payload: BasePatchPayload = {};
    if (dirtyFields.nickname) payload.nickname = values.nickname ?? null;
    if (dirtyFields.avatar) payload.avatar = values.avatar ?? null;
    if (Object.keys(payload).length === 0) {
      onClose();
      return;
    }
    mutation.mutate(payload);
  });

  const watchedAvatar = form.watch('avatar');
  const watchedNickname = form.watch('nickname');

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="flex items-center gap-4">
          <UserAvatar
            user={{
              pk: profile.pk,
              nickname: watchedNickname ?? null,
              avatar: watchedAvatar ?? null,
            }}
            size="lg"
          />
          <EditButton
            type="button"
            onClick={() => document.getElementById('avatar-input')?.focus()}
            data-testid="edit-user-avatar-trigger"
          >
            Change avatar
          </EditButton>
        </div>

        <FormField
          control={form.control}
          name="nickname"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nickname</FormLabel>
              <FormControl>
                <Input
                  placeholder="Enter your nickname"
                  data-testid="edit-user-nickname"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>Display name shown on your profile</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="avatar"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Avatar URL</FormLabel>
              <FormControl>
                <Input
                  id="avatar-input"
                  placeholder="https://example.com/avatar.png"
                  data-testid="edit-user-avatar"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end gap-2 pt-4">
          <CancelButton type="button" onClick={onClose}>
            Cancel
          </CancelButton>
          <SubmitButton
            loading={mutation.isPending}
            loadingText="Saving..."
            data-testid="edit-user-save"
          >
            Save Changes
          </SubmitButton>
        </div>
      </form>
    </Form>
  );
}
```

Notes:
- `UserAvatar`'s `user` prop is typed concretely (`{ pk, nickname, avatar }`); no `as never`. Adjust the prop shape if your `UserAvatar` accepts a different minimum type.
- `useUserCacheStore.getState().upsert(...)` is called with a real `Partial<UserType>` shape — no `as never`. If the existing `upsert` signature requires more fields, either widen the signature or use the cache store's `getById` + spread pattern.
- The `useEffect` for write-through stays in the parent shell (Task 13). The mutation's `onSuccess` does its own micro-write into the store for immediate UI feedback before the query refetch finishes.

If `@sentry/react` is not in `frontend/package.json`, verify it's actually installed and used elsewhere — if not, replace the `Sentry.captureException(...)` call with a TODO and a `log.error(...)` (a separate cleanup can wire Sentry later).

- [ ] **Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Brand sanity check**

```bash
rg "from '~/components/ui/button'" frontend/app/pages/user/EditProfileModal/ frontend/app/pages/user/EditProfileModal.tsx
```

Expected: zero hits.

```bash
rg 'variant=["'\''](outline|destructive|ghost)["'\'']' frontend/app/pages/user/EditProfileModal/
```

Expected: zero hits.

```bash
rg "as never" frontend/app/pages/user/EditProfileModal/
```

Expected: zero hits.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/pages/user/EditProfileModal/tabs/BaseTab.tsx
git commit -m "feat(user): BaseTab — shadcn Form + Zod + useMutation + brand primitives + dual-write"
```

---

## Task 15 — Wire mount point + verify list views unaffected

**Files:**
- Modify: `frontend/app/routes/editProfile.tsx`, `frontend/app/pages/user/UserProfilePage.tsx:20,181`

- [ ] **Step 1: Find every importer of the modal**

```bash
grep -nR "EditProfileModal" frontend/app/
```

Expected: `frontend/app/routes/editProfile.tsx`, `frontend/app/pages/user/UserProfilePage.tsx`. Any other consumer is also updated below.

- [ ] **Step 2: Update prop shape (modal now takes `userPk`, not the whole user)**

In each importer, change the JSX to pass `userPk={user.pk}`:

```tsx
<EditProfileModal
  userPk={user.pk}
  open={editOpen}
  onOpenChange={setEditOpen}
  onSave={refetch}
/>
```

The import itself doesn't need to change — the file path is the same since we atomically replaced the content.

- [ ] **Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Run the frontend unit suite**

```bash
cd frontend && npx vitest run
```

Expected: all pass.

- [ ] **Step 5: Smoke-test in a browser**

```bash
just dev::debug
```

Open the app, log in, click Edit Profile. Verify:
- Modal opens.
- Nickname + avatar fields pre-fill from current values.
- Changing nickname and saving shows a success toast.
- Modal closes.
- UserCard on the same page reflects the new nickname (dual-write).
- Page refresh — change persists.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/routes/editProfile.tsx frontend/app/pages/user/UserProfilePage.tsx
git commit -m "feat(user): wire EditProfileModal mount points to new userPk API"
```

---

## Task 16 — Playwright spec rewrite (`15-edit-user/06-profile-edit.spec.ts`)

**Files:**
- Rewrite: `frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts`

- [ ] **Step 1: Read existing spec for conventions**

```bash
cat frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts | head -40
cat frontend/tests/playwright/helpers/edit-user.ts | head -80
```

Note:
- Test import: `import { test, expect } from '../../fixtures'`
- Auth: `test.beforeEach(async ({ loginAdmin }) => { await loginAdmin(); })` (or `loginAsUser`)
- Selectors: `[data-testid="edit-user-{field}"]`
- Helpers: `openEditModal`, `fillEditField`, `saveEditModal`

- [ ] **Step 2: Rewrite the spec**

`frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts`:

```ts
import { test, expect } from '../../fixtures';

test.describe('Edit Profile — Base tab (new layered modal)', () => {
  test('user can change nickname and see it reflect in UserCard without refresh', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();
    await page.goto('/profile');

    // Read current nickname so we can restore it at the end
    const editTrigger = page.locator('[data-testid="edit-user-btn"]').first();
    await expect(editTrigger).toBeVisible({ timeout: 10_000 });
    await editTrigger.click();

    const nicknameInput = page.locator('[data-testid="edit-user-nickname"]');
    await expect(nicknameInput).toBeVisible({ timeout: 5_000 });
    const originalNickname = await nicknameInput.inputValue();

    try {
      const newNickname = `Renamed-${Date.now()}`;
      await nicknameInput.fill(newNickname);
      await page.locator('[data-testid="edit-user-save"]').click();

      await expect(page.getByText(/profile updated/i)).toBeVisible({ timeout: 10_000 });
      await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });

      // Dual-write verification — UserCard reflects new nickname via userAdapter
      // (auto-retrying assertion handles the microtask race).
      const userCardName = page
        .locator('[data-testid="user-card-nickname"]')
        .first();
      await expect(userCardName).toHaveText(newNickname, { timeout: 10_000 });
    } finally {
      // Restore — pattern from 06-profile-edit.spec.ts:93-141 (existing convention)
      await editTrigger.click();
      await expect(nicknameInput).toBeVisible({ timeout: 5_000 });
      await nicknameInput.fill(originalNickname);
      await page.locator('[data-testid="edit-user-save"]').click();
      await expect(page.getByText(/profile updated/i)).toBeVisible({ timeout: 10_000 });
    }
  });

  test('avatar URL updates persist across reload', async ({ page, loginAdmin }) => {
    await loginAdmin();
    await page.goto('/profile');

    await page.locator('[data-testid="edit-user-btn"]').first().click();
    const avatarInput = page.locator('[data-testid="edit-user-avatar"]');
    await expect(avatarInput).toBeVisible({ timeout: 5_000 });
    const originalAvatar = await avatarInput.inputValue();

    const newAvatar = `https://example.com/test-${Date.now()}.png`;
    try {
      await avatarInput.fill(newAvatar);
      await page.locator('[data-testid="edit-user-save"]').click();
      await expect(page.getByText(/profile updated/i)).toBeVisible({ timeout: 10_000 });

      await page.reload();
      await page.locator('[data-testid="edit-user-btn"]').first().click();
      await expect(page.locator('[data-testid="edit-user-avatar"]')).toHaveValue(
        newAvatar,
        { timeout: 10_000 },
      );
    } finally {
      await page.locator('[data-testid="edit-user-avatar"]').fill(originalAvatar);
      await page.locator('[data-testid="edit-user-save"]').click();
      await expect(page.getByText(/profile updated/i)).toBeVisible({ timeout: 10_000 });
    }
  });
});
```

If the actual `UserCard` test-id is different, replace `user-card-nickname` with the correct selector (check `grep -rn "data-testid.*nickname" frontend/app/`).

- [ ] **Step 3: Run the spec**

```bash
just test::pw::spec 06-profile-edit
```

Expected: 2 tests pass.

- [ ] **Step 4: Run the full edit-user suite to check for regressions**

```bash
just test::pw::spec 15-edit-user
```

Expected: all green (the other specs in `15-edit-user/` rely on the same `data-testid` selectors, which the new modal preserves).

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts
git commit -m "test(user): Playwright spec for new EditProfileModal Base tab (with restore + auto-retry)"
```

---

## Final verification

- [ ] **Run all backend test modules**

```bash
just test::run 'python manage.py test user -v 2'
just test::run 'python manage.py test app -v 2'
```

Expected: all green.

- [ ] **Run all frontend unit tests**

```bash
cd frontend && npx vitest run
```

Expected: all green.

- [ ] **Run full Playwright headless**

```bash
just test::pw::headless
```

Expected: no regressions (new spec passes, plus all existing specs in `15-edit-user/` and elsewhere).

- [ ] **Grep guardrails**

```bash
rg "@cached_as\(.*CustomUser" backend/app/ backend/user/ | rg -v "BaseUserProfile"
# Expected: empty
rg "from '~/components/ui/button'" frontend/app/pages/user/EditProfileModal/ frontend/app/pages/user/EditProfileModal.tsx
# Expected: empty
rg "as never" frontend/app/pages/user/EditProfileModal/
# Expected: empty
rg 'variant=["'\''](outline|destructive|ghost)["'\'']' frontend/app/pages/user/EditProfileModal/
# Expected: empty
```

- [ ] **Smoke-test populate fixtures still work**

```bash
just db::reset-test
just db::populate::all
just test::run 'python manage.py test user -v 2'
```

Expected: populate completes; `users` suite still green against populated data.

- [ ] **Push and open PR**

```bash
git push -u origin <branch>
gh pr create --title "T1: BaseUserProfile end-to-end (epic #224)" --body "$(cat <<'EOF'
## Summary
- New `users` Django app
- Moves `nickname` and `avatar` off `CustomUser` into new `BaseUserProfile` (OneToOne)
- Transitional setter properties on `CustomUser.nickname`/`avatar` keep populate fixtures and incidental writers working
- Auto-creates `BaseUserProfile` on every `CustomUser` save
- `GET /api/users/me/profile/` (layered) + `PATCH /api/users/me/profile/base/` with structlog logging
- `userProfileEntityAdapter` (Zustand) scaffolded — only Base layer wired
- New `EditProfileModal` (ErrorBoundary → Suspense → useSuspenseQuery; per-tab useMutation; lazy-mounted tabs; brand primitives; dual-write to `userAdapter` + `queryClient.invalidateQueries` on PATCH success)
- `user.baseuserprofile` added to `CACHEOPS`; every `@cached_as(CustomUser,…)` site that ships nickname/avatar now depends on `BaseUserProfile` (grep guardrail acceptance)

## Spec
`docs/plans/2026-05-17-user-profile-entity-adapter-epic-design.md` §T1

## Test plan
- [x] `just test::run 'python manage.py test user -v 2'`
- [x] `just test::run 'python manage.py test app -v 2'` (no regressions)
- [x] `cd frontend && npx vitest run`
- [x] `just test::pw::spec 15-edit-user` (rewritten 06-profile-edit + existing specs)
- [x] `just test::pw::headless` (no other regressions)
- [x] Grep guardrails: `@cached_as` deps, no raw button imports, no `as never`, no outline variants
- [x] Manual smoke: populate + edit profile + reflect in UserCard + reload persists

## Follow-ups
- T2: `DotaUserProfile` + `DeadlockUserProfile` user-wide layer + Dota/Deadlock tabs + `PositionsModel.save()` rewrite (blocker-class invalidation chain).
- T3: `OrgUserProfile` + per-org game profiles + per-org tabs.
- Cleanup: remove `CustomUser.nickname`/`avatar` transitional setter properties after one release.
EOF
)"
```

---

## Lessons learned — bind these patterns into T2/T3

Captured during PR #250 review iterations. T2 and T3 should inherit these by design; don't relearn them by review.

1. **`select_related` is required on every queryset feeding a user-shaped serializer.**
   `UserSerializer`, `TournamentUserSerializer`, `OrgUserSerializer`, `LeagueUserSerializer` all resolve `nickname`/`avatar` via the `CustomUser` `@property` (`self.base_profile.<x>`), so DRF cannot auto-detect the join. Cold-cache hits eat N extra SELECTs. The same will be true for T2's `DotaUserProfile`/`DeadlockUserProfile` and T3's `OrgUserProfile`. Patterns landed in T1:
   - Direct user queryset: `.select_related("base_profile")` (plus existing `"positions"`).
   - Reverse through `OrgUser`/`LeagueUser`: `.select_related("user__base_profile")` (plus existing `"user", "user__positions"`).
   - Fix sites in T1 (use as templates): `backend/app/views_main.py` UserView queryset + org/league list endpoints, `backend/app/views/admin_team.py` search + org_user detail, `backend/app/serializers.py` `_build_users_dict` + `_serialize_users_with_mmr`.
   - T2/T3 equivalent: every queryset that flows into a serializer reading `obj.dota_profile.x` / `obj.deadlock_profile.x` / `obj.org_user_profile.x` MUST `select_related` the new model.

2. **Pre-pk pending-buffer flush: hold the `del` until after `bp.save()` succeeds.**
   `CustomUser.save()` buffers `_pending_nickname`/`_pending_avatar` while `pk is None`, then flushes after `BaseUserProfile.get_or_create`. The `del self._pending_*` MUST come *after* `bp.save(update_fields=...)` returns, otherwise a transient DB failure loses the buffer and a retry has nothing to flush. T2's per-game profiles will need the same pattern if they introduce any pre-pk-buffered setter on `CustomUser`.

3. **`test_populate_style_create_keeps_working` is legitimate — don't refactor it.**
   `CustomUser(nickname="X")` *does* exercise the `@property.setter` because Django's `Model.__init__` invokes class-level descriptors via `setattr()` (the descriptor protocol). One earlier review claim said the test passed for the wrong reason; verification proved that wrong. Future readers may have the same instinct — the docstring on the test itself should call this out (and the broader test_transitional_setters file does cover the no-pk → save path explicitly via `test_nickname_setter_writes_to_base_profile`).

4. **`UserSerializer`/`TournamentUserSerializer` nickname/avatar are writable, NOT `read_only=True`.**
   The plan originally specified `read_only=True` to "force callers to use the new endpoint." That broke admin PATCH `/api/users/<pk>/`: DRF silently drops `read_only` fields on write, so the admin user-edit flow became a no-op. Correct pattern (now in code): plain `CharField(allow_null=True, allow_blank=True, required=False)` — writes route through the `@property.setter` which writes through to `base_profile`. T2/T3 must preserve this writability for any field they migrate off `CustomUser`.

5. **`allow_blank=True` is required wherever `TextField(blank=True)` is in the model.**
   DRF `CharField` defaults to `allow_blank=False`, which 400s `{"field": ""}`. The base profile fields are `TextField(null=True, blank=True)`, so the serializer fields need `allow_null=True, allow_blank=True`. T2/T3 fields likely follow the same shape (display-only strings) — keep the pattern.

6. **`BaseTab.onSuccess` 4-way store sync is load-bearing, not over-engineered.**
   The mutation `onSuccess` writes to `userCacheStore.upsert`, `userProfileStore.upsert`, `userStore.patchCurrentUser`, then `queryClient.invalidateQueries`. `EditProfileModal` also has a write-through `useEffect` that mirrors fetched data into `userProfileStore`. Surface read: looks redundant — surely the refetch via invalidateQueries handles everything? **No.** `onClose()` fires immediately in the same microtask after `onSave?.()`, which unmounts `EditProfileModal` before its write-through `useEffect` can re-run on refetched data. The manual writes are what update the navbar/header/list view *now*. The invalidate is what makes the next mount fetch fresh. Both are required. T2/T3 game/org tabs should follow the same shape.

7. **Discord avatar is a HASH (~32 chars), not a URL.**
   `BaseUserProfile.avatar` stores the Discord avatar hash; `CustomUser.avatarUrl` is a computed `@property` that builds the CDN URL from `discordId` + hash. Any UI that lets a user "edit avatar" must not validate as a URL or store a URL. T1's `BaseTab.tsx` intentionally has no avatar input — avatar is read-only display only. T2's Dota/Deadlock tabs may have game-icon avatars; check whether those are hashes (Discord-style) or URLs (uploaded artwork) and validate accordingly.

8. **`update_user_avatar` internal endpoint: sanity-cap the payload.**
   The Celery avatar-refresh task is the only ingress, but the endpoint accepts any string. Cap at 64 chars (animated Discord hashes are 34 with the `a_` prefix; 32 plain). T2/T3 internal endpoints that accept Discord-shaped data should follow.

9. **`@cached_as(..., BaseUserProfile, ...)` dep declaration.**
   Every endpoint shipping nickname/avatar must list `BaseUserProfile` in `cached_as` deps so post-PATCH eviction works. `backend/user/tests/test_cacheops.py` is the static grep guardrail (catches obvious misses). `backend/user/tests/test_cacheops_integration.py` is the live-Redis behavioral test (catches subtle dep gaps when run inside `just test::run`). T2's `DotaUserProfile`/`DeadlockUserProfile` and T3's `OrgUserProfile` will need their own grep targets added to `test_cacheops.py:SCAN_TARGETS` and their own behavioral tests mirroring `test_cacheops_integration.py`.

10. **Frontend logger: always `getLogger('namespace')` from `~/lib/logger`.**
    Never hand-roll `const log = { debug: (...) => console.debug('[ns]', ...) }` wrappers. The project logger is consola-backed and handles level gating in dev/test vs prod. T2/T3 tabs/stores: `getLogger('user.editProfile.dota')`, `getLogger('user.editProfile.org')`, etc.

11. **`userStore.patchCurrentUser(partial)` exists — use it for any partial currentUser update.**
    `setCurrentUser` is a full replace; `patchCurrentUser` is the partial-merge helper, guards on `currentUser.pk`, and is the right primitive when a PATCH succeeds and only one or two fields changed. T2 nickname-via-OrgUser flows (if any) should call this rather than spreading manually.

12. **3-generic `useForm<z.input<typeof S>, unknown, OutputType>` for any zod schema with `.default()` / `.transform()`.**
    Project convention from main's `2e41cf80` `fix(types): align useForm generics with zodResolver input/output split`. T1's `BaseTab` got away with single-generic because the schema is pure-shape, but T2's Dota/Deadlock tabs and T3's org tabs will almost certainly have position-default `.default(3)` style fields — use the 3-generic form from day one. Examples: `MmrApprovalModal.tsx:75`, `EditOrgDefaultsModal.tsx:72`.

13. **Sweep N+1 outside the `app/` boundary, not just inside it.**
    The first review pass caught `select_related("base_profile")` gaps in `backend/app/`. A *second* sweep was needed for cross-app serializers that read `user.nickname` / `user.avatar` through the `@property`: `backend/events/views.py` (`subscribers`, `EventSignupViewSet.get_queryset`), `backend/steam/views.py` (`LeaderboardView.get_queryset`). T2/T3 must do the same cross-app sweep when their new fields ship — grep all `source="user.<field>"` in `*/serializers.py`, then grep the queryset that feeds each serializer.

14. **Cacheops integration tests need `TransactionTestCase`, not `TestCase`.**
    `invalidate_after_commit` schedules eviction via `transaction.on_commit`. Plain `TestCase` wraps each test in a transaction that's rolled back at teardown — the on_commit hook never fires mid-test, the cache is never evicted between warm and re-fetch, and the test passes for the wrong reason (cache evicted at teardown, not by the PATCH). Use `TransactionTestCase` for any live-Redis behavioral test that exercises `on_commit`-scheduled invalidation. Pattern: `backend/app/tests/test_league_serializer.py:136`. T2/T3's equivalent integration tests (`DotaUserProfile`, `OrgUserProfile`) must inherit this rule.

---

## Self-review notes

- **Spec coverage:** every §T1 requirement maps to a task (users app: T1; model + auto-create: T2-3; data migration: T4; column drop + transitional setters: T5; existing-serializer update: T6; new serializers: T7; views + structlog: T8; cacheops + grep guardrail: T9; frontend types/store/api: T10-12; modal shell with ErrorBoundary + Suspense + useSuspenseQuery: T13; Base tab with useMutation + dual-write + brand primitives + no `as never`: T14; mount swap: T15; Playwright rewrite at `15-edit-user/06-profile-edit.spec.ts`: T16). Frontend hook & data-loading contract (from spec) lands in T13/T14 (useSuspenseQuery + useMutation + invalidateQueries + lazy tab + dual-write). Logging conventions land in T8 (backend) + T14 (frontend bracket prefix + Sentry).
- **Reviewer findings actively addressed:** `select`-purity (T13 useEffect, not select side-effect); ErrorBoundary (T13); useMutation not useActionState (T14); no V2 suffix (T13 atomic replace); sibling-dir file org matching EventSignupModal (T13/T14); no `as never` casts (T14, with grep guardrail in final-verification); `loginAdmin` fixture (T16); `data-testid` selectors (T13/T14/T16); restore-in-test (T16); `expect.toHaveText` auto-retry (T16); poetry not requirements.txt (T4); transitional setters keep populate working (T5).
- **Two "look this up" instructions** kept explicit: T4 step 4 ("latest `app` migration name") and T9 step 2 ("specific cached endpoint URL to use in the integration test"). These need real investigation at execution time.
- **Per-task type consistency:** `UserProfileEntry`, `BaseProfile`, `selectBase`, `upsert`, `reset`, `useUserProfileStore` — identical across tasks 10-16. `BasePatchPayload` defined in T12, consumed in T14. `loginAdmin`/`loginAsUser` named per actual fixture file.
