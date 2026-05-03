# Discord Dota MMR Range Suggestions & Customizable Medal→MMR System

**Date:** 2026-05-03
**Status:** Design
**Related spec (separate):** Discord medal-select bug fix (rank_medal/StarSelect race condition) — to be written next.

## Summary

Replace the hardcoded `MEDAL_MMR` constant in `MmrApprovalModal.tsx` with a customizable, settings-driven medal→MMR system that surfaces an MMR **range** (not just a point estimate) to admins approving event signups. Always pre-fill the input with the previously approved MMR when present, and always display all available rank signals (prior approved, self-reported, medal, battle cup) so admins can sanity-check the suggestion.

## Problem

The current `MmrApprovalModal` has three issues:

1. **Hardcoded medal→MMR table in TypeScript.** `MEDAL_MMR` lives in `frontend/app/components/events/MmrApprovalModal.tsx` and pre-fills a single integer per medal. Updating the table requires a frontend deploy.
2. **No range guidance.** The modal pre-fills a point estimate (e.g., Herald 1 → 200) and shows no information about the MMR band that medal actually represents (~0–770), so admins can't tell whether the suggestion is a sane midpoint or a low-bound underestimate.
3. **Bad signal hierarchy when ranks are misclicked or stale.** Many signups currently land with `rank_medal="Herald N"` regardless of the user's actual rank — partly user error, partly a known Discord bug being addressed in a separate spec. Admins approving these need to see *all* available rank signals (self-reported MMR, prior approved MMR, medal range) at once to land on a sensible value.

## Non-goals

- Changing the DB representation of approved MMR (still a single integer on `OrgUser`).
- Per-org or per-event MMR customization. Site-wide settings only.
- Periodic prompts that nudge users to refresh stale MMR. Self-report still happens at signup time as today.
- Fixing the Discord rank_medal race condition that mislabels picks as Herald — that's a separate spec.

## Approach

**Server-side computation, client-side display.** The signup serializer computes `suggested_mmr` (default for the input) and `suggested_mmr_range` (helper text bounds) using site-wide settings constants. The modal displays the values and renders a "Rank Signals" block summarizing all available signals.

Rationale: keeping the precedence logic in Python keeps it testable in isolation, avoids drift between frontend and backend constants, and future-proofs for the case where the Discord bot or other backend code wants to use the same suggestion logic (e.g., to validate that `event.min_mmr` matches a sane bracket).

## Data shape

### Settings constants

`backend/backend/settings.py`:

```python
# Medal name → (low, high) MMR range. Range is medal-wide; star is not narrowed.
DOTA_MEDAL_MMR_RANGES = {
    "Herald":    (0,    770),
    "Guardian":  (770,  1540),
    "Crusader":  (1540, 2310),
    "Archon":    (2310, 3080),
    "Legend":    (3080, 3850),
    "Ancient":   (3850, 4620),
    "Divine":    (4620, 5420),
    "Immortal":  (5420, 8000),
}

# Battle Cup tier (1 = lowest, 8 = Immortal-tier) → (low, high) MMR range.
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

# Fallback when no medal and no battle cup are available.
DOTA_DEFAULT_MMR_RANGE = (0, 2000)
```

Customization workflow: edit settings → deploy. No DB model, no admin UI in this spec.

### Suggestion module

New file: `backend/events/mmr_suggestions.py`

```python
from django.conf import settings


def suggest_mmr(profile, prior_approved_mmr) -> dict:
    """
    Compute the values the approval modal needs.

    Returns:
        {
            "default": int,                  # form pre-fill
            "default_source": str,           # "prior" | "self_report" | "medal" | "battle_cup" | "fallback"
            "range": [low, high],            # always shown as helper text
            "range_source": str,             # "medal" | "battle_cup" | "fallback"
        }
    """
    range_low, range_high, range_source = _compute_range(profile)

    if prior_approved_mmr is not None:
        default, default_source = prior_approved_mmr, "prior"
    elif profile and profile.mmr is not None:
        default, default_source = profile.mmr, "self_report"
    else:
        default, default_source = (range_low + range_high) // 2, range_source

    return {
        "default": default,
        "default_source": default_source,
        "range": [range_low, range_high],
        "range_source": range_source,
    }


def _compute_range(profile):
    if profile and profile.rank_medal:
        medal_name, _star = _parse_medal(profile.rank_medal)
        if medal_name in settings.DOTA_MEDAL_MMR_RANGES:
            low, high = settings.DOTA_MEDAL_MMR_RANGES[medal_name]
            return low, high, "medal"

    if profile and profile.rank_status == "never" and profile.battle_cup_tier:
        if profile.battle_cup_tier in settings.DOTA_BATTLE_CUP_MMR_RANGES:
            low, high = settings.DOTA_BATTLE_CUP_MMR_RANGES[profile.battle_cup_tier]
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

Precedence rules:
- **Default value:** `prior_approved_mmr` → self-reported `profile.mmr` → range midpoint.
- **Range:** medal (regardless of `rank_status`) → battle cup tier (only when `rank_status="never"`) → fallback.
- Range is **medal-wide**: `Crusader 1` and `Crusader 5` both display `1,540–2,310`. Per-star precision adds noise without value.

### Serializer

`backend/events/serializers.py` — `EventSignupSerializer` adds two read-only computed fields. Reuse the same `OrgUser` + `PlayerDotaProfile` lookup pattern already used by `get_dota_profile` (line 418) and `get_org_user_mmr` (line 446).

```python
suggested_mmr        = serializers.SerializerMethodField()  # int
suggested_mmr_range  = serializers.SerializerMethodField()  # [low, high]

