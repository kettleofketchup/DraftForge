# Per-User Core Cache (Scope A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Make user serialization/fetch fast and **independently cached per-user**, with **zero change to any response shape** (so zero frontend impact, minimal risk). This is the safe foundation; the full structural-cache decoupling + prebaked-once-everywhere is a deliberately-deferred epic (Scope B, appended).

**Lands BEFORE T2**, off `main`. `positions` is still the real `CustomUser.positions` column here; T2 repoints the one shared JOIN when it rebases.

**Architecture:**
- `serialize_user_core(pk)` — `@cached_as(CustomUser.objects.filter(pk=pk), BaseUserProfile.objects.filter(user_id=pk), extra="user_core:{pk}")` returning the **context-stable** user fields only (positions, nickname, avatar, avatarUrl, steam_account_id, discordId, username, teams). Invalidated only by that user's own model changes. **MUST include the `BaseUserProfile` dep** — nickname/avatar are CustomUser `@property`s that write through to `base_profile` (`bp.save()`, never `user.save()`), so a CustomUser-only dep serves stale names.
- `bulk_users` (`POST /users/bulk/`) assembles from `serialize_user_core` → per-user cache hits.
- `_build_users_dict` **preserves its current output shape** (core **+** contextual MMR) by merging cached core with per-request MMR — so the tournament/draft `_users` payload is byte-identical to today. No serializer is converted to pk-only; no structural cache is decoupled; no frontend changes.

**What Scope A deliberately does NOT do** (→ Scope B epic): convert nested users to pk-refs, decouple the tournament/draft structural `@cached_as` from user models, migrate the ~15 MMR-read sites, touch the frontend, or change `_users`/team/bracket/game/list response shapes.

**Tech:** Django + DRF + django-cacheops.

---

## Ground truth (off main `a10e0ef1`)

- `backend/app/serializers.py`: `_serialize_users_with_mmr` (~95) returns users **with** org/league MMR when the tournament has an org (via `OrgUserSerializer`), else `TournamentUserSerializer` (no mmr); `_build_users_dict` (~170) = `{pk: u for u in _serialize_users_with_mmr(user_qs, tournament)}`; `TournamentUserSerializer` (~61) = core fields incl. positions, no mmr; `OrgUserSerializer` (`org/serializers.py:9`) = core + `mmr`/`league_mmr`.
- `backend/app/views_main.py`: `bulk_users` (~1317) — `TournamentUserSerializer(many=True)`, **not cached**, docstring "core fields only — MMR comes from context-specific fetches".
- nickname/avatar are `@property` on CustomUser writing through to `base_profile` (`backend/app/models.py:135-178`); `positions` is a real FK; `PositionsModel.save()` calls `invalidate_obj(user)` (`models.py:43-48`).
- `settings.py` CACHEOPS has `app.customuser`, `user.baseuserprofile`.

---

## Task 1: `serialize_user_core(pk)` per-user cache

**Files:** Create `backend/app/user_cache.py`; Test `backend/app/tests/test_user_core_cache.py`.

- [ ] **Step 1: Failing test** — core fields present, no mmr, and **nickname edit invalidates** (the BaseUserProfile-dep regression guard):

```python
# backend/app/tests/test_user_core_cache.py
from django.test import TransactionTestCase   # on_commit invalidation
from app.models import CustomUser
from app.user_cache import serialize_user_core


class SerializeUserCoreTests(TransactionTestCase):
    def test_core_fields_no_mmr(self):
        u = CustomUser.objects.create(username="core", nickname="Core")
        d = serialize_user_core(u.pk)
        assert d["pk"] == u.pk and d["nickname"] == "Core"
        assert "positions" in d
        assert "mmr" not in d and "league_mmr" not in d

    def test_invalidates_on_nickname_edit(self):
        # nickname writes through to base_profile (bp.save), NOT user.save —
        # the cache MUST depend on BaseUserProfile or this returns stale.
        u = CustomUser.objects.create(username="c2", nickname="Old")
        assert serialize_user_core(u.pk)["nickname"] == "Old"
        u.nickname = "New"   # property setter → bp.save(update_fields=["nickname"])
        assert serialize_user_core(u.pk)["nickname"] == "New"

    def test_invalidates_on_positions_edit(self):
        u = CustomUser.objects.create(username="c3")
        u.positions.carry = 5
        u.positions.save()   # PositionsModel.save() → invalidate_obj(user)
        assert serialize_user_core(u.pk)["positions"]["carry"] == 5
```

- [ ] **Step 2: Run, verify fail** — `just test::run 'python manage.py test app.tests.test_user_core_cache -v 2'`.

- [ ] **Step 3: Implement** — note the **two** dep querysets:

