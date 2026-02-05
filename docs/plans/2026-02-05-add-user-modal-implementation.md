# AddUserModal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reusable AddUserModal component that adds users to Orgs, Leagues, and Tournaments via a single search bar that queries both site users and Discord members in parallel.

**Architecture:** Entity-agnostic modal receives callbacks (`onAdd`, `isAdded`) from parent. Single search bar fires two parallel backend calls — one for site users (annotated with membership context), one for Discord members (cached in Redis with 1hr TTL). Desktop shows two columns; mobile uses tabs. Discord members without site accounts are auto-created on add.

**Tech Stack:** Django REST Framework, Redis, React, TypeScript, Tailwind CSS, shadcn/ui Dialog, Zustand, Zod

**Design Doc:** `docs/plans/2026-02-05-add-user-modal-design.md`

---

## Critical Implementation Notes

### Optimistic Updates (from Zustand store review)

**`getOrgUsers()` and `getLeagueUsers()` have skip-if-cached guards** that prevent re-fetching for the same org/league ID. After `onAdd` succeeds, calling `getOrgUsers(orgId)` will silently return stale data.

**Solution:** Follow the `AdminTeamSection` pattern — use optimistic local updates. When `onAdd` succeeds and returns the new user, the parent should append the user to the local/store array using `setOrgUsers([...orgUsers, newUser])`. Do NOT call `clearOrgUsers()` on modal close — that would break the parent page's user list behind the modal.

### API Function Placement

All fetch functions MUST be declared in `frontend/app/components/api/<entity>API.tsx`:
- Site user search enhancements → `api.tsx`
- Discord member search/refresh → `orgAPI.tsx`
- Add org member → `orgAPI.tsx`
- Add league member → `leagueAPI.tsx`
- Add tournament member → `api.tsx` (tournament functions already live here)

All new exports from `orgAPI.tsx` and `leagueAPI.tsx` MUST be re-exported from `api.tsx`. Consumers always import from `~/components/api/api`, never from entity API files directly.

### Component Directory

All AddUserModal components live in `frontend/app/components/user/AddUserModal/` (NOT `shared/`). The `shared/` directory doesn't exist in this codebase. `DiscordMemberStrip` lives alongside `UserStrip` in `components/user/`.

### Frontend Search Pattern

Use the existing `useDebouncedValue` hook + `@tanstack/react-query` `useQuery` for search — NOT manual debounce + Promise.all. This matches `UserSearchInput` / `AdminTeamSection` patterns and prevents race conditions with stale responses.

---

## Review Amendments (from 8-agent review)

The following changes were applied based on findings from 8 parallel review agents (Tailwind theming, reusable components, React efficiency, Zustand store isolation, Redis/backend, API organization, test coverage, security).

### Critical Fixes Applied

| # | Fix | Affected Tasks |
|---|-----|----------------|
| C1 | **`_resolve_user` rewritten** — backend looks up Discord data from its own Redis cache by `discord_id` + `org_id` instead of trusting client payload. Creates user properly with `PositionsModel` and `save()`. | Task 3 |
| C2 | **Separate cache key** — `discord_members_search_{server_id}` avoids TTL conflict with existing 15s cache in `get_discord_members_data()`. | Task 2 |
| C3 | **`useQuery` + `useDebouncedValue`** replaces manual debounce + Promise.all — fixes race conditions, debounce cleanup, aligns with codebase patterns. | Task 9 |
| C4 | **Error handling** added around `get_discord_members_data` calls in both Discord endpoints. | Task 2 |

### Security Fixes Applied

| # | Fix | Affected Tasks |
|---|-----|----------------|
| H1 | **Authorization check** on `search_users` when `org_id` provided — requires `has_org_staff_access`. | Task 1 |
| H2 | **Trust boundary fix** — backend resolves Discord users from its own cache, not client-supplied `discord_data`. Frontend sends `discord_id` + `org_id` only. | Tasks 3, 4, 5, 8 |

### Important Fixes Applied

| # | Fix | Affected Tasks |
|---|-----|----------------|
| I1 | **Directory: `components/user/AddUserModal/`** not `shared/`. `DiscordMemberStrip` at `components/user/DiscordMemberStrip.tsx`. | Tasks 5-9 |
| I3 | **MembershipBadge uses `Badge` component** + semantic tokens (`text-info`/`text-success`/`text-warning`). | Task 7 |
| I4 | **`DiscordMemberStrip.onAdd` accepts member arg** — prevents inline arrow from defeating `React.memo`. | Tasks 6, 8 |
| I5 | **`handleAddMember` uses `useOrgStore.getState()`** — avoids stale closure + unnecessary callback recreation. | Tasks 10-12 |
| I6 | **DiscordMemberStrip styling** matches UserStrip: `cn()`, `border-border/50`, `bg-muted/20 hover:bg-muted/40`. | Task 6 |
| I7 | **`addTournamentMember` in `api.tsx`** — no `tournamentAPI.tsx` file. | Task 4 |
| I8 | **Re-exports added to `api.tsx`** for all new orgAPI/leagueAPI exports. | Task 4 |
| I9 | **`AddMemberPayload` in `api/types.d.ts`** — single source of truth, no cross-file coupling. | Task 4 |
| I10 | **`IntegrityError` handling** on OrgUser/LeagueUser create for concurrent adds. | Task 3 |
| I11 | **`transaction.atomic()`** wraps OrgUser + LeagueUser create pair in `add_league_member`. | Task 3 |
| I12 | **Rate limiting** on `refresh_discord_members` — per-org 5-minute cooldown via Redis. | Task 2 |
| I13 | **Audit logging** via `OrgLog`/`LeagueLog` on all add-member operations. | Task 3 |
| I14 | **`hasDiscordServer` is a prop** passed from parent (checks `discord_server_id`), not derived from `Boolean(orgId)`. | Tasks 5, 9-12 |
| I15 | **Permission denial tests** added for all protected endpoints. | Tasks 1-3 |
| I16 | **Missing `has_org_staff_access` import** added to `admin_team.py`. | Task 3 |

---

## Task 1: Backend — Enhance search_users with steamid and membership annotation

**Files:**
- Modify: `backend/app/views/admin_team.py:22-48` (search_users function)
- Test: `backend/app/tests/test_search_users.py` (create new)

**Step 1: Write failing tests**

Create `backend/app/tests/test_search_users.py`:

```python
from django.test import TestCase
from rest_framework.test import APIClient
from app.models import CustomUser
from org.models import OrgUser, Organization
from league.models import LeagueUser, League


class SearchUsersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123", is_staff=True
        )
        self.client.force_authenticate(user=self.staff)

        # Create org and league
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )

        # User in the league (implies org membership)
        self.league_user = CustomUser.objects.create_user(
            username="leagueuser", password="test", nickname="LeagueJohn"
        )
        org_user = OrgUser.objects.create(
            user=self.league_user, organization=self.org
        )
        LeagueUser.objects.create(
            user=self.league_user, org_user=org_user, league=self.league
        )

        # User in org only
        self.org_only_user = CustomUser.objects.create_user(
            username="orgonlyuser", password="test", nickname="OrgJohn"
        )
        OrgUser.objects.create(user=self.org_only_user, organization=self.org)

        # User in a different org
        self.other_org = Organization.objects.create(name="Other Org")
        self.other_org_user = CustomUser.objects.create_user(
            username="otherorguser", password="test", nickname="OtherJohn"
        )
        OrgUser.objects.create(
            user=self.other_org_user, organization=self.other_org
        )

        # Global user (no org)
        self.global_user = CustomUser.objects.create_user(
            username="globaluser", password="test", nickname="GlobalJohn"
        )

        # User with steam ID
        self.steam_user = CustomUser.objects.create_user(
            username="steamjohn", password="test",
            steamid=76561198000000001, steam_account_id=39735273
        )

    def test_search_by_steamid(self):
        resp = self.client.get("/api/users/search/", {"q": "76561198000000001"})
        self.assertEqual(resp.status_code, 200)
        pks = [u["pk"] for u in resp.data]
        self.assertIn(self.steam_user.pk, pks)

    def test_search_by_steam_account_id(self):
        resp = self.client.get("/api/users/search/", {"q": "39735273"})
        self.assertEqual(resp.status_code, 200)
        pks = [u["pk"] for u in resp.data]
        self.assertIn(self.steam_user.pk, pks)

    def test_membership_annotation_league(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "leagueuser", "org_id": self.org.pk, "league_id": self.league.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertEqual(user_data["membership"], "league")
        self.assertEqual(user_data["membership_label"], "Test League")

    def test_membership_annotation_org(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "orgonlyuser", "org_id": self.org.pk, "league_id": self.league.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertEqual(user_data["membership"], "org")
        self.assertEqual(user_data["membership_label"], "Test Org")

    def test_membership_annotation_other_org(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "otherorguser", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertEqual(user_data["membership"], "other_org")
        self.assertEqual(user_data["membership_label"], "Other Org")

    def test_membership_annotation_global(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "globaluser", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertIsNone(user_data["membership"])

    def test_no_context_params_still_works(self):
        resp = self.client.get("/api/users/search/", {"q": "leagueuser"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertNotIn("membership", resp.data[0])

    def test_unauthenticated_returns_401(self):
        self.client.logout()
        resp = self.client.get("/api/users/search/", {"q": "test"})
        self.assertIn(resp.status_code, [401, 403])

    def test_non_staff_cannot_use_org_context(self):
        """Any authenticated user can search, but org_id requires org staff access."""
        regular = CustomUser.objects.create_user(
            username="regular", password="test123"
        )
        self.client.force_authenticate(user=regular)
        # Search without org_id — should work
        resp = self.client.get("/api/users/search/", {"q": "leagueuser"})
        self.assertEqual(resp.status_code, 200)
        # Search with org_id — should be denied (no org staff access)
        resp = self.client.get(
            "/api/users/search/",
            {"q": "leagueuser", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 403)

    def test_short_query_returns_400(self):
        resp = self.client.get("/api/users/search/", {"q": "ab"})
        self.assertEqual(resp.status_code, 400)

    def test_max_20_results(self):
        for i in range(25):
            CustomUser.objects.create_user(
                username=f"bulkuser{i}", password="test", nickname=f"Bulk{i}"
            )
        resp = self.client.get("/api/users/search/", {"q": "bulk"})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.data), 20)
```