def get_suggested_mmr(self, obj):
    return self._suggestion(obj)["default"]

def get_suggested_mmr_range(self, obj):
    return self._suggestion(obj)["range"]

def _suggestion(self, obj):
    # Memoize per-instance so we only call suggest_mmr once per signup.
    if hasattr(obj, "_mmr_suggestion_cache"):
        return obj._mmr_suggestion_cache

    from org.models import OrgUser
    from org.models_profiles import PlayerDotaProfile
    from events.mmr_suggestions import suggest_mmr

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

The `OrgUser` and `PlayerDotaProfile` queries duplicate the work `get_dota_profile` and `get_org_user_mmr` already do per signup. If profiling shows N+1 pressure on signup-list endpoints, factor the lookup into a single helper that all three methods share via the per-instance cache. Not in scope for this spec.

## Modal UX

`frontend/app/components/events/MmrApprovalModal.tsx`:

1. Delete the local `MEDAL_MMR` constant and `estimateMmr()` function.
2. Read the form default from `signup.suggested_mmr`.
3. Add a "Rank Signals" block above the existing screenshot section, always visible whenever the modal is open:

```
┌─ Rank Signals ─────────────────────────────────┐
│ Previously Approved MMR        2,400           │
│ Self-Reported MMR              3,500           │
│ Rank                Crusader 4  (1,540–2,310)  │
│ Battle Cup Tier              —                 │
└────────────────────────────────────────────────┘

Approved MMR: [ 2,400 ]
Suggested range: 1,540–2,310 (from medal)
```

Row rules:
- Each row shows the value or `—` if missing.
- The medal row appends the medal-wide range in muted text when a medal is present.
- The battle-cup row shows `Tier N (low–high)` when `rank_status="never"` and a tier is set; otherwise `—`.
- For `rank_status="previous"` + medal, append `(previous)` to the medal row label so admins know it's stale.
- Helper text under the input: `Suggested range: low–high (from medal | battle cup | fallback)`.

### `data-testid` contract

```
rank-signals
rank-signals-prior-mmr
rank-signals-self-report
rank-signals-medal
rank-signals-battle-cup
suggested-range-helper
```

These selectors are the test contract for the new block. Existing testids on the modal (`mmr-modal-approve`, `mmr-modal-reject`, `mmr-modal-close`) stay unchanged.

### Schema additions

`frontend/app/components/events/schemas.ts` — `EventSignupType` gains:

```typescript
suggested_mmr: z.number().int(),
suggested_mmr_range: z.tuple([z.number(), z.number()]),
```

## Edge cases

| State | Result |
|---|---|
| No `dota_profile`, no prior MMR | All signal rows `—`. Default = midpoint of fallback (1,000). Range = `0–2,000`. |
| Prior MMR set, no profile | Prior row shows value, others `—`. Default = prior. Range = fallback `0–2,000`. |
| Profile with `rank_status="never"` + battle_cup_tier=4, no prior | Medal row `—`. Battle-cup row `Tier 4 (2,000–3,000)`. Default = 2,500. Range source = `battle_cup`. |
| Profile with `rank_status="previous"` + medal, no prior, no self-report | Medal row `Crusader 3 (1,540–2,310) (previous)`. Default = 1,925 (midpoint). Range source = `medal`. |
| Medal value not in settings table (corrupted data) | Falls through to fallback range. Logged as a warning by `_compute_range` (future improvement, not in this spec). |
| `Immortal` (no star) | Parsed as `("Immortal", 1)`. Range = `5,420–8,000`. |

## Testing

### Backend unit tests

New file: `backend/events/tests/test_mmr_suggestions.py` (pytest).

| Case | `default_source` | `range_source` |
|---|---|---|
| prior + self-report + medal | `prior` | `medal` |
| no prior, self-report + medal | `self_report` | `medal` |
| no prior, no self-report, medal only | `medal` | `medal` |
| `rank_status=never` + battle_cup_tier | `battle_cup` | `battle_cup` |
| no profile, no prior | `fallback` | `fallback` |
| `rank_status=previous` + medal | `medal` | `medal` |