```python
# backend/app/user_cache.py
from cacheops import cached_as
from .models import CustomUser
from .serializers import TournamentUserSerializer  # core fields incl. positions, no mmr
from user.models import BaseUserProfile


def serialize_user_core(pk: int) -> dict:
    """Per-user cached CORE serialization (no MMR — MMR is contextual).
    Invalidated only by this user's own model changes. BaseUserProfile dep is
    required: nickname/avatar are CustomUser @propertys backed by base_profile."""

    @cached_as(
        CustomUser.objects.filter(pk=pk),
        BaseUserProfile.objects.filter(user_id=pk),
        extra=f"user_core:{pk}",
        timeout=60 * 60,
    )
    def _build() -> dict:
        user = (
            CustomUser.objects.select_related("positions")
            .filter(pk=pk)
            .first()
        )
        return TournamentUserSerializer(user).data if user else {}

    return _build()
```
Reuse `TournamentUserSerializer` (the existing core, no-mmr serializer) so the shape is identical to what `bulk_users` already returns. On main, `select_related("positions")` is correct (positions is a real FK).

- [ ] **Step 4: Run green. Step 5: commit** `feat(cache): serialize_user_core per-user cache (BaseUserProfile dep for nickname/avatar)`.

---

## Task 2: `bulk_users` assembles from the per-user cache

**Files:** Modify `backend/app/views_main.py` (`bulk_users` ~1317). Test: extend `test_user_core_cache.py`.

- [ ] **Step 1: Failing test** — `POST /users/bulk/` with `{pks:[...]}` returns one core entry per pk (same shape as today: `TournamentUserSerializer` fields), and a second call after a nickname edit reflects it (per-user invalidation).

