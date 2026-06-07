# User Prebake + Decoupled-Cache Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Serialize each user **exactly once** per payload into a flat `_users[]` dict resolved by the frontend entity adapter, and back it with a **per-user cache that is fully decoupled from the tournament/draft structural cache** — so a user edit never evicts a tournament blob and vice versa, and user fetch/serialize is consistently cache-fast.

**Lands BEFORE T2** (game-user-profiles). Built off `main`; `positions` is still the real `CustomUser.positions` column here — T2 later repoints the one shared JOIN. The two parked T2 commits on `feature/profile-t2` rebase onto this after it merges.

**Architecture:**
- `serialize_user_core(pk)` — one `@cached_as(CustomUser, BaseUserProfile, extra="user_core:{pk}")` function returning the context-stable user dict (positions, nickname, avatar, steam_account_id, discordId, avatarUrl, username, teams). Invalidated ONLY by that user's model changes.
- Structural caches (tournament detail, draft, tournament list) `@cached_as(Tournament, Team, Game, Draft, DraftRound)` — **drop `CustomUser`/`BaseUserProfile`** — return structure + pk-refs, NO `_users`.
- Views compose at request time: `data["_users"] = {pk: serialize_user_core(pk) for pk in pks}` (N per-user cache hits).
- **MMR is contextual** (org/league-scoped) — stays on the team/orgUser payload, NEVER in `serialize_user_core` (the global per-user cache). Putting it there poisons the global pk-indexed frontend cache across tournaments (and would corrupt T3 org-overrides).
- Frontend: every nested user level is pk-refs resolved via `hydrate*` + `userCacheStore`; the one un-hydrated path (`getTournaments`/`getTournamentsBasic`) gets wired up.

**Tech:** Django + DRF + django-cacheops; React + Zustand entity adapter + TanStack.

---

## Ground truth (verified off main `a10e0ef1`)

- `backend/app/serializers.py`: `_serialize_users_with_mmr` (~95) — shared helper, builds org_users with `select_related("user","user__positions")` + MMR; `_build_users_dict` (~170) — dedup `{pk: serialized}` via `_collect_tournament_user_pks` (~148); `TournamentSerializerBase`/`TeamSerializerSlim` already pk-only; **inline re-serializers still live:** `TeamSerializerForTournament.get_members/dropin/left/captain/deputy_captain` (~208-221), `TournamentsSerializer.captains = TournamentUserSerializer(many=True)` (~250). `TournamentUserSerializer` (~61) carries positions.
- `backend/app/views_main.py`: `tournament_detail_v2:{pk}` `@cached_as(Tournament, Team, CustomUser, BaseUserProfile, Game, Draft, DraftRound)` (~433) bakes `_users` inside (~456); draft block similar (~640-657); `bulk_users` (~1317) — `POST /users/bulk/`, `TournamentUserSerializer`, **NOT cached**, docstring already says "core fields only — MMR comes from context-specific fetches"; tournament-list views (`getTournaments`/`getTournamentsBasic`) ship inline captains with **no `_users`**.
- `backend/backend/settings.py` CACHEOPS: `app.customuser`, `user.baseuserprofile`, `app.tournament/team/draft/game/draftround`, etc. (1h timeouts).
- Frontend: `frontend/app/lib/hydrateTournament.ts` resolves `_users` → nested objects for tournament-detail + draft + WS; `frontend/app/store/userCacheStore.ts` (`createEntityAdapter`, indexes byDiscordId/bySteamAccountId, `UserEntry.positions`); `frontend/app/components/api/userAPI.tsx:42` calls `/users/bulk/`; `userStore.getTournaments` (~350) / `getTournamentsBasic` (~360) set raw response with NO hydrate.

---

## Task 1: `serialize_user_core(pk)` — the decoupled per-user cache

**Files:**
- Create: `backend/app/user_cache.py` (or add to an existing serializers/cache module)
- Test: `backend/app/tests/test_user_core_cache.py`

- [ ] **Step 1: Failing test** — assert (a) `serialize_user_core(pk)` returns the context-stable fields, (b) editing the user's nickname changes the next call's output (cache invalidation), (c) MMR is NOT in the output.