Plus parametric coverage:
- All 8 medals — assert returned range matches `DOTA_MEDAL_MMR_RANGES[medal]`.
- All 8 battle cup tiers — assert returned range matches `DOTA_BATTLE_CUP_MMR_RANGES[tier]`.
- `_parse_medal("Immortal")` returns `("Immortal", 1)`.
- `_parse_medal("Crusader 3")` returns `("Crusader", 3)`.

### Playwright E2E

Extend the existing approval test in `frontend/tests/playwright/e2e/16-events/04-discord-integration.spec.ts` (already exercises `loginEventAdmin` approving `event_player_1`'s Legend 3 / 3,200 self-report signup).

**Augment the existing "approve via MMR modal" test** with assertions:
- `dialog.getByTestId('rank-signals')` visible.
- `dialog.getByTestId('rank-signals-self-report')` shows `3,200`.
- `dialog.getByTestId('rank-signals-medal')` shows `Legend 3` and `3,080–3,850`.
- `dialog.getByTestId('suggested-range-helper')` shows `3,080–3,850`.
- MMR input pre-fills with `3,200` (self-report, since `event_player_1` has no prior approval).

**Add two sibling tests in the same `describe` block:**

1. **Prior-approved precedence test.**
   - Use a test endpoint to set `OrgUser.org_user_mmr=2400` for `event_player_1` before opening the modal.
   - Test endpoint must call `invalidate_obj(org_user)` after the write (cacheops invalidation rule from the testing skill).
   - Assert input pre-fills with `2,400`, and the rank-signals block still shows `Legend 3 (3,080–3,850)`.

2. **Battle-cup path test.**
   - A second player (`event_player_2`, see test data section) signs up with `rank_status="never"` + `battle_cup_tier=4`.
   - Assert `rank-signals-medal` shows `—`.
   - Assert `rank-signals-battle-cup` shows `Tier 4 (2,000–3,000)`.
   - Assert helper text reads `Suggested range: 2,000–3,000 (from battle cup)`.
   - Assert input pre-fills with `2,500` (BC tier 4 midpoint).

All new assertions use `data-testid` selectors only — no `getByText`/`getByLabel`/`getByRole('combobox')` for element interaction (testing skill rule).

### Test data additions

`backend/tests/populate/events.py` (or the equivalent populate module for the events feature isolation):

- Add `event_player_2` (PK 1082), regular user, member of Events Test Org (PK 7).
- Their `PlayerDotaProfile`: `rank_status="never"`, `battle_cup_tier=4`, `mmr=null`, no medal.
- Add `loginEventPlayer2()` fixture in `frontend/tests/playwright/fixtures/auth.ts`.

Both `event_player_1` (existing) and `event_player_2` (new) must remain feature-isolated to the events test data — no reuse from other features (per the feature-isolation rule).

### Test endpoint additions

`backend/app/views/test_endpoints.py` (TEST=true only):

- `POST /api/tests/org-user/{org_user_id}/set-approved-mmr/` with body `{ "mmr": int }`. Sets `OrgUser.org_user_mmr` and calls `invalidate_obj(org_user)`. Used by the prior-approved precedence test.

Use `postWithCsrf` from the test fixture when calling this endpoint.

## Out of scope (future)

- Per-org or per-event range overrides.
- DB-backed admin-editable medal→MMR table.
- Logging/telemetry on which `default_source` admins ultimately accept vs. override.
- Periodic stale-MMR DM nudges.
- Companion bug-fix spec for the Discord rank_medal/StarSelect race that currently mislabels picks as Herald — separate doc.

## File list

**New files:**
- `backend/events/mmr_suggestions.py`
- `backend/events/tests/test_mmr_suggestions.py`
- `docs/superpowers/specs/2026-05-03-discord-dota-mmr-range-design.md` (this file)

**Modified files:**
- `backend/backend/settings.py` — add the three settings constants.
- `backend/events/serializers.py` — add `suggested_mmr` and `suggested_mmr_range` fields to `EventSignupSerializer`.
- `frontend/app/components/events/MmrApprovalModal.tsx` — remove `MEDAL_MMR`/`estimateMmr`, add Rank Signals block, switch default to `signup.suggested_mmr`, add helper text.
- `frontend/app/components/events/schemas.ts` — add `suggested_mmr` and `suggested_mmr_range` to `EventSignupType`.
- `frontend/tests/playwright/e2e/16-events/04-discord-integration.spec.ts` — augment existing test, add two siblings.
- `frontend/tests/playwright/fixtures/auth.ts` — add `loginEventPlayer2()`.
- `backend/tests/populate/events.py` (or local equivalent) — add `event_player_2` with `rank_status=never` + `battle_cup_tier=4`.
- `backend/app/views/test_endpoints.py` — add `set-approved-mmr` test endpoint with cacheops invalidation.
