# Org Standing

`org/standing/` is the one interface between the rest of the backend and the
per-member organization tracks. A track scores members of an organization on one
axis. Three tracks are planned:

| Track | Status | Measures |
|---|---|---|
| `contribution` | Live | Points for hosting, helping, promotion and manual awards (the ledger) |
| `conduct` | Live (backend) | Attendance outcomes and each member's show rate |
| `leadership` | Planned | Captain and team-leadership history |

Each track's code stays in its own package (`org/contributions/`, `org/conduct/`), and
the package's `adapter.py` plugs it into the registry. Conduct is registered after
contribution.

## Public interface

`events/` and `app/` import only `org.standing.api`. They never import
`org.contributions.*` and never name a track's output keys:

```python
from org.standing import api as standing

with transaction.atomic():
    # ... write the state change ...
    result = standing.on_event_closed(
        event, cancelled=False, source="admin", actor=user, now=now
    )
    OrgLog.objects.create(
        ..., details={"event_id": event.pk, **result.orglog_details()}
    )
log.info("event_closed", system="events", subsystem="services", **result.log_fields())
```

Each hook returns a `HookResult` holding one `TrackOutput` per track.
`orglog_details()` merges every track's OrgLog keys and `log_fields()` merges every
track's structlog fields, so callers spread both without knowing which track wrote
them.

| Hook | Called from | Contribution track | Conduct track |
|---|---|---|---|
| `on_event_closed(event, *, cancelled, source, actor, now=None)` | `events.completion`, `events.services.cancel_event` | Awards host/helper points (also on an auto-cancel that had staff), stamps `contributions_awarded_at`; returns `awarded` (OrgLog, log) and `created` (log) | Finalizes outcomes, or voids them when `cancelled`; sets `event.conduct_finalized_at` in memory |
| `on_event_reopened(event, *, actor, now=None)` | `events.reopen` | Revokes host/helper points; returns `revoked` (OrgLog, log) | Deletes default and automatic outcomes, unfinalizes the rest (staff edits, late cancels); returns `attendance_reopened` (OrgLog, deleted + kept) |
| `reopen_reset_fields()` | `events.reopen` compare-and-set | `{"contributions_awarded_at": None}`, cleared in the same `UPDATE` | `{"conduct_finalized_at": None}` |
| `on_event_deleted(event, *, actor, now=None)` | `events.services.teardown_event`, `EventAdmin.delete_model`/`delete_queryset` | Nothing | Deletes unfinalized outcomes, voids finalized ones |
| `on_event_changed(event, *, fields, now=None)` | Event PATCH (every changed model field), staff edit, host/helper dedupe after a merge | Re-syncs host/helper points once awarded when `fields` includes a time, name or staff field; returns `synced` (log) | Nothing |
| `on_signup_withdrawn(signup, *, prior_status, by_member, now=None)` | `events.services._withdraw`, used by `cancel_signup`, `decline_signup` and `create_tentative_signup` (the switch to Maybe), on every withdrawal; `by_member` comes from the actor's role: true for a member actor (web or Discord), false for staff and system actors | Nothing | Captures a late cancel (or a no-show after the start) when `by_member` and the prior status held a seat |
| `on_feature_toggled(org_id, feature, *, enabled)` | Feature switch API (`org/views_features.py`), `OrgFeatureAdmin.save_model`, both inside `transaction.atomic()` | Nothing | Re-stamps the org's stored eligibility reasons on commit |
| `merge_users(drop, keep, *, member_pairs)` | Profile claim merge (`org/views.py`), Discord account merge (`app/discord_accounts.py`); both also move the merged account's event signups through `events.merge.merge_user_signups`, which records them in the signup ledger | Moves ledger rows to the kept member, repoints `awarded_by`/`updated_by` | Moves outcomes (a staff edit wins a same-event clash), repoints `set_by`/`updated_by` |
| `on_user_deleted(user, *, actor)` | User delete (admin and API) | Deletes the user's rows, one `delete_user_contributions` OrgLog per org | Nothing (outcomes cascade with the `OrgUser`) |
| `deletion_blockers(user_pks)` | `CustomUserAdmin.get_deleted_objects` | The user's ledger rows (`RESTRICT`) | Nothing |
| `promotion_order(event, candidates, *, cache)` | `events.services` waitlist promotion | No reordering | With back of the line on, moves deferred members after everyone else, keeping their order |
| `leaderboard(org, track, metric, period, *, viewer, now=None)` | `/contributions/leaderboard/`, `/standing/<track>/leaderboard/` (`/conduct/leaderboard/` reads `org/conduct/board.py` directly) | Points (or `entries`) per member for the period | Show rate per member, ranked then new; `total` is `null` |