```python
class BulkUsersCacheTests(TransactionTestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

    def test_bulk_users_returns_core_and_reflects_edit(self):
        from app.models import CustomUser
        u = CustomUser.objects.create(username="b1", nickname="B1")
        r = self.client.post("/api/users/bulk/", {"pks": [u.pk]}, format="json")
        assert r.status_code == 200 and r.json()[0]["nickname"] == "B1"
        u.nickname = "B1x"
        r2 = self.client.post("/api/users/bulk/", {"pks": [u.pk]}, format="json")
        assert r2.json()[0]["nickname"] == "B1x"
```
(Confirm the `/api/users/bulk/` route + auth — read the existing endpoint's decorators; mirror them in the test client setup.)

- [ ] **Step 2-3:** reimplement the body (keep the existing pk validation + 1-200 bound + decorators):

```python
    from app.user_cache import serialize_user_core
    data = [d for d in (serialize_user_core(pk) for pk in pks) if d]
    return Response(data)
```
Output shape is unchanged (TournamentUserSerializer fields), now per-user cached. `bulk_users` docstring already promises "core fields only" — no shape change.

- [ ] **Step 4: green. Step 5: commit** `perf(users): bulk_users assembles from per-user cache`.

---

## Task 3: `_build_users_dict` core-from-cache + contextual MMR merge (shape-preserving)

**Files:** Modify `backend/app/serializers.py` (`_build_users_dict` ~170, `_serialize_users_with_mmr` ~95). Test: `backend/app/tests/test_build_users_dict.py`.

> **The shape-preservation rule:** today `_build_users_dict` returns `{pk: core+mmr}` for org tournaments. Scope A keeps that EXACT shape — it just sources the **core** half from `serialize_user_core` (cached per-user) and merges the **contextual MMR** half computed per-request. Frontend reads `_users[pk].mmr` unchanged.

- [ ] **Step 1: Failing test** — for an org-scoped tournament, `_build_users_dict(t)` entries contain BOTH core fields (nickname/positions) AND `mmr`/`league_mmr` (shape parity with today); for a non-org tournament, no mmr (parity). And: a nickname edit is reflected (core cached but invalidated), an MMR change is reflected (computed fresh).

- [ ] **Step 2-3: Implement the merge.** Extract an MMR-only helper from `_serialize_users_with_mmr` (a `{pk: {"mmr":…, "league_mmr":…, "orgUserPk":…}}` map for the tournament's org/league context), then:

```python
def _build_users_dict(tournament) -> dict:
    from app.user_cache import serialize_user_core
    seen_pks = _collect_tournament_user_pks(tournament)
    core = {pk: serialize_user_core(pk) for pk in seen_pks}      # cached per-user
    mmr_map = _collect_context_mmr(tournament, seen_pks)         # per-request, contextual
    return {pk: {**core[pk], **mmr_map.get(pk, {})} for pk in seen_pks if core[pk]}
```
`_collect_context_mmr` reuses the existing OrgUser/LeagueUser lookup logic from `_serialize_users_with_mmr` (the org-users queryset + league prefetch), returning only the mmr fields per pk (empty for non-org tournaments). Keep `_serialize_users_with_mmr` itself for any other caller; this just factors its mmr half out. **Verify the merged output keys exactly match today's `_build_users_dict`** (diff a serialized tournament before/after — same JSON).

- [ ] **Step 4: green + shape-parity check.** Run the broad suite: `just test::run 'python manage.py test app -v 2'` — tournament/draft tests must stay green (the `_users` shape is unchanged). **Step 5: commit** `perf(users): _build_users_dict sources core from per-user cache, merges contextual MMR (shape-preserving)`.

---

## Task 4: Verification

- [ ] **Shape parity (the safety gate):** serialize a representative org tournament + a non-org tournament + a draft, assert `_users` JSON is byte-identical to `main` (capture from `git stash`/a main checkout, or assert the key set + a sample entry's keys match `TournamentUserSerializer` fields + mmr). This is what guarantees zero frontend impact.
- [ ] `just test::run 'python manage.py test app -v 2'` — full backend green.
- [ ] `just db::populate::all` smoke — populate works (the per-user cache + shim path).
- [ ] No frontend changes in this PR: `git diff --stat origin/main | grep frontend` → empty (except none expected).
- [ ] Cacheops behavioral (ship `@unittest.skip` + `_redis_reachable` guard, lesson #24): warm a cached tournament, edit a member nickname, refetch, assert fresh name — documents the per-user invalidation even if live-Redis timing is deferred.

---

## Scope B — deferred epic (DO NOT build here) — tracked in **GH issue #276**

Captured so it isn't lost. Full structural-cache decoupling + prebaked-once-everywhere, to be planned/built deliberately as its own epic (**https://github.com/kettleofketchup/DraftForge/issues/276**). Reviewed scope + the corrections the 3-agent panel found:

1. **Convert nested users to pk-refs** everywhere `TeamSerializerForTournament` reaches — tournament-detail, draft, **bracket** (`views/bracket.py:50,300,395,548` + `BracketGameSerializer`), **game** (`GameView`/`GameCreateView`, `GameSerializer`), **TeamView**, **tournament-list** (`TournamentsSerializer.captains`). Each emitting endpoint must attach `_users`.
2. **Decouple structural caches:** drop `CustomUser`/`BaseUserProfile` from the tournament/draft/team `@cached_as`; compose `_users` from the per-user cache; **collect `_users` pks from the cached payload dict, not `get_object()`/ORM** (avoids the warm-path re-query). Align draft struct timeout to 10m (currently 60m).
3. **M2M roster invalidation (required when CustomUser dep is dropped):** add `invalidate_after_commit(tournament, team)` at `org/views.py:248-257` (claim/merge does `users.add/remove`/`members.add/remove` with no invalidation — currently masked by the broad CustomUser dep) + audit `import_prod_tournament.py`, `sync_prod_tournaments.py`.
4. **Extend `_collect_tournament_user_pks`** to walk `draft.draft_rounds` captain/choice + `draft.users_remaining` (or assert the subset invariant in a contract test) — else a round captain/choice outside `tournament.users` renders blank.
5. **MMR-from-cache migration (~15 frontend sites)** reading `member.mmr`/`captain.mmr` off the hydrated tree (`captainTable`, `teamTable`, `TeamModal`, `seeding.ts`, `draftTable`, `ShufflePickOrder`, `DoublePickThreshold`, `AvailablePlayersSection`, `PickOrderSection`, `CompletedTeamDraftView`, `TeamPositionCoverage`, `createTeams`, `TeamPopoverContent`, `teamCard`): rule = **identity from hydrate-tree, MMR from cache** (`orgData`/`leagueData` via `useUserMmr`); backend ships a contextual pk→mmr map; frontend upserts it into `userCacheStore` with org/league context.
6. **Frontend hydration gaps:** per-tournament `_users` + `hydrateTournamentList = raw.map(hydrateTournament)` for `getTournaments`/`getTournamentsBasic`; bracket/game hydration (`MatchNode`, `MatchStatsModal`); wire `fetchUsersBulk` (dead code today) + a hydrate fallback that fetches unresolved pks via `/users/bulk/` and upserts `userCacheStore` (today hydrate renders a blank user on any `_users` miss).
7. **Tests:** contract (every nested user is a pk + `_users` covers all referenced pks), query-count regression (~160→~6), decoupling behavioral.

## Provenance

Design panel (4 agents) + plan-review panel (3 agents) + user scope decision (Scope A now, Scope B as deferred epic). Key corrections folded into Scope A: BaseUserProfile dep on the per-user cache; shape-preserving MMR merge so zero frontend impact.