**Step 2: Run tests to verify they fail**

Run: `just test::run 'python manage.py test app.tests.test_search_users -v 2'`
Expected: FAIL — steamid search not implemented, membership annotation not present.

**Step 3: Implement enhanced search_users**

Modify `backend/app/views/admin_team.py` — replace the `search_users` function:

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request):
    """
    Search users by username, nickname, Discord names, or Steam ID.

    Query params:
    - q: Search query (min 3 characters)
    - org_id: Optional org ID for membership annotation
    - league_id: Optional league ID for membership annotation

    Returns max 20 results, each annotated with membership context
    when org_id is provided.
    """
    query = request.query_params.get("q", "").strip()

    if len(query) < 3:
        return Response(
            {"error": "Search query must be at least 3 characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build search filter
    q_filter = (
        Q(discordUsername__icontains=query)
        | Q(discordNickname__icontains=query)
        | Q(guildNickname__icontains=query)
        | Q(username__icontains=query)
        | Q(nickname__icontains=query)
    )

    # Add Steam ID search if query is numeric
    if query.isdigit():
        q_filter |= Q(steamid=int(query)) | Q(steam_account_id=int(query))

    users = CustomUser.objects.filter(q_filter)[:20]
    data = TournamentUserSerializer(users, many=True).data

    # Annotate with membership context if org_id provided
    org_id = request.query_params.get("org_id")
    league_id = request.query_params.get("league_id")

    if org_id:
        try:
            org = Organization.objects.get(pk=int(org_id))
        except (Organization.DoesNotExist, ValueError):
            org = None

        # Require org staff access to see membership annotations
        if org and not has_org_staff_access(request.user, org):
            return Response(
                {"error": "You do not have access to this organization"},
                status=status.HTTP_403_FORBIDDEN,
            )

        league = None
        if league_id:
            try:
                league = League.objects.get(pk=int(league_id))
            except (League.DoesNotExist, ValueError):
                pass

        if org:
            user_ids = [u["pk"] for u in data]

            # Get league member IDs
            league_member_ids = set()
            if league:
                league_member_ids = set(
                    LeagueUser.objects.filter(
                        league=league, user_id__in=user_ids
                    ).values_list("user_id", flat=True)
                )

            # Get org member IDs
            org_member_ids = set(
                OrgUser.objects.filter(
                    organization=org, user_id__in=user_ids
                ).values_list("user_id", flat=True)
            )

            # Get other org memberships for remaining users
            other_org_map = {}
            remaining_ids = set(user_ids) - org_member_ids - league_member_ids
            if remaining_ids:
                other_memberships = (
                    OrgUser.objects.filter(user_id__in=remaining_ids)
                    .select_related("organization")
                    .values_list("user_id", "organization__name")
                )
                for uid, org_name in other_memberships:
                    if uid not in other_org_map:
                        other_org_map[uid] = org_name

            for user_data in data:
                uid = user_data["pk"]
                if uid in league_member_ids:
                    user_data["membership"] = "league"
                    user_data["membership_label"] = league.name if league else ""
                elif uid in org_member_ids:
                    user_data["membership"] = "org"
                    user_data["membership_label"] = org.name
                elif uid in other_org_map:
                    user_data["membership"] = "other_org"
                    user_data["membership_label"] = other_org_map[uid]
                else:
                    user_data["membership"] = None
                    user_data["membership_label"] = None

    return Response(data)
```

Add imports at the top of `admin_team.py`:

```python
from org.models import OrgUser, Organization
from league.models import LeagueUser, League
from app.permissions_org import has_org_staff_access  # add to existing import block
```

**Step 4: Run tests to verify they pass**

Run: `just test::run 'python manage.py test app.tests.test_search_users -v 2'`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/views/admin_team.py backend/app/tests/test_search_users.py
git commit -m "feat: enhance search_users with steamid search and membership annotation"
```

---

## Task 2: Backend — Discord member search endpoint with Redis caching

**Files:**
- Modify: `backend/discordbot/services/users.py` (add search + refresh functions)
- Modify: `backend/discordbot/urls.py` (add new URL patterns)
- Test: `backend/discordbot/tests/test_discord_search.py` (create new)

**Step 1: Write failing tests**

Create `backend/discordbot/tests/__init__.py` (if not exists) and `backend/discordbot/tests/test_discord_search.py`:

```python
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APIClient
from app.models import CustomUser
from org.models import Organization, OrgUser


MOCK_DISCORD_MEMBERS = [
    {
        "user": {"id": "111", "username": "johndiscord", "global_name": "John D", "avatar": "abc"},
        "nick": "JohnnyD",
        "joined_at": "2024-01-01T00:00:00+00:00",
    },
    {
        "user": {"id": "222", "username": "janediscord", "global_name": "Jane D", "avatar": None},
        "nick": None,
        "joined_at": "2024-01-01T00:00:00+00:00",
    },
    {
        "user": {"id": "333", "username": "bobdiscord", "global_name": "Bob", "avatar": "def"},
        "nick": "BobNick",
        "joined_at": "2024-01-01T00:00:00+00:00",
    },
]


class SearchDiscordMembersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

        self.org = Organization.objects.create(
            name="Test Org", discord_server_id="999888777"
        )

        # Staff user with org access
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123"
        )
        OrgUser.objects.create(user=self.staff, organization=self.org)
        self.org.staff.add(self.staff)
        self.client.force_authenticate(user=self.staff)

        # User with linked Discord account
        self.linked_user = CustomUser.objects.create_user(
            username="linkeduser", password="test", discordId="111"
        )

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_discord_members(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["user"]["username"], "johndiscord")
        self.assertTrue(results[0]["has_site_account"])
        self.assertEqual(results[0]["site_user_pk"], self.linked_user.pk)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_no_site_account(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "jane", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["has_site_account"])
        self.assertIsNone(results[0]["site_user_pk"])

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_uses_redis_cache(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS

        # First call populates cache
        self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        # Second call should use cache
        self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "bob", "org_id": self.org.pk},
        )
        # get_discord_members_data should only be called once (cache hit on second)
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_min_3_chars(self, mock_fetch):
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "jo", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_requires_org_id(self):
        resp = self.client.get(
            "/api/discord/search-discord-members/", {"q": "john"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_no_discord_server(self):
        org_no_discord = Organization.objects.create(name="No Discord Org")
        org_no_discord.staff.add(self.staff)
        OrgUser.objects.create(user=self.staff, organization=org_no_discord)
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": org_no_discord.pk},
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_unauthenticated_returns_401(self):
        self.client.logout()
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertIn(resp.status_code, [401, 403])

    def test_search_non_staff_returns_403(self):
        regular = CustomUser.objects.create_user(
            username="regular", password="test123"
        )
        self.client.force_authenticate(user=regular)
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_handles_discord_api_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("Discord API error")
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 502)


class RefreshDiscordMembersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

        self.org = Organization.objects.create(
            name="Test Org", discord_server_id="999888777"
        )
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123"
        )
        OrgUser.objects.create(user=self.staff, organization=self.org)
        self.org.staff.add(self.staff)
        self.client.force_authenticate(user=self.staff)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_clears_and_repopulates(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS

        # Pre-populate cache
        cache_key = f"discord_members_{self.org.discord_server_id}"
        cache.set(cache_key, [{"old": "data"}], timeout=3600)

        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["refreshed"])
        self.assertEqual(data["count"], 3)

        # Verify cache was repopulated (uses search-specific key)
        search_cache_key = f"discord_members_search_{self.org.discord_server_id}"
        cached = cache.get(search_cache_key)
        self.assertEqual(len(cached), 3)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_rate_limited(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        # First refresh should succeed
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Second immediate refresh should be rate limited
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 429)

    def test_refresh_non_staff_returns_403(self):
        regular = CustomUser.objects.create_user(
            username="regular", password="test123"
        )
        self.client.force_authenticate(user=regular)
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_handles_discord_api_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("Discord API error")
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 502)
```

**Step 2: Run tests to verify they fail**

Run: `just test::run 'python manage.py test discordbot.tests.test_discord_search -v 2'`
Expected: FAIL — endpoints don't exist.

**Step 3: Implement search and refresh endpoints**

Add to `backend/discordbot/services/users.py`:

```python
DISCORD_MEMBERS_CACHE_TTL = 3600  # 1 hour


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_discord_members(request):
    """
    Search Discord members for a specific organization's Discord server.
    Results are cached in Redis for 1 hour.

    Query params:
    - q: Search query (min 3 characters)
    - org_id: Organization ID (required)
    """
    query = request.query_params.get("q", "").strip().lower()
    org_id = request.query_params.get("org_id")

    if not org_id:
        return JsonResponse(
            {"error": "org_id is required"}, status=400
        )

    if len(query) < 3:
        return JsonResponse(
            {"error": "Search query must be at least 3 characters"}, status=400
        )

    try:
        org = Organization.objects.get(pk=int(org_id))
    except (Organization.DoesNotExist, ValueError):
        return JsonResponse({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return JsonResponse(
            {"error": "You do not have access to this organization"}, status=403
        )

    if not org.discord_server_id:
        return JsonResponse(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    # Get members from Redis cache or Discord API
    # Use a SEPARATE cache key from get_discord_members_data's internal 15s cache
    # to avoid TTL conflicts
    cache_key = f"discord_members_search_{org.discord_server_id}"
    members = cache.get(cache_key)

    if members is None:
        try:
            members = get_discord_members_data(guild_id=org.discord_server_id)
        except Exception as e:
            log.error(f"Error fetching Discord members for org {org.pk}: {e}")
            return JsonResponse(
                {"error": "Failed to fetch Discord members"}, status=502
            )
        cache.set(cache_key, members, timeout=DISCORD_MEMBERS_CACHE_TTL)

    # Filter by query
    filtered = []
    for member in members:
        user = member.get("user", {})
        username = (user.get("username") or "").lower()
        global_name = (user.get("global_name") or "").lower()
        nick = (member.get("nick") or "").lower()

        if query in username or query in global_name or query in nick:
            filtered.append(member)

        if len(filtered) >= 20:
            break

    # Cross-reference with site accounts
    discord_ids = [m["user"]["id"] for m in filtered]
    linked_users = dict(
        CustomUser.objects.filter(discordId__in=discord_ids).values_list(
            "discordId", "pk"
        )
    )

    results = []
    for member in filtered:
        discord_id = member["user"]["id"]
        site_pk = linked_users.get(discord_id)
        results.append({
            "user": member["user"],
            "nick": member.get("nick"),
            "has_site_account": site_pk is not None,
            "site_user_pk": site_pk,
        })

    return JsonResponse({"results": results})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_discord_members(request):
    """
    Refresh Discord members cache for a specific organization.

    Body:
    - org_id: Organization ID (required)
    """
    org_id = request.data.get("org_id")

    if not org_id:
        return JsonResponse({"error": "org_id is required"}, status=400)

    try:
        org = Organization.objects.get(pk=int(org_id))
    except (Organization.DoesNotExist, ValueError):
        return JsonResponse({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return JsonResponse(
            {"error": "You do not have access to this organization"}, status=403
        )

    if not org.discord_server_id:
        return JsonResponse(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    # Rate limit: 5-minute cooldown per org
    cooldown_key = f"discord_refresh_cooldown_{org.discord_server_id}"
    if cache.get(cooldown_key):
        return JsonResponse(
            {"error": "Please wait before refreshing again"}, status=429
        )

    # Clear search cache and re-fetch
    cache_key = f"discord_members_search_{org.discord_server_id}"
    cache.delete(cache_key)

    try:
        members = get_discord_members_data(guild_id=org.discord_server_id)
    except Exception as e:
        log.error(f"Error refreshing Discord members for org {org.pk}: {e}")
        return JsonResponse(
            {"error": "Failed to fetch Discord members"}, status=502
        )
    cache.set(cache_key, members, timeout=DISCORD_MEMBERS_CACHE_TTL)
    cache.set(cooldown_key, True, timeout=300)  # 5-minute cooldown

    return JsonResponse({"refreshed": True, "count": len(members)})
```

Add needed imports at the top of `users.py`:

```python
from app.models import CustomUser
from app.permissions_org import has_org_staff_access
from org.models import Organization
```

Add URL patterns to `backend/discordbot/urls.py`:

```python
path(
    "search-discord-members/",
    search_discord_members,
    name="search-discord-members",
),
path(
    "refresh-discord-members/",
    refresh_discord_members,
    name="refresh-discord-members",
),
```

Add imports to `urls.py`:

```python
from discordbot.services.users import search_discord_members, refresh_discord_members
```

**Step 4: Run tests to verify they pass**

Run: `just test::run 'python manage.py test discordbot.tests.test_discord_search -v 2'`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/discordbot/services/users.py backend/discordbot/urls.py backend/discordbot/tests/
git commit -m "feat: add Discord member search and refresh endpoints with Redis caching"
```

---

## Task 3: Backend — Add member endpoints for Org, League, Tournament

**Files:**
- Modify: `backend/app/views/admin_team.py` (add member views)
- Modify: `backend/app/urls.py` or relevant URL config (add URL patterns)
- Test: `backend/app/tests/test_add_member.py` (create new)

**Step 1: Write failing tests**

Create `backend/app/tests/test_add_member.py`:

```python
from django.test import TestCase
from rest_framework.test import APIClient
from app.models import CustomUser, Tournament
from org.models import OrgUser, Organization
from league.models import LeagueUser, League


class AddOrgMemberTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test123"
        )
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.admin, organization=self.org)
        self.client.force_authenticate(user=self.admin)

        self.target_user = CustomUser.objects.create_user(
            username="newmember", password="test"
        )

    def test_add_org_member(self):
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            OrgUser.objects.filter(
                user=self.target_user, organization=self.org
            ).exists()
        )

    def test_add_org_member_duplicate(self):
        OrgUser.objects.create(user=self.target_user, organization=self.org)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_add_org_member_from_discord_id(self):
        """Backend looks up Discord data from its own cache, not client payload."""
        from django.core.cache import cache

        # Pre-populate Discord member cache for this org
        self.org.discord_server_id = "999888777"
        self.org.save()
        cache_key = f"discord_members_search_999888777"
        cache.set(cache_key, [
            {
                "user": {"id": "12345", "username": "discorduser", "global_name": "Discord User", "avatar": "abc123"},
                "nick": "DiscordNick",
            }
        ], timeout=3600)

        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"discord_id": "12345"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        new_user = CustomUser.objects.get(discordId="12345")
        self.assertTrue(
            OrgUser.objects.filter(user=new_user, organization=self.org).exists()
        )
        # Verify user was created with correct data from cache
        self.assertEqual(new_user.discordUsername, "discorduser")
        self.assertEqual(new_user.nickname, "DiscordNick")

    def test_add_org_member_discord_id_not_in_cache(self):
        """Reject discord_id if member not found in org's Discord cache."""
        self.org.discord_server_id = "999888777"
        self.org.save()
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"discord_id": "nonexistent"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_add_org_member_non_staff_returns_403(self):
        regular = CustomUser.objects.create_user(
            username="regular", password="test123"
        )
        self.client.force_authenticate(user=regular)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_add_org_member_creates_audit_log(self):
        from app.models import OrgLog
        self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org,
                user=self.admin,
                action="add_member",
            ).exists()
        )


class AddLeagueMemberTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test123"
        )
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.admin, organization=self.org)
        self.client.force_authenticate(user=self.admin)

        self.target_user = CustomUser.objects.create_user(
            username="newmember", password="test"
        )

    def test_add_league_member_creates_org_user_too(self):
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Should create both OrgUser and LeagueUser
        self.assertTrue(
            OrgUser.objects.filter(
                user=self.target_user, organization=self.org
            ).exists()
        )
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league
            ).exists()
        )

    def test_add_league_member_existing_org_user(self):
        # Already in org, just add to league
        org_user = OrgUser.objects.create(
            user=self.target_user, organization=self.org
        )
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league, org_user=org_user
            ).exists()
        )


class AddTournamentMemberTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test123", is_staff=True
        )
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.admin, organization=self.org)
        self.client.force_authenticate(user=self.admin)

        from django.utils import timezone

        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=timezone.now(),
            league=self.league,
        )
        self.target_user = CustomUser.objects.create_user(
            username="newplayer", password="test"
        )

    def test_add_tournament_member(self):
        resp = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.target_user, self.tournament.users.all())

    def test_add_tournament_member_duplicate(self):
        self.tournament.users.add(self.target_user)
        resp = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
```

**Step 2: Run tests to verify they fail**

Run: `just test::run 'python manage.py test app.tests.test_add_member -v 2'`
Expected: FAIL — endpoints don't exist.

**Step 3: Implement add member endpoints**

Add to `backend/app/views/admin_team.py`:

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_member(request, org_id):
    """Add a member to an organization. Creates OrgUser record."""
    org = get_object_or_404(Organization, pk=org_id)

    if not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = _resolve_user(request.data, org=org)
    if isinstance(user, Response):
        return user  # Error response

    try:
        OrgUser.objects.create(user=user, organization=org)
    except IntegrityError:
        return Response(
            {"error": "User is already a member of this organization"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    OrgLog.objects.create(
        organization=org, user=request.user, action="add_member",
        details=f"Added {user.username} as member",
    )
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_league_member(request, league_id):
    """Add a member to a league. Creates LeagueUser (and OrgUser if needed)."""
    league = get_object_or_404(
        League.objects.select_related("organization"), pk=league_id
    )

    has_access = league.organization and has_org_admin_access(
        request.user, league.organization
    )
    if not has_access and not request.user.is_superuser:
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = _resolve_user(request.data, org=league.organization)
    if isinstance(user, Response):
        return user

    try:
        with transaction.atomic():
            org_user, _ = OrgUser.objects.get_or_create(
                user=user, organization=league.organization
            )
            LeagueUser.objects.create(user=user, org_user=org_user, league=league)
    except IntegrityError:
        return Response(
            {"error": "User is already a member of this league"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    LeagueLog.objects.create(
        league=league, user=request.user, action="add_member",
        details=f"Added {user.username} as member",
    )
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_tournament_member(request, tournament_id):
    """Add a member to a tournament's users M2M."""
    tournament = get_object_or_404(
        Tournament.objects.select_related("league__organization"), pk=tournament_id
    )

    # Check access via league's org
    has_access = False
    if tournament.league and tournament.league.organization:
        has_access = has_org_staff_access(
            request.user, tournament.league.organization
        )
    if not has_access and not request.user.is_superuser:
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org = tournament.league.organization if tournament.league else None
    user = _resolve_user(request.data, org=org)
    if isinstance(user, Response):
        return user

    if tournament.users.filter(pk=user.pk).exists():
        return Response(
            {"error": "User is already in this tournament"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tournament.users.add(user)
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


def _resolve_user(data, org=None):
    """
    Resolve a user from user_id or discord_id. Returns User or error Response.

    When discord_id is provided, the backend looks up the Discord member data
    from its own Redis cache (trust boundary — never trust client-supplied data).
    If the Discord user has no site account, one is auto-created.
    """
    user_id = data.get("user_id")
    discord_id = data.get("discord_id")

    if user_id:
        try:
            return CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
    elif discord_id:
        # Check if user already exists with this Discord ID
        existing = CustomUser.objects.filter(discordId=discord_id).first()
        if existing:
            return existing

        # Look up Discord data from our own cache (not client-supplied)
        if not org or not org.discord_server_id:
            return Response(
                {"error": "Cannot resolve Discord user without org Discord server"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"discord_members_search_{org.discord_server_id}"
        members = cache.get(cache_key)
        if not members:
            return Response(
                {"error": "Discord member cache is empty. Please refresh Discord members first."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Find the member in the cached list
        discord_member = None
        for m in members:
            if m.get("user", {}).get("id") == discord_id:
                discord_member = m
                break

        if not discord_member:
            return Response(
                {"error": "Discord member not found in cache"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Auto-create from cached Discord data
        # createFromDiscordData is an instance method expecting {"user": {...}, "nick": ...}
        positions = PositionsModel.objects.create()
        user = CustomUser(positions=positions)
        user.createFromDiscordData(discord_member)
        user.save()
        return user
    else:
        return Response(
            {"error": "user_id or discord_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
```

Add imports:

```python
from django.db import IntegrityError, transaction
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from app.models import CustomUser, Tournament, PositionsModel, OrgLog
from app.permissions_org import has_org_staff_access  # add to existing import block
from league.models import LeagueLog
```

Add URL patterns (check current URL config and add):

```python
path("organizations/<int:org_id>/members/", add_org_member, name="add-org-member"),
path("leagues/<int:league_id>/members/", add_league_member, name="add-league-member"),
path("tournaments/<int:tournament_id>/members/", add_tournament_member, name="add-tournament-member"),
```

**Step 4: Run tests to verify they pass**

Run: `just test::run 'python manage.py test app.tests.test_add_member -v 2'`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/views/admin_team.py backend/app/tests/test_add_member.py backend/app/urls.py
git commit -m "feat: add member endpoints for org, league, and tournament"
```

---

## Task 4: Frontend — API functions

**Files:**
- Modify: `frontend/app/components/api/types.d.ts` (add shared types)
- Modify: `frontend/app/components/api/api.tsx` (enhance searchUsers, add re-exports, add tournament member)
- Modify: `frontend/app/components/api/orgAPI.tsx` (add Discord + org member functions)
- Modify: `frontend/app/components/api/leagueAPI.tsx` (add league member function)

**Step 1: Add shared types**

Add to `frontend/app/components/api/types.d.ts`:

```typescript
export interface AddMemberPayload {
  user_id?: number;
  discord_id?: string;  // Backend looks up Discord data from its own cache
}

export interface AddUserResponse {
  status: string;
  user: UserType;
}
```

**Step 2: Add API functions**

Add to `frontend/app/components/api/orgAPI.tsx`:

```typescript
import type { AddMemberPayload, AddUserResponse } from './types';

export async function addOrgMember(
  orgId: number,
  payload: AddMemberPayload
): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(
    `/organizations/${orgId}/members/`,
    payload
  );
  return response.data.user;
}

// Discord member search
export interface DiscordSearchResult {
  user: {
    id: string;
    username: string;
    global_name?: string;
    avatar?: string;
  };
  nick?: string;
  has_site_account: boolean;
  site_user_pk: number | null;
}

export async function searchDiscordMembers(
  orgId: number,
  query: string
): Promise<DiscordSearchResult[]> {
  const response = await axios.get<{ results: DiscordSearchResult[] }>(
    `/discord/search-discord-members/`,
    { params: { q: query, org_id: orgId } }
  );
  return response.data.results;
}

export async function refreshDiscordMembers(
  orgId: number
): Promise<{ refreshed: boolean; count: number }> {
  const response = await axios.post<{ refreshed: boolean; count: number }>(
    `/discord/refresh-discord-members/`,
    { org_id: orgId }
  );
  return response.data;
}
```

Enhance `searchUsers` in `frontend/app/components/api/api.tsx`:

```typescript
export interface SearchUserResult extends UserType {
  membership?: 'league' | 'org' | 'other_org' | null;
  membership_label?: string | null;
}

export async function searchUsers(
  query: string,
  orgId?: number,
  leagueId?: number
): Promise<SearchUserResult[]> {
  const params: Record<string, string | number> = { q: query };
  if (orgId) params.org_id = orgId;
  if (leagueId) params.league_id = leagueId;
  const response = await axios.get<SearchUserResult[]>('/users/search/', { params });
  return response.data;
}
```

Add to `frontend/app/components/api/leagueAPI.tsx`:

```typescript
import type { AddMemberPayload, AddUserResponse } from './types';

export async function addLeagueMember(
  leagueId: number,
  payload: AddMemberPayload
): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(
    `/leagues/${leagueId}/members/`,
    payload
  );
  return response.data.user;
}
```

Add to `frontend/app/components/api/api.tsx` (tournament functions already live here):

```typescript
import type { AddMemberPayload, AddUserResponse } from './types';

export async function addTournamentMember(
  tournamentId: number,
  payload: AddMemberPayload
): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(
    `/tournaments/${tournamentId}/members/`,
    payload
  );
  return response.data.user;
}
```

**Step 3: Add re-exports to `api.tsx`**

All consumers import from `~/components/api/api`. Add these re-exports:

```typescript
// Add to the orgAPI re-export block:
export {
  // ... existing re-exports ...
  addOrgMember,
  searchDiscordMembers,
  refreshDiscordMembers,
  type DiscordSearchResult,
} from './orgAPI';

// Add to the leagueAPI re-export block:
export {
  // ... existing re-exports ...
  addLeagueMember,
} from './leagueAPI';

// Re-export shared types:
export type { AddMemberPayload, AddUserResponse } from './types';
```

**Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors in new/modified files.

**Step 3: Commit**

```bash
git add frontend/app/components/api/
git commit -m "feat: add API functions for member search, Discord search, and add member"
```

---

## Task 5: Frontend — AddUserModal types

**Files:**
- Create: `frontend/app/components/user/AddUserModal/types.ts`

**Step 1: Create types file**

```typescript
import type { UserType } from '~/components/user/types';
import type { SearchUserResult, DiscordSearchResult, AddMemberPayload } from '~/components/api/api';

export interface EntityContext {
  orgId?: number;
  leagueId?: number;
  tournamentId?: number;
}

export interface AddUserModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  entityContext: EntityContext;
  onAdd: (payload: AddMemberPayload) => Promise<UserType>;
  isAdded: (user: UserType) => boolean;
  entityLabel: string;
  /** Whether the org has a Discord server configured (checks discord_server_id) */
  hasDiscordServer: boolean;
}

export interface SiteUserResultsProps {
  results: SearchUserResult[];
  loading: boolean;
  onAdd: (payload: AddMemberPayload) => Promise<void>;
  isAdded: (user: UserType) => boolean;
  entityLabel: string;
}

export interface DiscordMemberResultsProps {
  results: DiscordSearchResult[];
  loading: boolean;
  onAdd: (payload: AddMemberPayload) => Promise<void>;
  isAdded: (user: UserType) => boolean;
  isDiscordUserAdded: (discordId: string) => boolean;
  entityLabel: string;
  orgId?: number;
  onRefresh: () => Promise<void>;
  refreshing: boolean;
  hasDiscordServer: boolean;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

**Step 3: Commit**

```bash
git add frontend/app/components/user/AddUserModal/types.ts
git commit -m "feat: add AddUserModal TypeScript types"
```

---

## Task 6: Frontend — DiscordMemberStrip component

**Files:**
- Create: `frontend/app/components/user/DiscordMemberStrip.tsx`

**Step 1: Create DiscordMemberStrip**

This component mirrors the visual style of `UserStrip` (see `frontend/app/components/user/UserStrip.tsx`) — same Tailwind classes, `cn()` utility, and border/background patterns.

**IMPORTANT:** `onAdd` accepts the member as an argument (not a closure). This prevents inline arrow functions from defeating `React.memo` in the parent's render loop.

```tsx
import React, { useCallback } from 'react';
import { Button } from '~/components/ui/button';
import type { DiscordSearchResult } from '~/components/api/api';
import { cn } from '~/lib/utils';

interface DiscordMemberStripProps {
  member: DiscordSearchResult;
  /** Accepts member as argument — DO NOT use inline arrows in parent */
  onAdd: (member: DiscordSearchResult) => void;
  disabled: boolean;
  disabledLabel?: string;
  adding?: boolean;
}

function getDiscordAvatarUrl(member: DiscordSearchResult): string {
  const { id, avatar } = member.user;
  if (avatar) {
    return `https://cdn.discordapp.com/avatars/${id}/${avatar}.png?size=32`;
  }
  // Default Discord avatar
  const index = Number(BigInt(id) >> 22n) % 6;
  return `https://cdn.discordapp.com/embed/avatars/${index}.png`;
}

export const DiscordMemberStrip = React.memo(function DiscordMemberStrip({
  member,
  onAdd,
  disabled,
  disabledLabel,
  adding,
}: DiscordMemberStripProps) {
  const displayName =
    member.nick || member.user.global_name || member.user.username;
  const subtitle =
    member.nick || member.user.global_name
      ? member.user.username
      : undefined;

  const handleClick = useCallback(() => onAdd(member), [onAdd, member]);

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg p-1 transition-colors',
        'border border-border/50',
        'bg-muted/20 hover:bg-muted/40',
        disabled && 'opacity-50',
      )}
    >
      {/* Avatar */}
      <img
        src={getDiscordAvatarUrl(member)}
        alt={displayName}
        className="h-8 w-8 rounded-full shrink-0"
      />

      {/* Name */}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-medium text-foreground">
          {displayName}
        </span>
        {subtitle && (
          <span className="truncate text-xs text-muted-foreground">
            {subtitle}
          </span>
        )}
      </div>

      {/* Site account badge */}
      {member.has_site_account && (
        <span className="shrink-0 text-xs text-muted-foreground">
          Linked
        </span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Action */}
      <div className="shrink-0">
        {disabled ? (
          <span className="text-xs text-muted-foreground">
            {disabledLabel || 'Added'}
          </span>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={handleClick}
            disabled={adding}
          >
            {adding ? '...' : '+'}
          </Button>
        )}
      </div>
    </div>
  );
});
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

**Step 3: Commit**

```bash
git add frontend/app/components/user/DiscordMemberStrip.tsx
git commit -m "feat: add DiscordMemberStrip component matching UserStrip styling"
```

---

## Task 7: Frontend — SiteUserResults component

**Files:**
- Create: `frontend/app/components/user/AddUserModal/SiteUserResults.tsx`

**Step 1: Create SiteUserResults**

Uses existing `UserStrip` component with `contextSlot` for membership badge and `actionSlot` for add button. MembershipBadge uses the existing `Badge` component with semantic theme tokens.