```python
# backend/app/tests/test_user_core_cache.py
from django.test import TransactionTestCase  # on_commit invalidation
from app.models import CustomUser
from app.user_cache import serialize_user_core


class SerializeUserCoreTests(TransactionTestCase):
    def test_returns_core_fields_no_mmr(self):
        u = CustomUser.objects.create(username="core", nickname="Core")
        data = serialize_user_core(u.pk)
        assert data["pk"] == u.pk
        assert data["nickname"] == "Core"
        assert "positions" in data
        assert "mmr" not in data and "league_mmr" not in data

    def test_invalidates_on_user_edit(self):
        u = CustomUser.objects.create(username="c2", nickname="Old")
        assert serialize_user_core(u.pk)["nickname"] == "Old"
        u.nickname = "New"; u.save()
        assert serialize_user_core(u.pk)["nickname"] == "New"
```

- [ ] **Step 2: Run, verify fail** — `just test::run 'python manage.py test app.tests.test_user_core_cache -v 2'` → ImportError.

- [ ] **Step 3: Implement.** Define a `PrebakedUserSerializer` (context-stable fields only — NO mmr/league_mmr) and the cached function:

```python
# backend/app/user_cache.py
from cacheops import cached_as
from rest_framework import serializers
from .models import CustomUser, PositionsModel
from .serializers import PositionsSerializer


class PrebakedUserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            "pk", "username", "nickname", "avatar", "avatarUrl",
            "discordId", "steam_account_id", "positions",
        )  # context-STABLE only; MMR is contextual, stays on the team payload


def serialize_user_core(pk: int) -> dict:
    """Per-user cached serialization. Invalidated ONLY by this user's model
    changes — fully decoupled from tournament/draft structural caches."""

    @cached_as(
        CustomUser.objects.filter(pk=pk),
        extra=f"user_core:{pk}",
        timeout=60 * 60,
    )
    def _build() -> dict:
        user = (
            CustomUser.objects.select_related("positions")
            .filter(pk=pk)
            .first()
        )
        if user is None:
            return {}
        return PrebakedUserSerializer(user).data

    return _build()
```
Note: on `main`, positions is the real `CustomUser.positions` FK — `select_related("positions")` is correct here. (T2 repoints to `base_profile__dota_user_profile__positions` and adds `BaseUserProfile`/`DotaUserProfile` to the `@cached_as` deps when it rebases.) The `extra=f"user_core:{pk}"` key + the single-user queryset dependency means a `save()` on that user evicts exactly this entry.

- [ ] **Step 4: Run, verify pass.** Step 5: commit `feat(cache): serialize_user_core per-user decoupled cache`.

---

## Task 2: Cache `bulk_users` via `serialize_user_core`

**Files:** Modify `backend/app/views_main.py` (`bulk_users` ~1317). Test: `backend/app/tests/test_user_core_cache.py` (extend).

- [ ] **Step 1: Failing test** — `POST /users/bulk/` with pks returns one entry per pk with core fields; a second call after editing one user reflects the change (per-user invalidation, not whole-endpoint).
- [ ] **Step 2-4:** Reimplement `bulk_users` to assemble from the per-user cache:

```python
def bulk_users(request):
    pks = request.data.get("pks", [])
    if not isinstance(pks, list) or not all(isinstance(p, int) for p in pks):
        return Response({"error": "Provide a list of integer pks"}, status=400)
    if not (1 <= len(pks) <= 200):
        return Response({"error": "Provide 1-200 pks"}, status=400)
    from app.user_cache import serialize_user_core
    data = [serialize_user_core(pk) for pk in pks]
    return Response([d for d in data if d])  # drop missing
```
Each entry is a per-user cache hit → fetching is cache-fast and a single user edit invalidates only that user's entry, not all bulk responses. Commit `perf(users): bulk_users assembles from per-user cache`.

---

## Task 3: Refactor `_build_users_dict` to assemble from the per-user cache

**Files:** Modify `backend/app/serializers.py` (`_build_users_dict` ~170). Test: `backend/app/tests/test_build_users_dict.py`.

- [ ] **Step 1: Failing test** — `_build_users_dict(tournament)` returns `{pk: core_user}` for every tournament+team+captain pk, MMR absent from the per-user entries (MMR now rides the team payload, Task 6).
- [ ] **Step 2-4:** Reimplement:

```python
def _build_users_dict(tournament) -> dict:
    from app.user_cache import serialize_user_core
    seen_pks = _collect_tournament_user_pks(tournament)
    return {pk: serialize_user_core(pk) for pk in seen_pks}
```
`_collect_tournament_user_pks` stays. `_serialize_users_with_mmr` is NOT used for `_users` anymore (it's MMR-bearing) — it remains only for the contextual MMR path (Task 6). Commit `refactor(users): _build_users_dict from per-user cache`.

---

## Task 4: Decouple tournament + draft structural caches from user models; compose `_users` at request time

**Files:** Modify `backend/app/views_main.py` (tournament `retrieve` ~433-460, draft block ~640-657). Test: `backend/app/tests/test_cache_decoupling.py`.

- [ ] **Step 1: Failing test (the headline guarantee).** Warm the tournament detail; edit a member's nickname; assert the tournament STRUCTURAL cache did NOT miss (only the per-user entry did) yet the refetched payload shows the new nickname. And: edit the tournament name; assert the per-user cache stayed warm.

```python
# backend/app/tests/test_cache_decoupling.py — TransactionTestCase, _redis_reachable skip-guard
# (mirror backend/user/tests/test_cacheops_integration.py's skip pattern)
# 1. GET /api/tournament/<pk>/ (warm)
# 2. PATCH a member nickname via the user
# 3. GET again → nickname updated AND assert structural cache key still present
#    (assert via a cache-miss log counter or by checking the structural fn wasn't re-run)
```
Because asserting "structural fn didn't re-run" is awkward, the pragmatic assertion: after a USER edit, the refetched `_users[pk].nickname` is fresh; after a TOURNAMENT edit, a user whose entry was cached returns from cache (timing/marker). Ship this test `@unittest.skip`-guarded like T1's cacheops integration (lesson #24) if live-eviction timing is flaky; keep the structural-deps assertion (Step 3) as the hard gate.

- [ ] **Step 2-4: Drop user models from the structural `@cached_as`, compose `_users` outside it:**

```python
@cached_as(
    Tournament.objects.filter(pk=pk), Team, Game, Draft, DraftRound,
    extra=f"tournament_struct:{pk}", timeout=60 * 10,
)   # NOTE: CustomUser + BaseUserProfile REMOVED — user data is composed below
def get_structure():
    instance = self.get_object()
    return self.get_serializer(instance).data   # pk-refs only, NO _users

data = get_structure()
data["_users"] = _build_users_dict(self.get_object())   # per-user cache hits, outside the structural cache
return Response(data)
```
Same shape for the draft block. The structural payload must NOT embed `_users` inside the cached fn (or it recouples). Apply the same to any other structural `@cached_as` that currently lists `CustomUser`/`BaseUserProfile` AND composes `_users`. Commit `perf(cache): decouple tournament/draft structural cache from user cache`.

> **cacheops guardrail shift:** after this, structural blocks no longer list `CustomUser`. The user-model deps live in `serialize_user_core` only. Update any grep guardrail accordingly (and this is what makes T2's "add DotaUserProfile to every @cached_as(CustomUser)" collapse to a SINGLE site — `serialize_user_core`).

---

## Task 5: Convert remaining inline re-serializers to pk-only

**Files:** Modify `backend/app/serializers.py` — `TeamSerializerForTournament` (~200-235), `TournamentsSerializer.captains` (~250), and the perf-flagged `GameSerializer`/`BracketGameSerializer`/`DraftRoundSerializer`/`TeamView` surfaces. Template: `TeamSerializerSlim` (~238, already pk-only).

- [ ] Convert `get_members/get_dropin_members/get_left_members` → `UserPkField(many=True)`, `get_captain/get_deputy_captain` → `UserPkField()`. Make `TeamSerializerForTournament` itself pk-only (or have callers use `TeamSerializerSlim`). `TournamentsSerializer.captains` → `UserPkField(many=True)`.
- [ ] Every endpoint emitting these MUST attach `_users` (Task 4 pattern). Audit: `rg -n "_serialize_users_with_mmr|TournamentUserSerializer\(" backend/app` — each remaining full-user inline site either moves to pk + `_users` or is justified (e.g. `bulk_users` IS the user source).
- [ ] Commit `refactor(serializers): nested user refs pk-only across tournament/team/game/draft`.

---

## Task 6: Contextual MMR stays on the team/orgUser payload

**Files:** Modify `backend/app/serializers.py` (team serializers), `backend/org/serializers.py` if needed. Test: `backend/app/tests/test_mmr_contextual.py`.

- [ ] MMR/league_mmr must remain reachable per-tournament. Since members are now pk-refs, expose MMR as a pk→mmr map on the team or tournament payload (e.g. `team.member_mmr: {pk: mmr}`) OR keep `OrgUserSerializer` for the explicit org/league roster endpoints (which legitimately ship MMR and are separate from `_users`). Do NOT add mmr to `serialize_user_core`.
- [ ] Test: a user on two tournaments with different org MMRs serializes each tournament's MMR correctly, while `serialize_user_core` returns no MMR. Commit `feat(serializers): contextual MMR map separate from global user cache`.

---

## Task 7: WS broadcast `_users` parity

**Files:** `backend/app/consumers.py` (+ any broadcast emitting slim teams). Test: existing WS tests.

- [ ] Audit every broadcast that emits pk-ref teams/users — each must attach `_users` (via `_build_users_dict`) or the client can't resolve them. `rg -n "_users|_build_users_dict|broadcast|group_send" backend/app/consumers.py`. Commit `fix(ws): attach _users to slim broadcasts`.

---

## Task 8: Frontend — hydrate the tournament-list path + one source of truth

**Files:** `frontend/app/store/userStore.ts` (`getTournaments` ~350, `getTournamentsBasic` ~360), `frontend/app/lib/hydrateTournament.ts`, the tournament-list captain consumers.

- [ ] Route `getTournaments`/`getTournamentsBasic` responses through `hydrateTournament` (or a list variant) so the now-pk-only `captains` resolve. The at-risk consumers (`captainTable.tsx`, `UpdateCaptainButton.tsx`, `createTeamFromCaptainHook.tsx`, `draftOrder.tsx`) then read resolved objects.
- [ ] Ensure `bulk_users` results populate `userCacheStore` so unknown pks resolve; confirm `hydrateTournament` covers every nested level (members/captain/deputy/dropin/left/users_remaining/draft_rounds) — it already does for detail/draft; add the list path.
- [ ] Pick ONE source of truth for nested reads (keep the hydrate-tree pattern consistently; contextual MMR read from the per-tournament tree, never the global cache). Commit `feat(frontend): hydrate tournament-list path + consistent user resolution`.

---

## Task 9: Tests + verification

- [ ] **Contract test** (`backend/app/tests/test_users_dict_contract.py`): for tournament-detail, draft, and tournament-list responses, assert every nested user reference is an int pk AND `_users` is present and covers all referenced pks.
- [ ] **Query-count regression** (`assertNumQueries`): tournament-detail cold render issues O(1) `_build_users_dict` user query path, not O(teams×members). Lock in the win (panel estimate ~160→~6).
- [ ] **Decoupling behavioral** (Task 4 test) — shipped skip-guarded if live-Redis timing is flaky; the structural-deps assertion is the hard gate.
- [ ] **Playwright** (`frontend/tests/playwright/e2e/`): tournament list + detail + draft render captains/members correctly post-conversion (no blank names). Reuse existing edit-user/tournament specs.
- [ ] **Final:** `just test::run 'python manage.py test app -v 2'` green; `cd frontend && npx tsc --noEmit` no new errors; `npx vitest run` green; `just test::pw::spec tournament` + `draft` green; `just db::populate::all` smoke. Commit per task.

---

## Sequencing into T2

After this PR merges: rebase `feature/profile-t2` onto the new `main`. T2's Task 9 then only has to (a) repoint `serialize_user_core`'s `select_related("positions")` → `base_profile__dota_user_profile__positions` and (b) add `BaseUserProfile, DotaUserProfile` to `serialize_user_core`'s `@cached_as` deps — a SINGLE site, not 14. The T2 cacheops guardrail simplifies to "the per-user cache lists the user-model deps."

## Spec / design provenance

Design panel (4 agents) + user directives: prebaked-once + pk-refs (unanimous), decoupled per-user cache separate from tournament caching (user requirement), global-vs-contextual MMR split (DRF architect), tournament-list is the one un-hydrated path (frontend), ~160→~6 query win (perf), separate-PR-first sequencing (3/4 + user).