`leaderboard` raises `UnknownTrack`, `UnknownMetric`, `FeatureLocked`, or
`AccessDenied` when the track's `access()` returns `allowed=False`. It blanks `rows`
and `own_row` when the viewer may not see them, never `total`, and sets
`rows_visible`. Contribution also serves an `entries` metric (rows ordered by entry
count) from the same aggregation as `points`.

### Read surface

| Call | Returns |
|---|---|
| `viewer_roles(org, viewer)` | A lazy `ViewerRoles`: `is_admin`, `is_staff` and `can_view_members` each run their permission query on first read only. Anonymous or `None` viewers get all-False with no queries |
| `ViewerRoles.fixed(is_admin, is_staff, can_view_members)` | Eager roles from values the caller already has (org detail uses its cached payload) |
| `tracks_for(org_id, *, viewer, features, roles)` | One `TrackInfo` per track whose feature is in `features`, in registry order |
| `member_standing(org_user, *, viewer, roles, now=None)` | `{track_key: block}` for unlocked tracks that let this viewer see the member |

A track implements `access(org_id, *, viewer, roles) -> TrackAccess` (`can_view_rows`,
`can_view_own`, `allowed`, `board_open`) and
`member_standing(org_user, *, viewer, roles, now)`. `track_info()` is built on the base
class from `access()` plus `roles.is_admin` for `can_manage`. A track reads only the
roles it needs, so contribution's leaderboard costs the same single member-list query
it always has. Contribution's `member_standing` returns `totals` and `monthly` for the
member themselves or a viewer who can see the member list, in two queries.

!!! info "Interface status"
    `ledger.upsert_event_entry` arrives with the leadership track.

## Invariants

- **Caller owns the transaction.** Every lifecycle, merge and delete hook runs inside
  the caller's `transaction.atomic()`, after the state change is written and before
  the OrgLog row. Outside an atomic block a hook raises `RuntimeError`. `api.py` never
  opens its own atomic, so hooks add no savepoint queries.
- **Registry order.** Tracks run in `registry.TRACKS` order with one shared `now`.
- **No swallowing.** An exception in a track propagates and rolls the caller's
  transition back.
- **Idempotent.** A hook may run again for the same state without writing twice
  (contribution close and edits reconcile the event's host/helper rows with
  `sync_event_staff_entries` instead of appending).
- **Fixed output keys.** Each track declares the keys it returns per hook in
  `output_keys` and always returns exactly those. `api.py` rejects undeclared output,
  and the registry rejects two tracks that share a key.
- **Gating is per track.** Contribution writes are not gated on
  `FeatureKey.CONTRIBUTIONS`, so a locked org keeps its ledger current; reads
  (`leaderboard`) are gated.

## Reopen

`events.reopen.reopen_event` spreads `standing.reopen_reset_fields()` into its
compare-and-set `UPDATE events_event`, so every track's "already processed" stamp is
cleared in the same statement. It then refreshes the event and calls
`on_event_reopened`, so tracks see the reopened event. `ReopenResult.details` carries
the hook's OrgLog details (empty when the reopen was skipped).

## Merge

Both merge sites follow the same order inside one atomic block:

1. Build `member_pairs`: `(drop_org_user, keep_org_user)` for every org where both
   users are members (members only `drop` has are moved, not paired).
2. `standing.merge_users(drop, keep, member_pairs=pairs)`.
3. `org.accounts.repoint_org_attribution(drop, keep)` for non-standing account data
   (`OrgFeature.enabled_by`, `PromoTemplate.created_by`).
4. Delete the dropped `OrgUser` rows. This must come after step 2: ledger rows point
   at `OrgUser` with `RESTRICT`.