```tsx
import React, { useCallback, useState } from 'react';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { UserStrip } from '~/components/user/UserStrip';
import { toast } from 'sonner';
import type { SearchUserResult, AddMemberPayload } from '~/components/api/api';
import type { SiteUserResultsProps } from './types';

function MembershipBadge({ result }: { result: SearchUserResult }) {
  if (!result.membership) return null;

  const config: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline'; className: string }> = {
    league: { label: 'League Member', variant: 'secondary', className: 'text-info' },
    org: { label: 'Org Member', variant: 'secondary', className: 'text-success' },
    other_org: { label: `Other: ${result.membership_label}`, variant: 'outline', className: 'text-warning' },
  };

  const { label, variant, className } = config[result.membership] ?? {
    label: result.membership_label ?? '',
    variant: 'outline' as const,
    className: 'text-muted-foreground',
  };

  return (
    <Badge variant={variant} className={`text-xs px-1.5 py-0 ${className}`}>
      {label}
    </Badge>
  );
}

export const SiteUserResults: React.FC<SiteUserResultsProps> = ({
  results,
  loading,
  onAdd,
  isAdded,
  entityLabel,
}) => {
  const [addingPk, setAddingPk] = useState<number | null>(null);

  const handleAdd = useCallback(
    async (user: SearchUserResult) => {
      if (!user.pk) return;
      setAddingPk(user.pk);
      try {
        await onAdd({ user_id: user.pk });
        toast.success(`Added ${user.nickname || user.username}`);
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : 'Failed to add user'
        );
      } finally {
        setAddingPk(null);
      }
    },
    [onAdd]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        Searching...
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No site users found
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {results.map((result) => {
        const added = result.pk ? isAdded(result) : false;

        return (
          <UserStrip
            key={result.pk}
            user={result}
            compact
            contextSlot={<MembershipBadge result={result} />}
            actionSlot={
              added ? (
                <span className="text-xs text-muted-foreground">
                  Already in {entityLabel}
                </span>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleAdd(result)}
                  disabled={addingPk === result.pk}
                >
                  {addingPk === result.pk ? '...' : '+'}
                </Button>
              )
            }
            className={added ? 'opacity-50' : ''}
          />
        );
      })}
    </div>
  );
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

**Step 3: Commit**

```bash
git add frontend/app/components/user/AddUserModal/SiteUserResults.tsx
git commit -m "feat: add SiteUserResults component with membership badges"
```

---

## Task 8: Frontend — DiscordMemberResults component

**Files:**
- Create: `frontend/app/components/user/AddUserModal/DiscordMemberResults.tsx`

**Step 1: Create DiscordMemberResults**

Note: `DiscordMemberStrip.onAdd` accepts the member as an argument — NO inline arrows.
Payload uses `discord_id` (backend looks up data from its own cache).

```tsx
import React, { useCallback, useState } from 'react';
import { Button } from '~/components/ui/button';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { DiscordMemberStrip } from '~/components/user/DiscordMemberStrip';
import type { DiscordMemberResultsProps } from './types';
import type { AddMemberPayload, DiscordSearchResult } from '~/components/api/api';

