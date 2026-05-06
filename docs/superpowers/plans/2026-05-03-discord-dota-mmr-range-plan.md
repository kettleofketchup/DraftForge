# Discord Dota MMR Range Suggestions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a customizable, settings-driven medal→MMR range system that powers a new "Rank Signals" card in `MmrApprovalModal`. Server computes `suggested_mmr` and `suggested_mmr_range` per signup; frontend displays all signals (prior approved, self-reported, medal, battle cup) and a range helper.

**Architecture:** Site-wide medal/battle-cup MMR ranges live in Django settings. A pure-function suggestion module (`events/mmr_suggestions.py`) computes the modal's default and range from a `PlayerDotaProfile` + `OrgUser.mmr`. `EventSignupSerializer` exposes both via two new read-only fields. The modal is refactored to render a single `<RankSignalsCard>` (replacing two existing inline blocks) and a `<SuggestedRangeHelper>` line under the input.

**Tech Stack:** Django 5 + DRF on the backend, React 19 + TypeScript + shadcn/ui (Tailwind) on the frontend, pytest for backend unit tests, Playwright for E2E.

**Spec:** `docs/superpowers/specs/2026-05-03-discord-dota-mmr-range-design.md`

---

## File map

**New files:**
- `backend/events/mmr_suggestions.py` — pure functions: `suggest_mmr`, `_compute_range`, `_parse_medal`.
- `backend/events/tests/test_mmr_suggestions.py` — pytest unit tests.
- `frontend/app/components/events/RankSignalsCard.tsx` — read-only signals card.

**Modified files (MMR range feature):**
- `backend/backend/settings.py` — three settings constants.
- `backend/events/serializers.py` — three computed fields on `EventSignupSerializer`.
- `backend/tests/test_events_discord.py` — new `set_org_user_approved_mmr` test endpoint.
- `backend/tests/urls.py` — register the new endpoint URL.
- `frontend/app/components/events/MmrApprovalModal.tsx` — remove old constants + two inline blocks; render new card + helper; add `data-testid="mmr-input"`.
- `frontend/app/components/events/schemas.ts` — extend `EventSignupType`.
- `frontend/tests/playwright/fixtures/events.ts` — add `loginEventPlayer4` and `setApprovedMmr` helpers.
- `frontend/tests/playwright/fixtures/index.ts` — re-export the new helpers.
- `frontend/tests/playwright/e2e/16-events/04-discord-integration.spec.ts` — augment one test, add two siblings.

**Modified files (Discord MedalSelect race fix — Phase 4):**
- `backend/discordbot/components.py` — `MedalSelect.__init__` accepts `rank_status` + `require_screenshot`; `MedalSelect.callback` rebuilds the view directly.
- `backend/discordbot/bot.py` — remove the `rank_medal:` branch from `bot.on_interaction` (lines 268–285).
- `backend/discordbot/tests/test_components.py` — append `TestMedalSelectRebuildsView` regression tests.

