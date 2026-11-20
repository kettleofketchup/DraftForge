# Org Standing

`org/standing/` is the one interface between the rest of the backend and the
per-member organization tracks. A track scores members of an organization on one
axis. Three tracks are planned:

| Track | Status | Measures |
|---|---|---|
| `contribution` | Live | Points for hosting, helping, promotion and manual awards (the ledger) |
| `conduct` | Planned | Attendance and reliability rates |
| `leadership` | Planned | Captain and team-leadership history |

Contributions are the first track. The code stays in `org/contributions/`; its
`adapter.py` plugs it into the registry.

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

| Hook | Called from | Contribution track |
|---|---|---|
| `on_event_closed(event, *, cancelled, source, actor, now=None)` | `events.completion` | Awards host/helper points (also on an auto-cancel that had staff), stamps `contributions_awarded_at`; returns `awarded` (OrgLog, log) and `created` (log) |
| `on_event_reopened(event, *, actor, now=None)` | `events.reopen` | Revokes host/helper points; returns `revoked` (OrgLog, log) |
| `reopen_reset_fields()` | `events.reopen` compare-and-set | `{"contributions_awarded_at": None}`, cleared in the same `UPDATE` |
| `on_event_deleted(event, *, actor, now=None)` | `events.services.teardown_event` | Nothing |
| `on_event_changed(event, *, fields, now=None)` | Event PATCH (every changed model field), staff edit, host/helper dedupe after a merge | Re-syncs host/helper points once awarded when `fields` includes a time, name or staff field; returns `synced` (log) |
| `on_signup_withdrawn(signup, *, prior_status, by_member, now=None)` | No caller yet | Nothing |
| `on_feature_toggled(org_id, feature, *, enabled)` | No caller yet | Nothing |
| `merge_users(drop, keep, *, member_pairs)` | Profile claim merge (`org/views.py`), Discord account merge (`app/discord_accounts.py`) | Moves ledger rows to the kept member, repoints `awarded_by`/`updated_by` |
| `on_user_deleted(user, *, actor)` | User delete (admin and API) | Deletes the user's rows, one `delete_user_contributions` OrgLog per org |
| `deletion_blockers(user_pks)` | `CustomUserAdmin.get_deleted_objects` | The user's ledger rows (`RESTRICT`) |
| `promotion_order(event, candidates, *, cache)` | No caller yet (waitlist promotion) | No reordering |
| `leaderboard(org, track, metric, period, *, viewer, now=None)` | `/contributions/leaderboard/` | Points per member for the period |

`leaderboard` raises `UnknownTrack`, `UnknownMetric` or `FeatureLocked`. It blanks
`rows` and `own_row` when the viewer may not see them (from the track's `access()`),
never `total`, and sets `rows_visible`.

!!! info "Interface status"
    This is the first cut of the interface. Tracks expose `access()` for read
    permissions; `track_info()`, `member_standing()` and `api.tracks_for()` arrive
    with the conduct track and replace or extend it. `ledger.upsert_event_entry`
    arrives with the leadership track. Test data population is unchanged until the
    conduct track.

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

## Adding a track

1. Subclass `org.standing.base.TrackBase` in the track's package (`adapter.py`).
   Override only the hooks you need, mark them `@typing.override`, and keep the
   base signatures exactly (`test_standing_registry` checks this). Implement
   `access()` and `leaderboard()`.
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
  base.py, types.py, cache.py, errors.py, scoring.py,
  periods.py, kinds.py, ledger.py      leaves
```

- `__init__.py` stays empty, so importing a leaf never loads the registry.
- Leaves never import `api`, `registry` or an adapter.
- `scoring.py` is pure Python: no Django, `org`, `events` or `app` imports.
- Nothing `registry.py` reaches imports `events.services`, `events.views`,
  `events.completion`, `events.reopen`, `events.admission` or `events.eligibility`.
- `app/` and `events/` import only `org.standing.api` (and `org.standing.cache`).

`org.tests.test_standing_layering` checks these rules, including the transitive
closure of the registry. `org.tests.test_standing_import_order` imports each entry
point first in a fresh interpreter to catch import cycles.

## Logging

Shared helpers log with `system="org", subsystem="standing"`
(`org_timezone_invalid` from `periods.py`). Contribution ledger writes keep
`system="org", subsystem="contributions"`.