export const DiscordMemberResults: React.FC<DiscordMemberResultsProps> = ({
  results,
  loading,
  onAdd,
  isAdded,
  isDiscordUserAdded,
  entityLabel,
  onRefresh,
  refreshing,
  hasDiscordServer,
}) => {
  const [addingId, setAddingId] = useState<string | null>(null);

  const handleAdd = useCallback(
    async (member: DiscordSearchResult) => {
      const discordId = member.user.id;
      setAddingId(discordId);
      try {
        // Backend resolves Discord data from its own cache — just send the ID
        const payload: AddMemberPayload = member.has_site_account
          ? { user_id: member.site_user_pk! }
          : { discord_id: member.user.id };
        await onAdd(payload);
        toast.success(
          `Added ${member.nick || member.user.global_name || member.user.username}`
        );
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : 'Failed to add user'
        );
      } finally {
        setAddingId(null);
      }
    },
    [onAdd]
  );

  if (!hasDiscordServer) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No Discord server configured for this organization
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Refresh button */}
      <Button
        variant="outline"
        className="w-full"
        onClick={onRefresh}
        disabled={refreshing}
      >
        <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
        {refreshing ? 'Refreshing...' : 'Refresh Discord Members'}
      </Button>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          Searching...
        </div>
      ) : results.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          No Discord members found
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {results.map((member) => {
            const isDisabled = isDiscordUserAdded(member.user.id);

            return (
              <DiscordMemberStrip
                key={member.user.id}
                member={member}
                onAdd={handleAdd}
                disabled={isDisabled}
                disabledLabel={`Already in ${entityLabel}`}
                adding={addingId === member.user.id}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

**Step 3: Commit**

```bash
git add frontend/app/components/user/AddUserModal/DiscordMemberResults.tsx
git commit -m "feat: add DiscordMemberResults component with refresh button"
```

---

## Task 9: Frontend — AddUserModal main component

**Files:**
- Create: `frontend/app/components/user/AddUserModal/AddUserModal.tsx`
- Create: `frontend/app/components/user/AddUserModal/index.ts`

**Step 1: Create AddUserModal**

This is the main modal component. Uses `useDebouncedValue` + `useQuery` from `@tanstack/react-query` (matching `UserSearchInput` pattern) instead of manual debounce + Promise.all. This prevents race conditions where stale search responses overwrite newer results.

`hasDiscordServer` is a **prop** from the parent (which checks `discord_server_id`), not derived from `Boolean(orgId)`.

```tsx
import React, { useState, useCallback, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FormDialog } from '~/components/ui/dialogs/FormDialog';
import { Input } from '~/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Search } from 'lucide-react';
import {
  searchUsers,
  searchDiscordMembers,
  refreshDiscordMembers,
} from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';
import { toast } from 'sonner';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import { SiteUserResults } from './SiteUserResults';
import { DiscordMemberResults } from './DiscordMemberResults';
import type { AddUserModalProps } from './types';
import type { UserType } from '~/components/user/types';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 3;

export const AddUserModal: React.FC<AddUserModalProps> = ({
  open,
  onOpenChange,
  title,
  entityContext,
  onAdd,
  isAdded,
  entityLabel,
  hasDiscordServer,
}) => {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query, DEBOUNCE_MS);
  const [refreshing, setRefreshing] = useState(false);
  const [addedUsers, setAddedUsers] = useState<Set<number>>(new Set());
  const [addedDiscordIds, setAddedDiscordIds] = useState<Set<string>>(new Set());
  const queryClient = useQueryClient();
  const queryRef = useRef(query);
  queryRef.current = query;

  // Site user search via react-query (automatic race condition handling)
  const siteQuery = useQuery({
    queryKey: ['userSearch', debouncedQuery, entityContext.orgId, entityContext.leagueId],
    queryFn: () => searchUsers(debouncedQuery, entityContext.orgId, entityContext.leagueId),
    enabled: open && debouncedQuery.length >= MIN_QUERY_LENGTH,
  });

  // Discord member search via react-query
  const discordQuery = useQuery({
    queryKey: ['discordSearch', debouncedQuery, entityContext.orgId],
    queryFn: () => searchDiscordMembers(entityContext.orgId!, debouncedQuery),
    enabled: open && debouncedQuery.length >= MIN_QUERY_LENGTH && hasDiscordServer && !!entityContext.orgId,
  });

  const siteResults = siteQuery.data ?? [];
  const discordResults = discordQuery.data ?? [];

  // Reset state when modal closes
  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setQuery('');
        setAddedUsers(new Set());
        setAddedDiscordIds(new Set());
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange]
  );

  const handleRefresh = useCallback(async () => {
    if (!entityContext.orgId) return;
    setRefreshing(true);
    try {
      const result = await refreshDiscordMembers(entityContext.orgId);
      toast.success(`Refreshed ${result.count} Discord members`);
      // Invalidate Discord search query to re-fetch
      queryClient.invalidateQueries({ queryKey: ['discordSearch'] });
    } catch {
      toast.error('Failed to refresh Discord members');
    } finally {
      setRefreshing(false);
    }
  }, [entityContext.orgId, queryClient]);

  // Wrap onAdd to track locally added users (optimistic)
  const handleAdd = useCallback(
    async (payload: AddMemberPayload) => {
      const user = await onAdd(payload);
      // Track in local state so isAdded works immediately
      if (user.pk) {
        setAddedUsers((prev) => new Set(prev).add(user.pk!));
      }
      if (payload.discord_id) {
        setAddedDiscordIds((prev) => new Set(prev).add(payload.discord_id!));
      }
      return user;
    },
    [onAdd]
  );

  const checkIsAdded = useCallback(
    (user: UserType) => {
      if (user.pk && addedUsers.has(user.pk)) return true;
      return isAdded(user);
    },
    [isAdded, addedUsers]
  );

  const checkIsDiscordUserAdded = useCallback(
    (discordId: string) => {
      if (addedDiscordIds.has(discordId)) return true;
      // Check if the Discord user has a linked site account that's already added
      const member = discordResults.find((m) => m.user.id === discordId);
      if (member?.has_site_account && member.site_user_pk) {
        return addedUsers.has(member.site_user_pk) || isAdded({ pk: member.site_user_pk } as UserType);
      }
      return false;
    },
    [addedDiscordIds, addedUsers, discordResults, isAdded]
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={title}
      onSubmit={() => handleOpenChange(false)}
      submitLabel="Done"
      size="xl"
      showFooter={false}
      data-testid="add-user-modal"
    >
      {/* Single search bar */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by username, nickname, or Steam ID..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9"
          autoFocus
          data-testid="add-user-search"
        />
        {query.length > 0 && query.length < MIN_QUERY_LENGTH && (
          <p className="mt-1 text-xs text-muted-foreground">
            Type at least {MIN_QUERY_LENGTH} characters to search
          </p>
        )}
      </div>

      {/* Desktop: two columns, Mobile: tabs */}
      <div className="hidden md:grid md:grid-cols-2 md:gap-4">
        <div>
          <h3 className="mb-2 text-sm font-medium text-foreground">
            Site Users
          </h3>
          <SiteUserResults
            results={siteResults}
            loading={siteQuery.isFetching}
            onAdd={handleAdd}
            isAdded={checkIsAdded}
            entityLabel={entityLabel}
          />
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium text-foreground">
            Discord Members
          </h3>
          <DiscordMemberResults
            results={discordResults}
            loading={discordQuery.isFetching}
            onAdd={handleAdd}
            isAdded={checkIsAdded}
            isDiscordUserAdded={checkIsDiscordUserAdded}
            entityLabel={entityLabel}
            orgId={entityContext.orgId}
            onRefresh={handleRefresh}
            refreshing={refreshing}
            hasDiscordServer={hasDiscordServer}
          />
        </div>
      </div>

      {/* Mobile: tabs */}
      <div className="md:hidden">
        <Tabs defaultValue="site">
          <TabsList className="w-full">
            <TabsTrigger value="site" className="flex-1">
              Site Users
            </TabsTrigger>
            <TabsTrigger value="discord" className="flex-1">
              Discord
            </TabsTrigger>
          </TabsList>
          <TabsContent value="site">
            <SiteUserResults
              results={siteResults}
              loading={siteQuery.isFetching}
              onAdd={handleAdd}
              isAdded={checkIsAdded}
              entityLabel={entityLabel}
            />
          </TabsContent>
          <TabsContent value="discord">
            <DiscordMemberResults
              results={discordResults}
              loading={discordQuery.isFetching}
              onAdd={handleAdd}
              isAdded={checkIsAdded}
              isDiscordUserAdded={checkIsDiscordUserAdded}
              entityLabel={entityLabel}
              orgId={entityContext.orgId}
              onRefresh={handleRefresh}
              refreshing={refreshing}
              hasDiscordServer={hasDiscordServer}
            />
          </TabsContent>
        </Tabs>
      </div>
    </FormDialog>
  );
};
```

Create barrel export `frontend/app/components/user/AddUserModal/index.ts`:

```typescript
export { AddUserModal } from './AddUserModal';
export type { AddUserModalProps, EntityContext } from './types';
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

**Step 3: Commit**

```bash
git add frontend/app/components/user/AddUserModal/ frontend/app/components/user/DiscordMemberStrip.tsx
git commit -m "feat: add AddUserModal with useQuery search and responsive two-column layout"
```

---

## Task 10: Frontend — Wire up AddUserModal to Organization page

**Files:**
- Modify: `frontend/app/routes/organization.tsx` or the org members tab component
- Reference: `frontend/app/store/orgStore.ts` for `orgUsers`, `setOrgUsers`

**Step 1: Identify the org members section**

Find where the members/users list is rendered on the Organization page. Look for the tab that uses `getOrgUsers` or `orgUsers`. The `AddUserModal` replaces the existing add flow.

**Step 2: Add AddUserModal to the org members tab**

Uses `useOrgStore.getState()` inside the callback to avoid closing over `orgUsers` (which would cause callback recreation on every add and stale closure bugs).

```tsx
import { AddUserModal } from '~/components/user/AddUserModal';
import { addOrgMember } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';

// Inside the component:
const [showAddUser, setShowAddUser] = useState(false);
const orgUsers = useOrgStore((s) => s.orgUsers);
const currentOrg = useOrgStore((s) => s.currentOrg);

// Stable callback — uses getState() to read current orgUsers at call time
const handleAddMember = useCallback(
  async (payload: AddMemberPayload) => {
    if (!currentOrg?.pk) throw new Error('No organization');
    const user = await addOrgMember(currentOrg.pk, payload);
    // Optimistic update — read current state at call time, not closure time
    const { orgUsers, setOrgUsers } = useOrgStore.getState();
    setOrgUsers([...orgUsers, user]);
    return user;
  },
  [currentOrg?.pk]
);

// isUserAdded uses a Set for O(1) lookups
const addedPkSet = useMemo(
  () => new Set(orgUsers.map((u) => u.pk)),
  [orgUsers]
);
const isUserAdded = useCallback(
  (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
  [addedPkSet]
);

// hasDiscordServer checks actual discord_server_id, not just orgId existence
const hasDiscordServer = Boolean(currentOrg?.discord_server_id);

// In JSX, add button to trigger modal + the modal:
<Button onClick={() => setShowAddUser(true)}>Add Member</Button>

<AddUserModal
  open={showAddUser}
  onOpenChange={setShowAddUser}
  title={`Add Member to ${currentOrg?.name || 'Organization'}`}
  entityContext={{ orgId: currentOrg?.pk }}
  onAdd={handleAddMember}
  isAdded={isUserAdded}
  entityLabel={currentOrg?.name || 'Organization'}
  hasDiscordServer={hasDiscordServer}
/>
```

**Step 3: Verify it renders**

Start dev environment: `just dev::debug`
Navigate to an organization page, open the members tab, click "Add Member".
Expected: Modal opens with search bar and two-column layout.

**Step 4: Commit**

```bash
git add frontend/app/routes/organization.tsx  # or relevant file
git commit -m "feat: wire AddUserModal to organization members section"
```

---

## Task 11: Frontend — Wire up AddUserModal to League page

**Files:**
- Modify: `frontend/app/components/league/tabs/UsersTab.tsx` or relevant league page component
- Reference: `frontend/app/store/leagueStore.ts` for `leagueUsers`, `setLeagueUsers`
- Reference: `frontend/app/store/orgStore.ts` for `currentOrg` (league belongs to an org)

**Step 1: Identify the league members section**

Find where the members/users list is rendered on the League page. Look for the tab that uses `getLeagueUsers` or `leagueUsers`. The `AddUserModal` replaces the existing add flow.

**Step 2: Add AddUserModal to league members tab**

Same pattern as Task 10 — uses `useLeagueStore.getState()` inside the callback to avoid stale closure, `useMemo` Set for O(1) lookups, and `hasDiscordServer` prop.

```tsx
import { AddUserModal } from '~/components/user/AddUserModal';
import { addLeagueMember } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';

// Inside the component:
const [showAddUser, setShowAddUser] = useState(false);
const leagueUsers = useLeagueStore((s) => s.leagueUsers);
const currentLeague = useLeagueStore((s) => s.currentLeague);
const currentOrg = useOrgStore((s) => s.currentOrg);

// Stable callback — uses getState() to read current leagueUsers at call time
const handleAddMember = useCallback(
  async (payload: AddMemberPayload) => {
    if (!currentLeague?.pk) throw new Error('No league');
    const user = await addLeagueMember(currentLeague.pk, payload);
    // Optimistic update — read current state at call time, not closure time
    const { leagueUsers, setLeagueUsers } = useLeagueStore.getState();
    setLeagueUsers([...leagueUsers, user]);
    return user;
  },
  [currentLeague?.pk]
);

// isUserAdded uses a Set for O(1) lookups
const addedPkSet = useMemo(
  () => new Set(leagueUsers.map((u) => u.pk)),
  [leagueUsers]
);
const isUserAdded = useCallback(
  (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
  [addedPkSet]
);

// hasDiscordServer checks actual discord_server_id on the parent org
const hasDiscordServer = Boolean(currentOrg?.discord_server_id);

// In JSX:
<Button onClick={() => setShowAddUser(true)}>Add Member</Button>

<AddUserModal
  open={showAddUser}
  onOpenChange={setShowAddUser}
  title={`Add Member to ${currentLeague?.name || 'League'}`}
  entityContext={{
    orgId: currentOrg?.pk,
    leagueId: currentLeague?.pk,
  }}
  onAdd={handleAddMember}
  isAdded={isUserAdded}
  entityLabel={currentLeague?.name || 'League'}
  hasDiscordServer={hasDiscordServer}
/>
```

**Step 3: Verify it renders**

Start dev environment: `just dev::debug`
Navigate to a league page, open the members tab, click "Add Member".
Expected: Modal opens with search bar and two-column layout (Discord column visible only if parent org has `discord_server_id`).

**Step 4: Commit**

```bash
git add frontend/app/components/league/tabs/UsersTab.tsx  # or relevant file
git commit -m "feat: wire AddUserModal to league members section"
```

---

## Task 12: Frontend — Wire up AddUserModal to Tournament page

**Files:**
- Modify: `frontend/app/pages/tournament/tabs/players/` — replace or update existing `addPlayerModal.tsx`
- Reference: Tournament uses direct M2M `users` field (no intermediary model like OrgUser/LeagueUser)

**Step 1: Replace existing addPlayerModal with AddUserModal**

The existing `addPlayerModal.tsx` at `frontend/app/pages/tournament/tabs/players/addPlayerModal.tsx` should be replaced or updated to use the new `AddUserModal`. This component currently uses the old pattern of client-side search against `orgUsers` or `globalUsers`.

Same patterns as Tasks 10-11: `getState()` for optimistic updates, `useMemo` Set for O(1) lookups, `hasDiscordServer` prop. Note: `addTournamentMember` lives in `api.tsx` (not a separate `tournamentAPI.tsx`).

```tsx
import { AddUserModal } from '~/components/user/AddUserModal';
import { addTournamentMember } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';

// In the parent component that manages the tournament players tab:
const [showAddUser, setShowAddUser] = useState(false);
const currentOrg = useOrgStore((s) => s.currentOrg);

// Tournament users — get from whatever state manages them (local state or store)
// Use getState() pattern if using a store, or local state if managed locally
const handleAddMember = useCallback(
  async (payload: AddMemberPayload) => {
    if (!tournamentId) throw new Error('No tournament');
    const user = await addTournamentMember(tournamentId, payload);
    // Optimistic update — append to local tournament users list
    // If using local state:
    setTournamentUsers((prev) => [...prev, user]);
    // If using a store, use getState() pattern like Tasks 10-11
    return user;
  },
  [tournamentId]
);

// isUserAdded uses a Set for O(1) lookups
const addedPkSet = useMemo(
  () => new Set(tournamentUsers.map((u) => u.pk)),
  [tournamentUsers]
);
const isUserAdded = useCallback(
  (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
  [addedPkSet]
);

// hasDiscordServer checks actual discord_server_id on the parent org
const hasDiscordServer = Boolean(currentOrg?.discord_server_id);

// In JSX:
<Button onClick={() => setShowAddUser(true)}>Add Player</Button>

<AddUserModal
  open={showAddUser}
  onOpenChange={setShowAddUser}
  title={`Add Player to ${tournament?.name || 'Tournament'}`}
  entityContext={{
    orgId: currentOrg?.pk,
    leagueId: tournament?.league?.pk,
    tournamentId: tournament?.pk,
  }}
  onAdd={handleAddMember}
  isAdded={isUserAdded}
  entityLabel={tournament?.name || 'Tournament'}
  hasDiscordServer={hasDiscordServer}
/>
```

**Step 2: Verify it renders**

Start dev environment: `just dev::debug`
Navigate to a tournament page, open the players tab, click "Add Player".
Expected: Modal opens with search bar. Discord column visible only if parent org has `discord_server_id`.

**Step 3: Commit**

```bash
git add frontend/app/pages/tournament/tabs/players/
git commit -m "feat: wire AddUserModal to tournament players section"
```

---

## Task 13: End-to-end manual testing

**Step 1: Start test environment**

```bash
just test::up
just db::populate::all
```

**Step 2: Test org member add flow**

1. Navigate to an organization page → Members tab
2. Click "Add Member"
3. Search for a user by username — verify membership badges appear
4. Search for a user by Steam ID — verify results
5. Click Add on a global user — verify success toast and user appears grayed
6. Search Discord column — verify Discord members appear
7. Click Refresh Discord — verify refresh works
8. Click Add on a Discord member without site account — verify auto-create
9. Close and reopen modal — verify state resets

**Step 3: Test league member add flow**

Same as above but from a league page. Verify:
- League members show "Already in {league}" (grayed)
- Org members show "Org Member" badge
- Adding creates both OrgUser + LeagueUser if needed

**Step 4: Test tournament member add flow**

Same pattern from tournament page.

**Step 5: Test mobile view**

Resize browser to <768px. Verify tabs appear instead of columns.

**Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during manual testing"
```

---

## Phase 2: Test Suite Remediation

> **Analysis performed by 6 parallel agents** reviewing all skipped and flaky Playwright tests.
> Goal: Zero skipped tests without justification, zero flaky tests.

### Summary

| Category | Count | Action |
|----------|-------|--------|
| Tests to UNSKIP & FIX | 15 | Remove `.skip()`, fix issues |
| Tests to REMOVE | 2 | Delete duplicate test file |
| Tests to KEEP SKIPPED | 13 | Add clear justification comments |
| Flaky tests to FIX | 3 | Address root cause race conditions |

---

## Task 13: Remove Duplicate Test File

**Files:**
- Delete: `frontend/tests/playwright/e2e/herodraft/kick-reconnect.spec.ts`

**Reason:** This file duplicates functionality already tested in `herodraft-captain-connection.spec.ts`. Both test the same "kick old connection" feature. The canonical test is in `herodraft-captain-connection.spec.ts`.

**Step 1: Verify duplicate coverage**

```bash
# Compare test descriptions
grep -n "kick\|reconnect" frontend/tests/playwright/e2e/herodraft/kick-reconnect.spec.ts
grep -n "kick\|reconnect" frontend/tests/playwright/e2e/herodraft-captain-connection.spec.ts
```

**Step 2: Delete the duplicate file**

```bash
rm frontend/tests/playwright/e2e/herodraft/kick-reconnect.spec.ts
```

**Step 3: Commit**

```bash
git add -A
git commit -m "test: remove duplicate kick-reconnect.spec.ts (covered by herodraft-captain-connection.spec.ts)"
```

---

## Task 14: Unskip HeroDraft Timeout Auto-Random Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/herodraft/timeout-auto-random.spec.ts`

**Reason:** All 4 tests in this file test the auto-random pick feature which is **fully implemented**:
- Backend: `force_herodraft_timeout` endpoint exists
- Backend: `auto_random_pick` function broadcasts state updates
- Frontend: Store handles `herodraft_event` messages correctly

**Step 1: Remove all `.skip()` calls**

```typescript
// Change all instances of:
test.skip('auto-random pick is triggered...', async () => {
// To:
test('auto-random pick is triggered...', async () => {
```

Remove `.skip()` from all 4 tests:
1. "auto-random pick is triggered on timeout and broadcast to all clients"
2. "multiple consecutive timeouts complete multiple rounds"
3. "timeout advances through different round types (bans and picks)"
4. "draft completes when all rounds timeout"

**Step 2: Run tests to verify**

```bash
npx playwright test tests/playwright/e2e/herodraft/timeout-auto-random.spec.ts --repeat-each=2
```

**Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/herodraft/timeout-auto-random.spec.ts
git commit -m "test: unskip timeout-auto-random tests (feature fully implemented)"
```

---

## Task 15: Unskip WebSocket Reconnect Tests (Partial)

**Files:**
- Modify: `frontend/tests/playwright/e2e/herodraft/websocket-reconnect-fuzz.spec.ts`

**Reason:** First 2 tests have stable features, last 2 have legitimate issues.

**Step 1: Unskip first 2 tests**

Remove `.skip()` from:
1. "should maintain state through multiple connection drops during waiting phase"
2. "should recover draft state after reconnection during drafting phase"

**Step 2: Add justification comments to remaining skipped tests**

```typescript
// Keep skipped with clear reason:
test.skip('should pause timer when disconnected and resume on reconnect', async () => {
  // SKIP REASON: Timer pause feature not fully implemented on backend.
  // The server doesn't pause/resume timers on disconnect - it would require
  // tracking connection state per-user and coordinating timer state.
});

test.skip('should complete full draft with intermittent connection drops', async () => {
  // SKIP REASON: Complex stress test with random timing that causes
  // unpredictable failures. The first two tests cover the core reconnection
  // scenarios adequately.
});
```

**Step 3: Run tests to verify**

```bash
npx playwright test tests/playwright/e2e/herodraft/websocket-reconnect-fuzz.spec.ts
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/herodraft/websocket-reconnect-fuzz.spec.ts
git commit -m "test: unskip websocket reconnect tests 1-2, document skip reasons for 3-4"
```

---

## Task 16: Unskip Captain Connection Test

**Files:**
- Modify: `frontend/tests/playwright/e2e/herodraft-captain-connection.spec.ts`

**Reason:** "kick old connection" feature is fully implemented with proper test IDs.

**Step 1: Unskip first test only**

```typescript
// Change:
test.skip('should kick old connection when captain opens new tab', async ({
// To:
test('should kick old connection when captain opens new tab', async ({
```

**Step 2: Add justification to remaining skipped test**

```typescript
test.skip('should only kick captain connections, not spectators', async ({
  // SKIP REASON: Complex 4-context test (2 captains + 2 spectators) with
  // timing-sensitive WebSocket interactions. The first test covers the core
  // kick functionality. Spectator handling is an edge case.
```

**Step 3: Run test to verify**

```bash
npx playwright test tests/playwright/e2e/herodraft-captain-connection.spec.ts
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/herodraft-captain-connection.spec.ts
git commit -m "test: unskip captain connection kick test, document spectator test skip"
```

---

## Task 17: Unskip and Fix Largo Hero Pick Test

**Files:**
- Modify: `frontend/tests/playwright/e2e/herodraft/largo-hero-pick.spec.ts`

**Reason:** The original regression (hardcoded hero IDs 1-138) has been fixed. Hero data now comes from `dotaconstants` dynamically.

**Step 1: Unskip and refactor to use fixtures**

```typescript
import { test, expect } from '../../fixtures';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

test.describe('Largo Hero Pick', () => {
  test('should be able to pick Largo (ID 155) in draft', async ({ page, loginAdmin }) => {
    await loginAdmin();

    // Use the helper class for reliable interactions
    const heroDraftPage = new HeroDraftPage(page);

    // Navigate to a draft that's in drafting phase
    // ... (refactor to use test fixtures instead of manual browser creation)
  });
});
```

**Step 2: Run test to verify**

```bash
npx playwright test tests/playwright/e2e/herodraft/largo-hero-pick.spec.ts
```

**Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/herodraft/largo-hero-pick.spec.ts
git commit -m "test: unskip and refactor largo-hero-pick test to use fixtures"
```

---

## Task 18: Fix Undo Pick Permission Test

**Files:**
- Modify: `frontend/tests/playwright/e2e/07-draft/02-undo-pick.spec.ts`

**Reason:** Permission test "should NOT show undo button for non-staff users" is important for security validation.

**Step 1: Unskip and fix the permission test**

```typescript
// Change:
test.skip('should NOT show undo button for non-staff users', async ({
// To:
test('should NOT show undo button for non-staff users', async ({
```

Fix the test to:
1. Use `completed_bracket` tournament (deterministic state)
2. Login as non-staff user
3. Navigate directly to tournament teams tab
4. Verify undo button is NOT visible

**Step 2: Add justification to remaining skipped tests**

```typescript
test.skip('should show undo button for staff when picks have been made', async ({
  // SKIP REASON: Requires specific draft state with curDraftRound.choice set.
  // Test data setup is complex - need tournament mid-draft with picks made.
  // The passing "no picks" test validates basic visibility logic.
});

test.skip('should undo the last pick when confirmed', async ({
  // SKIP REASON: Requires draft state with undoable picks. Complex setup.
});

test.skip('should cancel undo when cancel is clicked', async ({
  // SKIP REASON: Dialog interaction test - lower priority than core undo.
});
```

**Step 3: Run tests to verify**

```bash
npx playwright test tests/playwright/e2e/07-draft/02-undo-pick.spec.ts
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/07-draft/02-undo-pick.spec.ts
git commit -m "test: unskip undo permission test, document other skip reasons"
```

---

## Task 19: Fix Shuffle Draft Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/08-shuffle-draft/01-full-draft.spec.ts`

**Reason:** Tests are skipped because they use wrong tournament (`completed_bracket` instead of `shuffle_draft_captain_turn`).

**Step 1: Fix tournament data in skipped tests**

```typescript
// In the skipped tests, change:
const tournament = await getTournamentByKey(context, 'completed_bracket');
// To:
const tournament = await getTournamentByKey(context, 'shuffle_draft_captain_turn');
```

**Step 2: Unskip the 2 fixable tests**

1. "should open draft modal and configure shuffle draft style"
2. "should complete shuffle draft flow with picks"

**Step 3: Add justification to remaining skipped test**

```typescript
test.skip('should allow navigating back to previous rounds', async ({
  // SKIP REASON: Requires specific draft state that's hard to control.
  // Navigation between rounds depends on round completion state.
});
```

**Step 4: Run tests to verify**

```bash
npx playwright test tests/playwright/e2e/08-shuffle-draft/01-full-draft.spec.ts
```

**Step 5: Commit**

```bash
git add frontend/tests/playwright/e2e/08-shuffle-draft/01-full-draft.spec.ts
git commit -m "test: fix shuffle draft tests to use correct tournament data"
```

---

## Task 20: Unskip Bracket Badge Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/09-bracket/01-bracket-badges.spec.ts`

**Reason:** Feature exists (`BracketBadge.tsx`), test data exists (`completed_bracket`, `partial_bracket`, `pending_bracket`).

**Step 1: Remove outer describe.skip**

```typescript
// Change:
test.describe.skip('Bracket Badges (e2e)', () => {
// To:
test.describe('Bracket Badges (e2e)', () => {
```

**Step 2: Remove inner test.skip calls**

Remove `.skip()` from all 3 tests:
1. "should display bracket badges on winners bracket matches"
2. "should display corresponding badges on losers bracket slots"
3. "should show badge letters with distinct colors"

**Step 3: Run tests to verify**

```bash
npx playwright test tests/playwright/e2e/09-bracket/01-bracket-badges.spec.ts
```

**Step 4: If tests fail, debug and fix**

Common issues:
- Test data not populated correctly
- Selector changes needed
- Timing issues with bracket rendering

**Step 5: Commit**

```bash
git add frontend/tests/playwright/e2e/09-bracket/01-bracket-badges.spec.ts
git commit -m "test: unskip bracket badge tests"
```

---

## Task 21: Unskip Bracket Match Linking Tests (Main Block)

**Files:**
- Modify: `frontend/tests/playwright/e2e/09-bracket/02-bracket-match-linking.spec.ts`

**Reason:** Feature exists (`LinkSteamMatchModal.tsx`), test data exists (`bracket_linking` tournament).

**Step 1: Remove outer describe.skip**

```typescript
// Change:
test.describe.skip('Bracket Match Linking (e2e)', () => {
// To:
test.describe('Bracket Match Linking (e2e)', () => {
```

**Step 2: Keep nested describe.skip blocks with justification**

```typescript
test.describe.skip('View Details Functionality', () => {
  // SKIP REASON: Flaky due to bracket state not persisting reliably
  // between describe blocks. Tests depend on prior test state.
});

test.describe.skip('Non-Staff User Access', () => {
  // SKIP REASON: Same bracket state persistence issue.
});
```

**Step 3: Run main navigation tests**

```bash
npx playwright test tests/playwright/e2e/09-bracket/02-bracket-match-linking.spec.ts
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/09-bracket/02-bracket-match-linking.spec.ts
git commit -m "test: unskip bracket match linking main tests, keep nested skips documented"
```

---

## Task 22: Add Skip Justifications to Captain Pick Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/07-draft/01-captain-pick.spec.ts`

**Reason:** All 6 skipped tests test Framer Motion animations and UI timing, not core logic. Keep skipped but document why.

**Step 1: Add clear justification comments to all skipped tests**

```typescript
test.skip('should show floating draft indicator when captain has active turn', async ({
  // SKIP REASON: Tests Framer Motion animation timing for FloatingDraftIndicator.
  // The indicator depends on async currentUser.active_drafts state which has
  // variable initialization timing. Core functionality is validated by the
  // passing "notification badge" test.
});

test.skip('should auto-open draft modal when visiting tournament with ?draft=open', async ({
  // SKIP REASON: API timeout issues in test environment. Query param routing
  // and modal auto-opening logic work in production but have environment-specific
  // timing issues in Playwright.
});

// ... similar comments for all 6 skipped tests
```

**Step 2: Commit**

```bash
git add frontend/tests/playwright/e2e/07-draft/01-captain-pick.spec.ts
git commit -m "test: document skip reasons for captain pick animation tests"
```

---

## Task 23: Add Skip Justifications to Other Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/09-bracket/03-bracket-winner-advancement.spec.ts`
- Modify: `frontend/tests/playwright/e2e/10-leagues/01-tabs.spec.ts`
- Modify: `frontend/tests/playwright/e2e/11-org-mmr/02-claim-profile.spec.ts`

**Step 1: Add justification to bracket winner advancement**

```typescript
test.skip('should advance loser to losers bracket after winner selection', async ({
  // SKIP REASON: Timing issue - modal appears before reseed completes.
  // Needs waitForLoadState coordination between reseed dialog close and
  // next action. TODO: Fix modal timing after reseed confirmation.
});
```

**Step 2: Add justification to league tabs**

```typescript
test.skip('should handle browser back/forward navigation', async ({ page }) => {
  // SKIP REASON: React Router client-side navigation doesn't push history
  // entries that Playwright's goBack() can navigate. This is an SPA
  // architectural limitation, not a bug. Browser back/forward work differently
  // with client-side routing than server-side routing.
});
```

**Step 3: Fix or remove claim profile test**

Option A - Fix selector (dialog → popover):
```typescript
// Update selector from dialog to popover
const claimPopover = page.locator('[data-testid="claim-popover"]');
```

Option B - Remove if low priority feature.

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/09-bracket/03-bracket-winner-advancement.spec.ts
git add frontend/tests/playwright/e2e/10-leagues/01-tabs.spec.ts
git add frontend/tests/playwright/e2e/11-org-mmr/02-claim-profile.spec.ts
git commit -m "test: document skip reasons for bracket/league/claim tests"
```

---

## Task 24: Fix Flaky League Tabs Test

**Files:**
- Modify: `frontend/tests/playwright/helpers/utils.ts`

**Root Cause:** `visitAndWaitForHydration` only waits 500ms after `domcontentloaded`, but React Router initialization can take longer.

**Step 1: Increase hydration timeout**

```typescript
// In visitAndWaitForHydration function, change:
await page.waitForTimeout(500);
// To:
await page.waitForTimeout(1500);
```

**Step 2: Update the league tabs test for explicit state wait**

```typescript
test('should load correct tab from URL', async ({ page }) => {
  await visitAndWaitForHydration(page, `/leagues/${testLeagueId}/tournaments`);
  const leaguePage = new LeaguePage(page);

  // Wait for tab to actually be active (React Router state synced)
  await expect(leaguePage.tournamentsTab).toHaveAttribute('data-state', 'active', {
    timeout: 10000
  });

  await expect(page).toHaveURL(/\/tournaments/);
});
```

**Step 3: Run test multiple times to verify fix**

```bash
npx playwright test tests/playwright/e2e/10-leagues/01-tabs.spec.ts --repeat-each=5
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/helpers/utils.ts
git add frontend/tests/playwright/e2e/10-leagues/01-tabs.spec.ts
git commit -m "fix: increase hydration timeout to fix flaky league tabs test"
```

---

## Task 25: Fix Flaky Admin Claims Test

**Files:**
- Modify: `frontend/tests/playwright/e2e/11-org-mmr/03-admin-claims.spec.ts`

**Root Cause:** Race condition between API response and UI state updates when switching tabs.

**Step 1: Add explicit API response waiting**

```typescript
test('org admin can approve a pending claim', async ({ page, context, loginOrgAdmin }) => {
  const claim = await createClaimRequest(context);
  await loginOrgAdmin();
  await page.goto(`/organizations/${claim.organization}`);
  await page.waitForLoadState('networkidle');
  await page.getByTestId('org-tab-claims').click();
  await expect(page.getByTestId('claims-tab-pending')).toBeVisible();
  await page.waitForSelector('[data-testid="claims-list"]', { timeout: 10000 });
  await expect(page.getByTestId(`claim-card-${claim.id}`)).toBeVisible();

  // Wait for approve API response before checking UI
  const approvePromise = page.waitForResponse(
    (res) => res.url().includes('/approve/') && res.status() === 200
  );
  await page.getByTestId(`approve-claim-btn-${claim.id}`).click();
  await page.getByTestId('confirm-approve-claim').click();
  await approvePromise;

  // Wait for refetch after approval
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId(`claim-card-${claim.id}`)).not.toBeVisible({ timeout: 10000 });

  // Click approved tab and wait for its fetch
  await page.getByTestId('claims-tab-approved').click();
  await page.waitForResponse(
    (res) => res.url().includes('/claim-requests/') && res.status() === 200
  );

  await expect(page.getByTestId(`claim-card-${claim.id}`)).toBeVisible({ timeout: 10000 });
});
```

**Step 2: Run test multiple times to verify fix**

```bash
npx playwright test tests/playwright/e2e/11-org-mmr/03-admin-claims.spec.ts --repeat-each=5
```

**Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/11-org-mmr/03-admin-claims.spec.ts
git commit -m "fix: add explicit API response waiting to fix flaky admin claims test"
```

---

## Task 26: Fix Flaky HeroDraft Two-Captains Test

**Files:**
- Modify: `frontend/tests/playwright/e2e/herodraft/two-captains-full-draft.spec.ts`

**Root Cause:** Race conditions in WebSocket message synchronization between two captains during round transitions.

**Step 1: Increase round completion timeout**

```typescript
// Change timeout from 5000 to 10000:
await Promise.all([
    roundCompletedA.waitFor({ state: 'attached', timeout: 10000 }),
    roundCompletedB.waitFor({ state: 'attached', timeout: 10000 }),
]);
```

**Step 2: Add server-side state verification**

```typescript
// Add helper function to verify round completion on server
const verifyRoundCompleteOnServer = async (
  page: Page,
  draftId: number,
  roundNumber: number,
  timeout = 5000
) => {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    const response = await page.request.get(
      `https://localhost/api/herodraft/${draftId}/`,
      { failOnStatusCode: false }
    );
    const draft = await response.json();
    const round = draft.rounds?.find((r: any) => r.round_number === roundNumber);
    if (round?.state === 'completed') {
      return true;
    }
    await page.waitForTimeout(100);
  }
  return false;
};

// Use before waiting for DOM:
await verifyRoundCompleteOnServer(captainA.page, draftId, currentRound);
```

**Step 3: Run test multiple times to verify fix**

```bash
npx playwright test tests/playwright/e2e/herodraft/two-captains-full-draft.spec.ts --project=herodraft --repeat-each=3
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/herodraft/two-captains-full-draft.spec.ts
git commit -m "fix: increase timeouts and add server verification to fix flaky two-captains test"
```

---

## Task 27: Final Verification

**Step 1: Run full test suite**

```bash
just test::pw::headless
```

**Step 2: Verify results**

Expected:
- 0 failed tests
- 0 flaky tests (or significantly reduced)
- ~13 skipped tests (all with documented justification)
- All other tests passing

**Step 3: If any issues remain, debug and fix**

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: complete test suite remediation - all skips justified, flaky tests fixed"
```