**Modified/new files (Discord reminder count fix — Phase 5, issue #188):**
- `backend/events/discord/embeds.py` — replace `getattr(event, "signup_count", 0)` with `_signup_counts(event)` in `_build_reminder_embed` (line 434) and `build_signup_reminder_embed` (line 523).
- `backend/events/tests/test_reminder_embeds.py` (new) — regression test asserting reminder embeds show the real active signup count.

---

## Test data we'll reuse

The existing `populate_events_data` already creates everything we need — no new test users:

| User | PK | Profile |
|---|---|---|
| `event_player_1` | 5001 | `rank_status="active"`, `rank_medal="Legend 3"`, `mmr=3200` |
| `event_player_4` | 5004 | `rank_status="never"`, `battle_cup_tier=5`, `mmr=null` |

For Legend 3 → range `3,080–3,850`, midpoint `3,465`. For Battle Cup tier 5 → range `3,000–4,000`, midpoint `3,500`.

---

## Phase 1 — Backend foundation

### Task 1: Add Dota MMR settings constants

**Files:**
- Modify: `backend/backend/settings.py` (append to bottom of file)

- [ ] **Step 1: Append the three constants to `settings.py`**

```python
# ============================================================================
# Dota 2 medal / battle cup → MMR range mappings
# ----------------------------------------------------------------------------
# Drives the suggestion shown in MmrApprovalModal. Edit + redeploy to update.
# Range is medal-wide (stars do not narrow). Battle cup tier 1 = lowest, 8 =
# Immortal-tier.
# ============================================================================

DOTA_MEDAL_MMR_RANGES = {
    "Herald":   (0,    770),
    "Guardian": (770,  1540),
    "Crusader": (1540, 2310),
    "Archon":   (2310, 3080),
    "Legend":   (3080, 3850),
    "Ancient":  (3850, 4620),
    "Divine":   (4620, 5420),
    "Immortal": (5420, 8000),
}

DOTA_BATTLE_CUP_MMR_RANGES = {
    1: (0,    500),
    2: (500,  1000),
    3: (1000, 2000),
    4: (2000, 3000),
    5: (3000, 4000),
    6: (4000, 5000),
    7: (5000, 6000),
    8: (6000, 8000),
}

DOTA_DEFAULT_MMR_RANGE = (0, 2000)
```

- [ ] **Step 2: Verify Django can load settings**

Run: `just dev::run 'python -c "from django.conf import settings; print(settings.DOTA_MEDAL_MMR_RANGES[\"Legend\"])"'`
Expected: `(3080, 3850)`

- [ ] **Step 3: Commit**

```bash
git add backend/backend/settings.py
git commit -m "feat(events): add Dota medal + battle-cup MMR range settings"
```

---

### Task 2: Write failing tests for `suggest_mmr`

**Files:**
- Create: `backend/events/tests/test_mmr_suggestions.py`

- [ ] **Step 1: Create the test file**

```python
"""Unit tests for events.mmr_suggestions.suggest_mmr."""
from types import SimpleNamespace

import pytest
from django.test import override_settings

from events.mmr_suggestions import suggest_mmr, _parse_medal


def make_profile(rank_status="active", rank_medal="", mmr=None, battle_cup_tier=None):
    """Build a duck-typed stand-in for PlayerDotaProfile."""
    return SimpleNamespace(
        rank_status=rank_status,
        rank_medal=rank_medal,
        mmr=mmr,
        battle_cup_tier=battle_cup_tier,
    )


# ---------- _parse_medal ----------------------------------------------------

def test_parse_medal_with_star():
    assert _parse_medal("Crusader 3") == ("Crusader", 3)


def test_parse_medal_immortal_no_star():
    assert _parse_medal("Immortal") == ("Immortal", 1)


def test_parse_medal_strips_whitespace():
    assert _parse_medal("  Legend 5  ") == ("Legend", 5)


def test_parse_medal_garbage_falls_back_to_star_1():
    assert _parse_medal("Legend nope") == ("Legend", 1)


# ---------- precedence: default value --------------------------------------

def test_prior_approved_wins_over_everything():
    profile = make_profile(rank_medal="Legend 3", mmr=3200)
    result = suggest_mmr(profile, prior_approved_mmr=2400)
    assert result["default"] == 2400
    assert result["default_source"] == "prior"
    assert result["range"] == [3080, 3850]
    assert result["range_source"] == "medal"


def test_self_report_wins_when_no_prior():
    profile = make_profile(rank_medal="Legend 3", mmr=3200)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["default"] == 3200
    assert result["default_source"] == "self_report"
    assert result["range"] == [3080, 3850]


def test_medal_midpoint_when_no_prior_no_self_report():
    profile = make_profile(rank_medal="Crusader 1", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # Crusader range: (1540, 2310) → midpoint 1925
    assert result["default"] == 1925
    assert result["default_source"] == "medal"
    assert result["range"] == [1540, 2310]


def test_battle_cup_midpoint_for_never_ranked():
    profile = make_profile(
        rank_status="never", rank_medal="", battle_cup_tier=5
    )
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # BC tier 5: (3000, 4000) → midpoint 3500
    assert result["default"] == 3500
    assert result["default_source"] == "battle_cup"
    assert result["range"] == [3000, 4000]
    assert result["range_source"] == "battle_cup"


def test_fallback_when_no_profile():
    result = suggest_mmr(profile=None, prior_approved_mmr=None)
    assert result["default"] == 1000  # midpoint of (0, 2000)
    assert result["default_source"] == "fallback"
    assert result["range"] == [0, 2000]
    assert result["range_source"] == "fallback"


def test_fallback_when_profile_has_no_signals():
    profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["default_source"] == "fallback"
    assert result["range_source"] == "fallback"


def test_previous_rank_uses_medal_range():
    profile = make_profile(rank_status="previous", rank_medal="Divine 2", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # Divine range: (4620, 5420) → midpoint 5020
    assert result["default"] == 5020
    assert result["default_source"] == "medal"
    assert result["range"] == [4620, 5420]
    assert result["range_source"] == "medal"


def test_prior_zero_is_treated_as_present():
    """org_user.mmr=0 is not None, so prior takes precedence."""
    profile = make_profile(rank_medal="Legend 3", mmr=3200)
    # Note: get_org_user_mmr nulls out zero MMR before passing in, so this
    # path verifies the function's contract — caller must pre-filter zero
    # if they want it to behave as "absent".
    result = suggest_mmr(profile, prior_approved_mmr=0)
    assert result["default"] == 0
    assert result["default_source"] == "prior"


# ---------- parametric coverage --------------------------------------------

@pytest.mark.parametrize(
    "medal,expected_low,expected_high",
    [
        ("Herald 1",   0,    770),
        ("Guardian 5", 770,  1540),
        ("Crusader 3", 1540, 2310),
        ("Archon 2",   2310, 3080),
        ("Legend 4",   3080, 3850),
        ("Ancient 1",  3850, 4620),
        ("Divine 2",   4620, 5420),
        ("Immortal",   5420, 8000),
    ],
)
def test_all_medals_match_settings_range(medal, expected_low, expected_high):
    profile = make_profile(rank_medal=medal)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["range"] == [expected_low, expected_high]
    assert result["range_source"] == "medal"


@pytest.mark.parametrize(
    "tier,expected_low,expected_high",
    [
        (1, 0,    500),
        (2, 500,  1000),
        (3, 1000, 2000),
        (4, 2000, 3000),
        (5, 3000, 4000),
        (6, 4000, 5000),
        (7, 5000, 6000),
        (8, 6000, 8000),
    ],
)
def test_all_battle_cup_tiers_match_settings_range(tier, expected_low, expected_high):
    profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=tier)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["range"] == [expected_low, expected_high]
    assert result["range_source"] == "battle_cup"
```

- [ ] **Step 2: Run tests to confirm they fail (module doesn't exist yet)**

Run: `just test::run 'python -m pytest events/tests/test_mmr_suggestions.py -v'`
Expected: `ImportError` or `ModuleNotFoundError: No module named 'events.mmr_suggestions'`. All tests fail.

- [ ] **Step 3: Commit failing tests**

```bash
git add backend/events/tests/test_mmr_suggestions.py
git commit -m "test(events): failing tests for suggest_mmr precedence + range tables"
```

---

### Task 3: Implement `events.mmr_suggestions`

**Files:**
- Create: `backend/events/mmr_suggestions.py`

- [ ] **Step 1: Write the module**

```python
"""MMR suggestion logic for the EventSignup approval modal.

Pure functions — no DB access, no Django-model imports. Caller passes a
duck-typed `profile` (the relevant fields of PlayerDotaProfile) and the
`prior_approved_mmr` (OrgUser.mmr, or None).

Settings constants:
    DOTA_MEDAL_MMR_RANGES        — medal name → (low, high)
    DOTA_BATTLE_CUP_MMR_RANGES   — tier (1-8) → (low, high)
    DOTA_DEFAULT_MMR_RANGE       — fallback (low, high)
"""
from typing import Optional

from django.conf import settings


def suggest_mmr(profile, prior_approved_mmr: Optional[int]) -> dict:
    """Compute the values the approval modal needs.

    Returns:
        {
            "default": int,         # form pre-fill
            "default_source": str,  # "prior" | "self_report" | "medal" | "battle_cup" | "fallback"
            "range": [low, high],   # always shown as helper text
            "range_source": str,    # "medal" | "battle_cup" | "fallback"
        }
    """
    range_low, range_high, range_source = _compute_range(profile)

    if prior_approved_mmr is not None:
        default, default_source = prior_approved_mmr, "prior"
    elif profile is not None and profile.mmr is not None:
        default, default_source = profile.mmr, "self_report"
    else:
        default, default_source = (range_low + range_high) // 2, range_source

    return {
        "default": default,
        "default_source": default_source,
        "range": [range_low, range_high],
        "range_source": range_source,
    }


def _compute_range(profile) -> tuple[int, int, str]:
    if profile is not None and profile.rank_medal:
        medal_name, _star = _parse_medal(profile.rank_medal)
        ranges = settings.DOTA_MEDAL_MMR_RANGES
        if medal_name in ranges:
            low, high = ranges[medal_name]
            return low, high, "medal"

    if (
        profile is not None
        and profile.rank_status == "never"
        and profile.battle_cup_tier
    ):
        ranges = settings.DOTA_BATTLE_CUP_MMR_RANGES
        if profile.battle_cup_tier in ranges:
            low, high = ranges[profile.battle_cup_tier]
            return low, high, "battle_cup"

    low, high = settings.DOTA_DEFAULT_MMR_RANGE
    return low, high, "fallback"


def _parse_medal(medal: str) -> tuple[str, int]:
    """'Crusader 3' → ('Crusader', 3); 'Immortal' → ('Immortal', 1)."""
    parts = medal.strip().split(" ", 1)
    name = parts[0]
    star = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    return name, star
```

- [ ] **Step 2: Run tests to confirm they pass**

Run: `just test::run 'python -m pytest events/tests/test_mmr_suggestions.py -v'`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/events/mmr_suggestions.py
git commit -m "feat(events): suggest_mmr — precedence + range derivation"
```

---

### Task 4: Add `suggested_mmr` and `suggested_mmr_range` to `EventSignupSerializer`

**Files:**
- Modify: `backend/events/serializers.py`

- [ ] **Step 1: Read the current `EventSignupSerializer` to find insertion points**

Run: `grep -n "class EventSignupSerializer\|dota_profile = \|org_user_mmr = \|fields = \[" backend/events/serializers.py | head -10`

Note the line numbers for the field declarations and the `Meta.fields` list — you'll insert the two new fields there.

- [ ] **Step 2: Add field declarations next to the existing `org_user_mmr`**

Find the existing block (around line 376–377):

```python
    dota_profile = serializers.SerializerMethodField()
    org_user_mmr = serializers.SerializerMethodField()
```

Replace with:

```python
    dota_profile = serializers.SerializerMethodField()
    org_user_mmr = serializers.SerializerMethodField()
    suggested_mmr = serializers.SerializerMethodField()
    suggested_mmr_range = serializers.SerializerMethodField()
    suggested_mmr_range_source = serializers.SerializerMethodField()
```

- [ ] **Step 3: Add the three new field names to `Meta.fields`**

In the `Meta.fields` list (around line 388–389), find:

```python
            "dota_profile",
            "org_user_mmr",
```

Add the three new field names immediately after:

```python
            "dota_profile",
            "org_user_mmr",
            "suggested_mmr",
            "suggested_mmr_range",
            "suggested_mmr_range_source",
```

- [ ] **Step 4: Add the getter methods at the end of the serializer class**

Insert these methods right after `get_org_user_mmr` (line 446-461), before the next class definition (`class OrgEventDefaultsSerializer` at line 464):

```python
    def get_suggested_mmr(self, obj):
        return self._mmr_suggestion(obj)["default"]

    def get_suggested_mmr_range(self, obj):
        return self._mmr_suggestion(obj)["range"]

    def get_suggested_mmr_range_source(self, obj):
        return self._mmr_suggestion(obj)["range_source"]

    def _mmr_suggestion(self, obj):
        """Memoize the suggest_mmr result per signup instance."""
        if hasattr(obj, "_mmr_suggestion_cache"):
            return obj._mmr_suggestion_cache

        from events.mmr_suggestions import suggest_mmr
        from org.models import OrgUser
        from org.models_profiles import PlayerDotaProfile

        profile = None
        prior_mmr = None
        try:
            org_user = OrgUser.objects.get(
                user=obj.user, organization=obj.event.organization
            )
            prior_mmr = org_user.mmr if org_user.mmr else None
            try:
                profile = PlayerDotaProfile.objects.get(org_user=org_user)
            except PlayerDotaProfile.DoesNotExist:
                profile = None
        except OrgUser.DoesNotExist:
            pass

        obj._mmr_suggestion_cache = suggest_mmr(profile, prior_mmr)
        return obj._mmr_suggestion_cache
```

- [ ] **Step 5: Verify with a quick API ping**

Run: `just test::up && just test::run 'python manage.py shell -c "from events.serializers import EventSignupSerializer; from events.models import EventSignup; s = EventSignup.objects.first(); print(EventSignupSerializer(s).data if s else \"no signups\") "'`
Expected: Either `"no signups"` or a dict containing `suggested_mmr` and `suggested_mmr_range` keys (range as 2-element list).

- [ ] **Step 6: Commit**

```bash
git add backend/events/serializers.py
git commit -m "feat(events): expose suggested_mmr + suggested_mmr_range on EventSignupSerializer"
```

---

### Task 5: Add `set_org_user_approved_mmr` test endpoint

**Files:**
- Modify: `backend/tests/test_events_discord.py`
- Modify: `backend/tests/urls.py`

- [ ] **Step 1: Add the endpoint function to `test_events_discord.py`**

Append to the bottom of `backend/tests/test_events_discord.py`:

```python
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def set_org_user_approved_mmr(request, org_pk: int, user_pk: int):
    """TEST ONLY: Set OrgUser.mmr for (org_pk, user_pk) and invalidate cacheops.

    Body: {"mmr": int}
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from cacheops import invalidate_obj
    from org.models import OrgUser

    try:
        mmr = int(request.data.get("mmr"))
    except (TypeError, ValueError):
        return Response(
            {"detail": "mmr must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        org_user = OrgUser.objects.get(organization_id=org_pk, user_id=user_pk)
    except OrgUser.DoesNotExist:
        return Response(
            {"detail": f"OrgUser org={org_pk} user={user_pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    org_user.mmr = mmr
    org_user.save(update_fields=["mmr"])
    invalidate_obj(org_user)

    return Response({"org_pk": org_pk, "user_pk": user_pk, "mmr": mmr})
```

- [ ] **Step 2: Register the URL in `backend/tests/urls.py`**

Find the `from .test_events_discord import (` import block (around line 32–37):

```python
from .test_events_discord import (
    send_test_notification,
    simulate_discord_signup,
    verify_discord_messages,
)
```

Add `set_org_user_approved_mmr` to the import:

```python
from .test_events_discord import (
    send_test_notification,
    set_org_user_approved_mmr,
    simulate_discord_signup,
    verify_discord_messages,
)
```

Then add a new path entry to `urlpatterns` (anywhere in the list — append after the existing `org/.../reset-admin-team/` entry around line 122–126):

```python
    path(
        "org/<int:org_pk>/user/<int:user_pk>/set-approved-mmr/",
        set_org_user_approved_mmr,
        name="test-set-org-user-approved-mmr",
    ),
```

- [ ] **Step 3: Verify the endpoint responds in the test env**

Run: `just test::up && curl -k -X POST -H 'Content-Type: application/json' -d '{"mmr": 2400}' https://localhost/api/tests/org/7/user/5001/set-approved-mmr/`
Expected: JSON `{"org_pk": 7, "user_pk": 5001, "mmr": 2400}` (or 404 if events org not yet populated — run `just db::populate::all` first).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_events_discord.py backend/tests/urls.py
git commit -m "test(events): add set_org_user_approved_mmr test endpoint"
```

---

## Phase 2 — Frontend foundation

### Task 6: Extend `EventSignupType` schema

**Files:**
- Modify: `frontend/app/components/events/schemas.ts`

- [ ] **Step 1: Locate the schema**

Run: `grep -n "EventSignupType\|export const eventSignupSchema\|org_user_mmr" frontend/app/components/events/schemas.ts | head -10`

- [ ] **Step 2: Add the three fields**

In the `eventSignupSchema` z-object (around line 145), find:

```typescript
  org_user_mmr: z.number().nullable().default(null),
```

Replace with:

```typescript
  org_user_mmr: z.number().nullable().default(null),
  suggested_mmr: z.number().int(),
  suggested_mmr_range: z.tuple([z.number().int(), z.number().int()]),
  suggested_mmr_range_source: z.enum(['medal', 'battle_cup', 'fallback']),
```

The `EventSignupType` type alias (line 154) updates automatically.

- [ ] **Step 3: Run TypeScript check to verify no breakage in importers**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No new errors involving `EventSignupType`. (Pre-existing unrelated errors are fine.)

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/events/schemas.ts
git commit -m "feat(events): add suggested_mmr fields to EventSignupType schema"
```

---

### Task 7: Create `<RankSignalsCard>` component

**Files:**
- Create: `frontend/app/components/events/RankSignalsCard.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { Badge } from '~/components/ui/badge';
import { RolePositions } from '~/components/user/positions';
import { dotaProfileToPositions } from '~/components/user/UserEventStrip';
import type { UserType } from '~/components/user/types';
import type { EventSignupType } from '~/components/events/schemas';

interface RankSignalsCardProps {
  signup: EventSignupType;
}

export function RankSignalsCard({ signup }: RankSignalsCardProps) {
  const profile = signup.dota_profile;
  const priorMmr = signup.org_user_mmr;
  const [rangeLow, rangeHigh] = signup.suggested_mmr_range;

  const positionsUser = profile?.positions
    ? ({ ...({} as UserType), positions: dotaProfileToPositions(profile.positions) } as UserType)
    : null;

  const isPrevious = profile?.rank_status === 'previous';

  return (
    <div
      data-testid="rank-signals"
      className="bg-base-300 border border-border rounded-lg p-4 space-y-2 text-sm"
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        Rank Signals
      </div>

      {/* Previously Approved MMR */}
      <div className="flex justify-between items-center" data-testid="rank-signals-prior-mmr">
        <span className="text-muted-foreground">Previously Approved MMR</span>
        <span className={priorMmr != null ? 'font-mono' : 'text-muted-foreground'}>
          {priorMmr != null ? priorMmr.toLocaleString() : '—'}
        </span>
      </div>

      {/* Self-Reported MMR */}
      <div className="flex justify-between items-center" data-testid="rank-signals-self-report">
        <span className="text-muted-foreground">Self-Reported MMR</span>
        <span className={profile?.mmr != null ? 'font-mono' : 'text-muted-foreground'}>
          {profile?.mmr != null ? profile.mmr.toLocaleString() : '—'}
        </span>
      </div>

      {/* Rank (medal) */}
      <div className="flex justify-between items-center" data-testid="rank-signals-medal">
        <span className="text-muted-foreground">Rank</span>
        {profile?.rank_medal ? (
          <span className="flex items-center">
            <Badge
              variant="outline"
              className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30"
            >
              {profile.rank_medal}
            </Badge>
            <span className="text-xs text-muted-foreground font-mono ml-2">
              {rangeLow.toLocaleString()}&ndash;{rangeHigh.toLocaleString()}
              {isPrevious ? ' (previous)' : ''}
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground">&mdash;</span>
        )}
      </div>

      {/* Battle Cup Tier */}
      <div className="flex justify-between items-center" data-testid="rank-signals-battle-cup">
        <span className="text-muted-foreground">Battle Cup Tier</span>
        {profile?.rank_status === 'never' && profile?.battle_cup_tier != null ? (
          <Badge
            variant="outline"
            className="px-1.5 py-0 text-xs font-medium text-blue-300 border-blue-500/30"
          >
            Tier {profile.battle_cup_tier}
          </Badge>
        ) : (
          <span className="text-muted-foreground">&mdash;</span>
        )}
      </div>

      {/* Positions (only when set) */}
      {positionsUser?.positions && (
        <div
          className="flex justify-between items-center"
          data-testid="rank-signals-positions"
        >
          <span className="text-muted-foreground">Positions</span>
          <RolePositions user={positionsUser} compact disableTooltips />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep RankSignalsCard | head -10`
Expected: No errors involving `RankSignalsCard`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/events/RankSignalsCard.tsx
git commit -m "feat(events): add RankSignalsCard read-only display component"
```

---

### Task 8: Refactor `MmrApprovalModal` to use `RankSignalsCard` + range helper

**Files:**
- Modify: `frontend/app/components/events/MmrApprovalModal.tsx`

- [ ] **Step 1: Remove the local medal table and estimator**

Delete lines 47–65 of the existing file (the `MEDAL_MMR` constant and `estimateMmr` function). After this deletion, the file should no longer reference `MEDAL_MMR` or `estimateMmr`.

- [ ] **Step 2: Update imports**

Add the new import near the existing `~/components/user/UserEventStrip` import (around line 34):

```typescript
import { RankSignalsCard } from '~/components/events/RankSignalsCard';
```

Remove now-unused imports: `RolePositions` (line 33), `dotaProfileToPositions` (line 34) — these moved into `RankSignalsCard`. Verify `Badge` is still used elsewhere in the modal; if not, remove its import too.

- [ ] **Step 3: Replace the `useEffect` default-MMR computation**

Find the block at lines 100–109:

```typescript
  useEffect(() => {
    if (signup && open) {
      const profile = signup.dota_profile;
      const defaultMmr =
        signup.org_user_mmr ??
        profile?.mmr ??
        (profile ? estimateMmr(profile.rank_medal) : 0);
      form.reset({ mmr: defaultMmr });
    }
  }, [signup, open]);
```

Replace with:

```typescript
  useEffect(() => {
    if (signup && open) {
      form.reset({ mmr: signup.suggested_mmr });
    }
  }, [signup, open]);
```

- [ ] **Step 4: Replace the two existing inline blocks with `<RankSignalsCard>`**

Find lines 168–217 (the two `bg-base-300 border border-border rounded-lg ...` divs — `Previously Approved MMR` and `Profile summary`). Delete both blocks entirely.

In their place, insert:

```tsx
        {/* Rank signals — replaces the two prior inline blocks. */}
        <RankSignalsCard signup={signup} />
```

- [ ] **Step 5: Add the suggested-range helper under the MMR input**

Find the `<FormField name="mmr" ...>` block (around lines 236–290). Inside the `render` function, locate the existing `mmrDelta` callout block (the `{mmrDelta != null && mmrDelta !== 0 && ( ... )}` block).

Immediately before that block, add:

```tsx
                  <p
                    data-testid="suggested-range-helper"
                    className="text-xs text-muted-foreground font-mono mt-1"
                  >
                    Suggested range:{' '}
                    {signup.suggested_mmr_range[0].toLocaleString()}&ndash;
                    {signup.suggested_mmr_range[1].toLocaleString()}
                    <span className="ml-1 text-muted-foreground/80">
                      (from{' '}
                      {signup.suggested_mmr_range_source === 'battle_cup'
                        ? 'battle cup'
                        : signup.suggested_mmr_range_source}
                      )
                    </span>
                  </p>
```

Also locate the `<Input type="number" ...>` element inside the same `FormField` (around line 244). Add a `data-testid` attribute so Playwright can select it without falling back to a CSS attribute selector (per the testing skill's data-testid rule):

```tsx
                    <Input
                      type="number"
                      placeholder="e.g. 3000"
                      data-testid="mmr-input"
                      {...field}
                      onChange={(e) => field.onChange(e.target.valueAsNumber || 0)}
                    />
```

- [ ] **Step 6: Remove `positionsUser` and `screenshotUrl` derivations that were used only by the deleted blocks**

Re-read the file. Any local variables or expressions that are now unreferenced (`positionsUser`, parts of `rankStatusBadge` that referenced removed UI) should be deleted. Keep the screenshot section intact — it stays where it is below the (now deleted) profile summary block.

- [ ] **Step 7: TypeScript check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -i "MmrApprovalModal\|RankSignalsCard" | head -20`
Expected: No errors involving these files.

- [ ] **Step 8: Smoke-test the modal in the dev environment**

Run: `just dev::debug` in one terminal. In another, navigate to a Dota event signups admin page and open the approval modal for an existing signup. Confirm visually:
- "Rank Signals" heading is visible.
- Four rows render (em-dash for missing values).
- Helper text "Suggested range: low–high" appears under the MMR input.
- Approve/Reject/Close buttons still work.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/components/events/MmrApprovalModal.tsx
git commit -m "feat(events): MmrApprovalModal renders RankSignalsCard + suggested range helper"
```

---

## Phase 3 — Test wiring

### Task 9: Add `loginEventPlayer4` and `setApprovedMmr` Playwright helpers

**Files:**
- Modify: `frontend/tests/playwright/fixtures/events.ts`
- Modify: `frontend/tests/playwright/fixtures/index.ts`

- [ ] **Step 1: Add helpers to `events.ts`**

After the existing `loginEventPlayer` function (around line 140), append:

```typescript
/** Login as event_player_4 (pk=5004) — rank_status="never", battle_cup_tier=5. */
export async function loginEventPlayer4(context: BrowserContext) {
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: 5004 },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`Login event player 4 failed: ${resp.status()}`);
  return resp.json();
}

/** TEST: Set OrgUser.mmr for a given (orgPk, userPk). Invalidates cacheops. */
export async function setApprovedMmr(
  context: BrowserContext,
  orgPk: number,
  userPk: number,
  mmr: number,
) {
  const resp = await context.request.post(
    `${API_URL}/tests/org/${orgPk}/user/${userPk}/set-approved-mmr/`,
    {
      data: { mmr },
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!resp.ok()) {
    throw new Error(`setApprovedMmr failed: ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}
```

- [ ] **Step 2: Re-export from `index.ts`**

Find the `// Events utilities` block (around line 117–130) and add the two new names to the export list:

```typescript
export {
  getEventsTestData,
  resetEventsData,
  triggerEventGeneration,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  setApprovedMmr,
  postWithCsrf,
  patchWithCsrf,
  syncDiscordEvents,
  simulateDiscordSignup,
  verifyDiscordMessages,
  sendTestNotification,
  EVENTS_ORG_NAME,
  ...
} from './events';
```

(Preserve any other names that already follow `EVENTS_ORG_NAME` in the existing block.)

- [ ] **Step 3: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -i "loginEventPlayer4\|setApprovedMmr" | head -10`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/fixtures/events.ts frontend/tests/playwright/fixtures/index.ts
git commit -m "test(events): add loginEventPlayer4 + setApprovedMmr playwright helpers"
```

---

### Task 10: Augment existing approval test + add 2 sibling tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/04-discord-integration.spec.ts`

- [ ] **Step 1: Augment the existing "approve via MMR modal" test**

Find the existing test that ends at line 318 (the one that approves an `event_player_1` signup with Legend 3 / 3,200 MMR). After step 8 (line 300 `await expect(dialog.getByText('Legend 3')).toBeVisible();`), add the new Rank Signals assertions before the existing `await mmrInput.fill('3500');`:

```typescript
    // 8b. Verify the new Rank Signals card renders all four signal rows
    await expect(dialog.getByTestId('rank-signals')).toBeVisible();
    await expect(dialog.getByTestId('rank-signals-self-report')).toContainText('3,200');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('Legend 3');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('3,080');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('3,850');
    await expect(dialog.getByTestId('rank-signals-battle-cup')).toContainText('—');
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      '3,080–3,850',
    );
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      'from medal',
    );

    // 8c. The MMR input should pre-fill with self-report (3200) since
    // event_player_1 has no prior approved MMR. Use the new data-testid
    // (mmr-input) instead of the [type=number] CSS locator the prior version
    // of this test used.
    await expect(dialog.getByTestId('mmr-input')).toHaveValue('3200');
```

- [ ] **Step 2: Update the import block at the top of the file**

Find the existing imports from `'../../fixtures'` and add the two new helpers:

```typescript
import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  setApprovedMmr,
  postWithCsrf,
  // ... preserve other existing imports
} from '../../fixtures';
```

- [ ] **Step 3: Add the prior-approved precedence sibling test**

Inside the same `test.describe(...)` block as the existing approval test, append:

```typescript
  test('approval modal — prior-approved MMR pre-fills input over self-report', async ({
    context,
    page,
  }) => {
    // Setup: create a fresh Dota event, RSVP as player 1, then set their
    // OrgUser.mmr=2400 BEFORE the admin opens the approval modal.
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Prior MMR Precedence Event',
      description: 'Tests prior-approved MMR pre-fills',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Prior MMR Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/rsvp/`);
    expect(rsvpResp.ok()).toBeTruthy();

    // Set prior approved MMR before opening modal
    await setApprovedMmr(context, eventInfo.orgPk, 5001, 2400);

    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByText('EventPlayer1')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: 'Approve' }).first().click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Prior-approved row shows 2,400; medal range still shows alongside.
    await expect(dialog.getByTestId('rank-signals-prior-mmr')).toContainText('2,400');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('Legend 3');
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      '3,080–3,850',
    );

    // Input pre-fills with prior (2,400), not self-report (3,200).
    await expect(dialog.getByTestId('mmr-input')).toHaveValue('2400');

    await dialog.getByTestId('mmr-modal-close').click();
  });
```

- [ ] **Step 4: Add the battle-cup path sibling test**

Append a third test inside the same `test.describe(...)` block:

```typescript
  test('approval modal — battle cup tier path shows BC range, no medal', async ({
    context,
    page,
  }) => {
    // event_player_4 has rank_status="never" + battle_cup_tier=5 from populate.
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Battle Cup Path Event',
      description: 'Tests battle-cup MMR range surface',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'BC Path Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await loginEventPlayer4(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/rsvp/`);
    expect(rsvpResp.ok()).toBeTruthy();

    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByText('EventPlayer4')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: 'Approve' }).first().click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Medal row is em-dash (no medal), BC row shows Tier 5.
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('—');
    await expect(dialog.getByTestId('rank-signals-battle-cup')).toContainText('Tier 5');

    // Helper text reflects BC range 3,000–4,000 with source label.
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      '3,000–4,000',
    );
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      'from battle cup',
    );

    // Input pre-fills with BC midpoint (3,500) since no prior + no self-report.
    await expect(dialog.getByTestId('mmr-input')).toHaveValue('3500');

    await dialog.getByTestId('mmr-modal-close').click();
  });
```

- [ ] **Step 5: Run the three tests in headless mode**

Run: `just test::pw::headless --grep "approval modal|approve via MMR modal"`

Expected: All three tests pass. If a test fails because pre-existing state isn't reset, run `just db::populate::all` between iterations.

> **NOTE:** Per the testing skill, do NOT spawn headed Playwright. If a test fails, read the artifacts (`test-results/.../error-context.md`, `test-results/.../trace.zip`) instead.

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/playwright/e2e/16-events/04-discord-integration.spec.ts
git commit -m "test(events): cover Rank Signals card + range helper across 3 paths"
```

---

## Phase 4 — Discord MedalSelect race fix (Crusader 4 → Herald 4 bug)

### Task 11: Plumb `rank_status` through `MedalSelect`

**Files:**
- Modify: `backend/discordbot/components.py`

**Why:** When `MedalSelect.callback` rebuilds the view (Task 12), it must reconstruct `RankDetailsView` with the correct `rank_status` ("active" vs "previous"). Today `MedalSelect` doesn't carry that field, so the bot.py handler hardcoded `rank_status="active"` — losing the "previous" branch. We move the rebuild into the callback and need rank_status accessible on `self`.

- [ ] **Step 1: Add constructor params to `MedalSelect`**

Find `class MedalSelect` at line 719:

```python
class MedalSelect(ui.Select):
    """Select menu for rank medal."""

    def __init__(self, event_id):
        super().__init__(
            placeholder="Select your medal",
            custom_id=f"rank_medal:{event_id}",
            min_values=1,
            max_values=1,
            options=_medal_options(),
        )
        self.event_id = event_id
```

Replace with:

```python
class MedalSelect(ui.Select):
    """Select menu for rank medal."""

    def __init__(self, event_id, rank_status="active", require_screenshot=False):
        super().__init__(
            placeholder="Select your medal",
            custom_id=f"rank_medal:{event_id}",
            min_values=1,
            max_values=1,
            options=_medal_options(),
        )
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
```

- [ ] **Step 2: Pass `rank_status` and `require_screenshot` from `RankDetailsView`**

Find `RankDetailsView.__init__` body (around lines 703–712). Replace:

```python
        if rank_status in ("active", "previous"):
            self.add_item(MedalSelect(event_id))
            self.add_item(
                StarSelect(
                    event_id,
                    rank_status,
                    require_screenshot=require_screenshot,
                    selected_medal=selected_medal,
                )
            )
```

with:

```python
        if rank_status in ("active", "previous"):
            self.add_item(
                MedalSelect(
                    event_id,
                    rank_status=rank_status,
                    require_screenshot=require_screenshot,
                )
            )
            self.add_item(
                StarSelect(
                    event_id,
                    rank_status,
                    require_screenshot=require_screenshot,
                    selected_medal=selected_medal,
                )
            )
```

- [ ] **Step 3: Verify nothing imports/calls `MedalSelect(event_id)` positionally**

Run: `grep -rn "MedalSelect(" backend/discordbot/ backend/events/ backend/tests/ 2>/dev/null`
Expected: All call sites pass keyword args (or zero call sites outside `RankDetailsView`). New positional-only signature `MedalSelect(event_id)` still works because the new params have defaults.

- [ ] **Step 4: Commit**

```bash
git add backend/discordbot/components.py
git commit -m "fix(discord): plumb rank_status + require_screenshot through MedalSelect"
```

---

### Task 12: Move view-rebuild from bot.py into `MedalSelect.callback`

**Files:**
- Modify: `backend/discordbot/components.py` (`MedalSelect.callback`)
- Modify: `backend/discordbot/bot.py` (remove the `rank_medal:` handler branch)

**Why (the race):** When the user picks a medal, two paths fire on the same interaction:
1. `MedalSelect.callback` (line 732): `await interaction.response.defer()`.
2. `bot.on_interaction` `rank_medal:` branch (`bot.py` lines 268–285): tries to rebuild the view via `interaction.response.edit_message`.

The component callback runs first and `defer()` marks the interaction as already responded. The bot.py `edit_message` then either errors silently or no-ops. The view never gets rebuilt with the new medal in `StarSelect.custom_id`. When the user picks a star, `StarSelect.callback` reads `parts[2]="Herald"` (the initial default), falls back to scanning `MedalSelect.values` from `self.view.children` — but `Select.values` is per-interaction and is empty in a *different* interaction context. Result: every signup gets "Herald N".

The fix collapses the two paths into one: `MedalSelect.callback` itself does the rebuild, and the bot.py handler goes away.

- [ ] **Step 1: Rewrite `MedalSelect.callback`**

Find at `backend/discordbot/components.py` line 732–733:

```python
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
```

Replace with:

```python
    async def callback(self, interaction: discord.Interaction):
        """Rebuild RankDetailsView so StarSelect.custom_id encodes the picked medal.

        Without this, the bug at b/discordbot/bot.py:268-285 (rank_medal: handler)
        races with this callback — defer() wins, bot.py never gets to edit_message,
        and StarSelect keeps custom_id=rank_star:{event_id}:Herald. Doing the rebuild
        here removes the race.
        """
        medal = self.values[0] if self.values else "Herald"
        view = RankDetailsView(
            self.event_id,
            rank_status=self.rank_status,
            require_screenshot=self.require_screenshot,
            selected_medal=medal,
        )
        label = "Rank" if self.rank_status == "active" else "Previous rank"
        await interaction.response.edit_message(
            content=f"\U0001f3c5 {label}: **{medal}** — now pick your star:",
            view=view,
        )
```

- [ ] **Step 2: Remove the `rank_medal:` branch from `bot.on_interaction`**

In `backend/discordbot/bot.py`, find lines 268–285:

```python
            elif custom_id.startswith("rank_medal:"):
                # Medal selected — update the star select custom_id to encode the medal
                event_id = int(custom_id.split(":")[1])
                medal_values = interaction.data.get("values", [])
                medal = medal_values[0] if medal_values else "Herald"

                from discordbot.components import RankDetailsView

                # Rebuild the view with the medal encoded in star select
                view = RankDetailsView(
                    event_id,
                    rank_status="active",
                    selected_medal=medal,
                )
                await interaction.response.edit_message(
                    content=f"\U0001f3c5 Selected **{medal}** — now pick your star:",
                    view=view,
                )
```

Delete the entire `elif` block. The next branch (`elif custom_id.startswith("rank_star:"):` at line 286) becomes the new branch following the previous `elif`.

- [ ] **Step 3: Verify the bot still loads**

Run: `just test::run 'python -c "from discordbot import bot; print(\"ok\")"'`
Expected: `ok` (no import errors).

- [ ] **Step 4: Commit**

```bash
git add backend/discordbot/components.py backend/discordbot/bot.py
git commit -m "fix(discord): MedalSelect rebuilds view directly, removes Herald race"
```

---

### Task 13: Unit test the medal-encoding fix

**Files:**
- Modify: `backend/discordbot/tests/test_components.py`

- [ ] **Step 1: Read the existing test file to follow its mock conventions**

Run: `grep -n "^def\|^class\|MedalSelect\|StarSelect\|AsyncMock\|MagicMock" backend/discordbot/tests/test_components.py | head -30`

Use the same mocking style (probably `unittest.mock.AsyncMock` / `MagicMock`).

- [ ] **Step 2: Append the test class**

```python
"""Regression test for the MedalSelect → StarSelect medal-encoding race.

Verifies that picking "Crusader" in MedalSelect rebuilds the view such that
StarSelect.custom_id is `rank_star:{event_id}:Crusader` — NOT the initial
default of `rank_star:{event_id}:Herald`. Without the fix in
backend/discordbot/components.py:MedalSelect.callback, this test would fail.
"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from discordbot.components import MedalSelect, RankDetailsView, StarSelect


class TestMedalSelectRebuildsView(IsolatedAsyncioTestCase):
    async def test_callback_rebuilds_view_with_medal_in_star_custom_id(self):
        event_id = 42
        medal = MedalSelect(
            event_id, rank_status="active", require_screenshot=False
        )
        # discord.py populates `values` from the user's selection before callback fires
        medal._values = ["Crusader"]  # private attr used by ui.Select

        # Mock the interaction.response.edit_message
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await medal.callback(interaction)

        # edit_message must have been called once
        interaction.response.edit_message.assert_awaited_once()
        kwargs = interaction.response.edit_message.call_args.kwargs

        # The new view must contain a StarSelect with custom_id encoding "Crusader"
        view = kwargs["view"]
        star_selects = [c for c in view.children if isinstance(c, StarSelect)]
        self.assertEqual(len(star_selects), 1)
        self.assertEqual(
            star_selects[0].custom_id, f"rank_star:{event_id}:Crusader"
        )

        # Content includes the medal name
        self.assertIn("Crusader", kwargs["content"])

    async def test_callback_preserves_previous_rank_status(self):
        event_id = 99
        medal = MedalSelect(
            event_id, rank_status="previous", require_screenshot=False
        )
        medal._values = ["Divine"]

        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await medal.callback(interaction)

        kwargs = interaction.response.edit_message.call_args.kwargs
        # Label should say "Previous rank", not "Rank"
        self.assertIn("Previous rank", kwargs["content"])
        # Rebuilt view's StarSelect should still be in active/previous mode
        view = kwargs["view"]
        star = next(c for c in view.children if isinstance(c, StarSelect))
        self.assertEqual(star.rank_status, "previous")
```

- [ ] **Step 3: Run the test to confirm it passes against the fix**

Run: `just test::run 'python -m pytest discordbot/tests/test_components.py::TestMedalSelectRebuildsView -v'`
Expected: Both tests PASS.

- [ ] **Step 4: Sanity check — run the full discordbot test suite**

Run: `just test::run 'python -m pytest discordbot/tests/ -v'`
Expected: No regressions.

- [ ] **Step 5: Commit**

```bash
git add backend/discordbot/tests/test_components.py
git commit -m "test(discord): regression test for MedalSelect medal-encoding rebuild"
```

---

## Phase 5 — Discord event reminder signup count fix (issue #188)

### Task 14: Fix `build_signup_reminder_embed` showing `0/∞` instead of real count

**Files:**
- Modify: `backend/events/discord/embeds.py` (`_build_reminder_embed` line ~434, `build_signup_reminder_embed` line ~523)
- Modify: `backend/events/tests/test_services.py` (or appropriate existing embed-test file — verify in step 1)

**Why:** Issue [#188](https://github.com/kettleofketchup/DraftForge/issues/188) — the Discord event reminder shows `Signups 0/∞ players` even when 13+ players are signed up. Both reminder builders read `active = getattr(event, "signup_count", 0)`. `signup_count` is a *serializer-computed* field (`backend/events/serializers.py:161`), NOT a model attribute on `Event`. When `tasks.py` and the Discord post helpers call these builders with a raw ORM `Event` instance, `getattr` falls through to the default `0` every time. The same module already defines `_signup_counts(event)` at line 40 (used at line 383 in `build_announcement_embeds`) — the reminder builders should call it too.

- [ ] **Step 1: Find the existing reminder-embed test (if any) for the test location**

Run: `grep -rn "build_signup_reminder_embed\|build_attendance_reminder_embed\|_build_reminder_embed\|signup_reminder" backend/events/tests/ backend/tests/ 2>/dev/null | head -10`

Pick the file already containing the closest neighbor; if no test exists, create `backend/events/tests/test_reminder_embeds.py`.

- [ ] **Step 2: Write the failing test**

If creating a new file, add this content. If extending an existing test file, append the test class:

```python
"""Regression test for issue #188 — reminder embed showed 0/∞ instead of actual count."""
from django.test import TestCase

from events.discord.embeds import (
    build_signup_reminder_embed,
    _build_reminder_embed,
)
from events.models import Event, EventSignup
from events.tests.factories import (
    create_test_event,
    create_test_signup,  # adapt to whatever factory helpers exist; otherwise inline-create
)


class TestReminderEmbedSignupCount(TestCase):
    def test_signup_reminder_shows_active_signup_count(self):
        """Issue #188: build_signup_reminder_embed must show real signup count."""
        event = create_test_event(max_players=None)  # max_players=None → ∞ display
        for _ in range(13):
            create_test_signup(event=event, status="approved")  # active status

        result = build_signup_reminder_embed(event)

        # The Signups field value should be **13/∞** players
        signups_field = next(
            f for f in result["embed"]["fields"] if f["name"] == "Signups"
        )
        self.assertEqual(signups_field["value"], "**13/∞** players")

        # The description text used by build_signup_reminder_embed itself
        # also shows the count — this catches the second getattr at line 523.
        self.assertIn("13/∞", result["embed"]["description"])

    def test_reminder_embed_excludes_cancelled_and_waitlisted(self):
        """Active count must exclude cancelled, rejected, waitlisted signups."""
        event = create_test_event(max_players=10)
        for _ in range(5):
            create_test_signup(event=event, status="approved")
        create_test_signup(event=event, status="cancelled")
        create_test_signup(event=event, status="rejected")
        create_test_signup(event=event, status="waitlisted")

        result = build_signup_reminder_embed(event)
        signups_field = next(
            f for f in result["embed"]["fields"] if f["name"] == "Signups"
        )
        self.assertEqual(signups_field["value"], "**5/10** players")
```

> **Adapt the factory helpers** to whatever the events test suite already provides. Look at one of the existing tests in `backend/events/tests/test_services.py` for the pattern. If no factory helpers exist, inline-create the `Organization`, `Event`, and `EventSignup` rows directly in `setUp` — the goal is just having an event with N active signups.

- [ ] **Step 3: Run the new tests to confirm they fail with the current (buggy) code**

Run: `just test::run 'python -m pytest events/tests/test_reminder_embeds.py -v'` (adjust path if you appended to an existing file).
Expected: Both tests FAIL with assertion errors showing `**0/...** players` rather than `**13/...**` / `**5/10**`.

- [ ] **Step 4: Apply the fix in `_build_reminder_embed`**

Find `backend/events/discord/embeds.py` line 434:

```python
    url = _event_url(event)
    active = getattr(event, "signup_count", 0)
    max_display = str(event.max_players) if event.max_players else "∞"
```

Replace with:

```python
    url = _event_url(event)
    active, _confirmed = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "∞"
```

- [ ] **Step 5: Apply the same fix in `build_signup_reminder_embed`**

Find line 523:

```python
def build_signup_reminder_embed(event):
    active = getattr(event, "signup_count", 0)
    max_display = str(event.max_players) if event.max_players else "∞"
```

Replace with:

```python
def build_signup_reminder_embed(event):
    active, _confirmed = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "∞"
```

- [ ] **Step 6: Re-run the new tests — they should now pass**

Run: `just test::run 'python -m pytest events/tests/test_reminder_embeds.py -v'`
Expected: Both tests PASS.

- [ ] **Step 7: Run the full events test suite to confirm no regressions**

Run: `just test::run 'python -m pytest events/ -v'`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/events/discord/embeds.py backend/events/tests/test_reminder_embeds.py
git commit -m "fix(discord): reminder embed shows real signup count (issue #188)" -m "Both _build_reminder_embed and build_signup_reminder_embed read event.signup_count via getattr with a default of 0 — but signup_count is a serializer-computed field, not a model attribute. On a raw ORM Event the getattr always returned 0, producing 'Signups 0/∞ players' regardless of actual signups. Switch to the existing _signup_counts(event) helper that queries EventSignup.status directly and excludes cancelled/rejected/waitlisted."
```

---

## Phase 6 — Verification

### Task 15: Full backend + frontend verification pass

- [ ] **Step 1: Backend unit tests**

Run: `just test::run 'python -m pytest events/tests/test_mmr_suggestions.py -v'`
Expected: All tests PASS.

- [ ] **Step 2: Backend full events + discordbot test suite**

Run: `just test::run 'python -m pytest events/ discordbot/ -v'`
Expected: No regressions in existing tests; new MedalSelect tests from Task 13 pass.

- [ ] **Step 3: Playwright events suite**

Run: `just test::pw::headless --grep events`
Expected: All passing.

- [ ] **Step 4: Frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors compared to baseline.

- [ ] **Step 5: Manual visual smoke (admin modal)**

Run: `just dev::debug`. Open the approval modal for any Dota event signup. Confirm:
- Rank Signals card replaces the two old blocks (no duplicate "Previously Approved MMR" / profile summary).
- Theming matches existing modal (slate background, muted labels, monospace numerics).
- Helper text reads "Suggested range: low–high (from medal | battle cup | fallback)".
- Approve/Reject still work; success toast appears.

- [ ] **Step 6: Manual Discord smoke (Phase 4 medal-select fix)**

In a Discord server with the bot installed, run a Dota signup flow end-to-end:
1. Click signup, fill the modal (friend ID + rank_status="active").
2. Pick **Crusader** in the medal dropdown.
3. Pick **4** in the star dropdown.
4. Confirm the resulting profile shows `Crusader 4`, NOT `Herald 4`.

Repeat with rank_status="previous" + medal **Divine** + star **3**: confirm `Divine 3` (not Herald 3) and that the prompt label says "Previous rank" rather than "Rank".

- [ ] **Step 7: Manual Discord smoke (Phase 5 reminder count fix, issue #188)**

In a test Discord server, create an event with a signup reminder configured, RSVP a few accounts, then trigger the reminder (either by waiting or by manually invoking the celery task). Confirm the embed shows the actual signup count (e.g., `**3/∞** players`) — not `**0/∞** players`.

Faster alternative: in a Django shell, build the embed directly and inspect:

```bash
just dev::run 'python manage.py shell -c "
from events.discord.embeds import build_signup_reminder_embed
from events.models import Event
e = Event.objects.exclude(signups=None).first()
print(build_signup_reminder_embed(e)[\"embed\"][\"fields\"][1][\"value\"])
"'
```

The output should match `**N/...** players` where N is the actual active signup count.

- [ ] **Step 8: Final commit if any fixes were needed**

If steps 1–6 surfaced regressions, fix and commit. Otherwise no commit needed.

---

## Self-review

**Spec coverage (MMR range feature):**
- Settings constants → Task 1 ✓
- `suggest_mmr` precedence + range → Tasks 2–3 ✓
- Serializer fields → Task 4 ✓
- Test endpoint with cacheops invalidation → Task 5 ✓
- Schema additions → Task 6 ✓
- `<RankSignalsCard>` extracted component with theming classes → Task 7 ✓
- Modal refactor (delete two blocks, add card + helper, add mmr-input testid) → Task 8 ✓
- Playwright fixtures → Task 9 ✓
- Augment existing test + 2 sibling tests → Task 10 ✓
- Backend unit tests for all precedence + range paths → Task 2 (parametric coverage) ✓

**Bug fix coverage (Discord MedalSelect race — Phase 4):**
- Plumb `rank_status` through MedalSelect → Task 11 ✓
- Move view-rebuild from bot.py into MedalSelect.callback (eliminates the defer/edit_message race) → Task 12 ✓
- Remove the now-dead `rank_medal:` branch from bot.on_interaction → Task 12 step 2 ✓
- Regression test that `MedalSelect.callback` produces a `StarSelect` whose `custom_id` encodes the picked medal (not "Herald") → Task 13 ✓
- Preserve "previous" rank_status through the rebuild → Task 13 second test ✓

**Bug fix coverage (issue #188 reminder embed — Phase 5):**
- `_build_reminder_embed` uses real signup count, not stale `getattr` default → Task 14 step 4 ✓
- `build_signup_reminder_embed` description string also uses real count → Task 14 step 5 ✓
- Regression test for both code paths and exclusion of cancelled/waitlisted → Task 14 step 2 ✓

**Placeholder scan:** No "TBD", no "implement later", every code step has a complete code block.

**Type/symbol consistency:**
- `suggest_mmr` returns dict with keys `default`, `default_source`, `range`, `range_source` — used consistently in Task 3 (impl), Task 4 (serializer exposes `range_source` via `get_suggested_mmr_range_source`), Task 6 (schema field `suggested_mmr_range_source`), Task 8 step 5 (helper-text `from ${source}` label).
- `loginEventPlayer4` (Task 9) used in Task 10 ✓
- `setApprovedMmr(context, orgPk, userPk, mmr)` signature consistent between Tasks 9 and 10 ✓
- `data-testid` selectors (`rank-signals`, `rank-signals-prior-mmr`, `rank-signals-self-report`, `rank-signals-medal`, `rank-signals-battle-cup`, `rank-signals-positions`, `suggested-range-helper`, `mmr-input`) match between Task 7 (component), Task 8 step 5 (input testid), and Task 10 (assertions) ✓
- Test data: `event_player_1` (pk=5001, Legend 3, MMR 3200) and `event_player_4` (pk=5004, BC tier 5) match the actual `populate_events_data` ✓

**Skill-driven adjustments from review:**
- **Spec UX section says** the helper reads `Suggested range: low–high (from medal | battle cup | fallback)`. Plan exposes `suggested_mmr_range_source` through Tasks 4/6 and renders the source parenthetical in Task 8 step 5; Task 10 asserts `'from medal'` and `'from battle cup'` text in helper.
- **Testing skill rule:** "Always use data-testid for element interaction." Task 8 step 5 adds `data-testid="mmr-input"` to the existing `<Input>`; Task 10 uses `dialog.getByTestId('mmr-input')` instead of the legacy `dialog.locator('input[type="number"]')` CSS selector.

**Out-of-spec deviation:** Spec said add new `event_player_2` with battle_cup_tier=4. Plan reuses existing `event_player_4` with tier 5 (range 3,000–4,000) instead — same code path exercised, no populate changes needed. Adjust assertions accordingly (Task 10 step 4).