5. After events are repointed, `events.staff.dedupe_host_helpers(keep)` removes the
   kept user from the helpers of events they also host and calls
   `standing.on_event_changed(event, fields=frozenset({"helpers"}))` for each of
   those events.

`merge_users` calls each track's `merge_members` once per pair and `repoint_user`
once. Per track, `merge_members` outputs are combined across pairs (ints added,
bools or-ed) and then joined with the `repoint_user` output by plain dict union. The
keys never overlap: the registry treats `merge_members` and `repoint_user` as one
output namespace.

!!! note "Grafana"
    `event_staff_deduped` now logs with `system="events", subsystem="services"`, not
    `org`/`contributions`. It still carries `synced`, the number of deduped events
    whose staff points were re-synced (summed from each `on_event_changed` result's
    `log_fields()`).

## Ledger and kinds

`org/standing/kinds.py` holds `KINDS`, one global table of ledger kinds
(`LedgerKind`: owning track, default points, once-per-event). Kind names are global;
`build_kinds` rejects duplicates across tracks. `kinds_for(track)` and
`ONCE_PER_EVENT_KINDS` derive from it.

`org/standing/ledger.py` reads and writes `ContributionEntry` (always `.nocache()`):

| Helper | Does |
|---|---|
| `award(*, org, user, kind, occurred_at, points=None, ...)` | Creates one entry; resolves the `OrgUser` and default points |
| `revoke_event_kinds(event, *, kinds)` | Deletes the event's entries of those kinds; returns the count |
| `sum_by_member(org_id, *, track, period)` | Per-member totals for a track, non-zero only, ranked |
| `total(org_id, *, track, period)` | The org's total for a track |
| `in_period(qs, period)` | Filters by `occurred_at` |
| `points_for(org, kind)` | The org's override from `ContributionPointValue`, else the kind's default |

Periods (`Period`, `parse_period`, org-timezone helpers) live in
`org/standing/periods.py`.

## Shared scorer

`org/standing/scoring.py` is the recency-weighted rate for rate metrics:
`weighted_rate`, `score_groups` (one pass over `(key, value, at)` rows, optional
`fill` with the prior), `prior_rate`, `mean_normalized`, `to_score5`/`from_score5`.

!!! info "Formula"
    `rate = (α·prior + Σ w·v) / (α + Σ w)`, with `w = 0.5^(age_days / half_life_days)`
    and `α = prior_strength`, clamped to `[0, 1]`. Rows older than `max_age_days` are
    ignored; a score is `"new"` until it has `min_count` observations.

## Conduct track

`org/conduct/adapter.py` (`CONDUCT`) wraps the conduct lifecycle (see the hook table).
The generic maths (`weighted_rate`, `score_groups`) comes from the shared scorer;
`org/conduct/scoring.py` keeps only conduct's show value, forecast and member score.
While Conduct is locked, the adapter records nothing new: finalize materializes no
outcomes and late cancels are not captured. Maintenance (void, reopen, delete, merge)
always runs.

### Enforcement through the evaluator

Enforcement is not a standing hook. It is the evaluator check
`events/eligibility/checks/conduct.py`, the one module in `events/` that imports a
track package, and it imports only `org.conduct.eligibility` (plus
`org.standing.cache`). The check reads the member's tier through a `StandingCache`, so
a waitlist pass builds the gate once and scores once; evaluator `PRIMERS` let
`events.eligibility.store` batch the scoring for a whole org without naming a track.

| Tier | Self sign-up | Staff placement or re-evaluation (`for_staff_placement=True`) |
|---|---|---|
| Require approval | `needs_approval`, rule `conduct-require-approval` | Same |
| Block | `block`, rule `conduct-block` | `needs_approval`, rule `conduct-block` |

Both carry code `conduct_below_threshold` and `params={"tier": ...}`, never the show
rate. `events.admission.ensure_self_serve` raises `SignupRefused` on any blocking
reason and logs `signup_eligibility_refused`; admission never imports conduct.

### Re-stamp slot

Conduct writes that change a tier (finalize, staff edits, settings, the feature switch)
re-stamp stored reasons through `org/standing/restamp.py`, a slot that lets a track
reach the evaluator store without importing `events.eligibility`:

| Call | Does |
|---|---|
| `register(org_fn, member_fn)` | `events.eligibility.store` registers `refresh_org_eligibility` and the batch member refresh at import |
| `org_on_commit(org_id)` | Re-stamps every open signup in the org after commit |
| `member_on_commit(org_users)` | One callback for a batch of members (one gate, one scoring query) |
| `override(org_fn, member_fn)` | Test-only context manager; tests never call `register()` |

Both `*_on_commit` calls raise `RuntimeError` when nothing is registered, which would
roll back the caller. `events/completion.py` and `events/reopen.py` import
`events.eligibility.store` at module top, so every interpreter that can finalize or
reopen has the slot registered (`org.tests.test_standing_import_order` checks each
entry point in a fresh interpreter).

## Generic endpoints

- `GET /api/organizations/<org_id>/standing/tracks/`: the viewer's tracks for the org
  (also embedded in org detail as `standing_tracks`).
- `GET /api/organizations/<org_id>/standing/<track>/leaderboard/?metric=&period=`: one
  metric's board. `api.leaderboard` blanks rows and the own row from the track's access
  rule, whatever the adapter returned. Non-periodic metrics echo `period="current"`.

`TrackAccess` carries two board-level flags beside the row flags. `allowed=False`
makes `api.leaderboard` raise `AccessDenied` (the view returns `401` to anonymous
viewers and `not_permitted` otherwise); conduct sets it when the ranking is private
and the viewer is neither staff nor a member. `board_open` is whether the board itself
is open to the viewer (conduct: `leaderboard_public` or org staff; contribution:
always), and backs org detail's `can_view_conduct`.

## Departures from the design

| Departure | Status |
|---|---|
| `track_info`, `member_standing`, `api.tracks_for`, `api.member_standing` | Closed by the conduct track |
| Contribution `entries` metric | Closed by the conduct track |
| `tests/populate/*` rewired onto standing | Closed by the conduct track |
| `ledger.upsert_event_entry` | Open, arrives with the leadership track |
| Promotion wrapper named `has_promo_entry` | Stays |
| `dedupe_host_helpers` calls `on_event_changed` itself; Event PATCH passes every changed field | Stays |
| The internal transition endpoint and `cleanup_stale_repeater_events` change event state without the hooks | Open |

## Adding a track

1. Subclass `org.standing.base.TrackBase` in the track's package (`adapter.py`).
   Override only the hooks you need, mark them `@typing.override`, and keep the
   base signatures exactly (`test_standing_registry` checks this). Implement
   `access()`, `leaderboard()` and `member_standing()`.
2. Declare `key`, `label`, `feature`, `metrics` (exactly one `default=True`),
   `output_keys` and any `reopen_reset_fields`.
3. Add the instance to `TRACKS` in `org/standing/registry.py`.
4. Add the track's ledger kinds to `org/standing/kinds.py`.
5. Test call sites with a fake track via `registry.override_tracks(...)`
   (see `org/tests/standing_fakes.py`).

## Layering

```text
org/standing/
  __init__.py   empty
  api.py        the interface (imports registry)
  registry.py   imports each adapter
  views.py, urls.py   generic endpoints (import api)
  base.py, types.py, cache.py, errors.py, scoring.py, serializers.py,
  periods.py, kinds.py, ledger.py, restamp.py      leaves
```

- `__init__.py` stays empty, so importing a leaf never loads the registry.
- Leaves never import `api`, `registry` or an adapter.
- `scoring.py` is pure Python: no Django, `org`, `events` or `app` imports.
- Nothing `registry.py` reaches imports `events.services`, `events.views`,
  `events.completion`, `events.reopen`, `events.admission` or `events.eligibility`.
- `app/` and `events/` import only `org.standing.api` (and `org.standing.cache`).
  `events/eligibility/store.py` may also import `org.standing.restamp`, and
  `events/eligibility/checks/conduct.py` may import `org.conduct.eligibility`. No other
  module in `events/` names a track or a track output key.

`org.tests.test_standing_layering` checks these rules, including the transitive
closure of the registry. `org.tests.test_standing_import_order` imports each entry
point first in a fresh interpreter to catch import cycles.

## Logging

Shared helpers log with `system="org", subsystem="standing"`
(`org_timezone_invalid` from `periods.py`). Contribution ledger writes keep
`system="org", subsystem="contributions"`.
