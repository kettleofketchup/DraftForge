# Org Standing

`org/standing/` is the one interface between the rest of the backend and the
per-member organization tracks. Today it has one track, **contribution**
(the points ledger); conduct and leadership are planned to join it.

Callers outside `org/` never name a track. They call hooks on
`org.standing.api` and pass the result into their own logs:

```python
from org.standing import api as standing

with transaction.atomic():
    result = standing.on_event_closed(
        event, cancelled=False, source="admin", actor=user, now=now
    )
    OrgLog.objects.create(..., details={"event_id": event.pk, **result.orglog_details()})
log.info("event_closed", ..., **result.log_fields())
```

## Hooks

| Hook | Called from | Contribution track |
|---|---|---|
| `on_event_closed` | `events.completion.close_event` | Awards host/helper points (also on an auto-cancel that had staff) and stamps `contributions_awarded_at` |
| `on_event_reopened` | `events.reopen.reopen_event` | Revokes host/helper points |
| `reopen_reset_fields()` | `reopen_event`'s compare-and-set update | Clears `contributions_awarded_at` in the same UPDATE |
| `on_event_deleted` | `events.services.teardown_event` | Nothing |
| `on_event_changed(fields=...)` | Event PATCH (time/name), staff edit, host/helper dedupe after a merge | Re-syncs host/helper points once awarded |
| `merge_users` | Profile claim merge, Discord account merge | Moves ledger rows, repoints `awarded_by`/`updated_by` |
| `on_user_deleted` | User delete (admin and API) | Deletes the user's rows, one `delete_user_contributions` OrgLog per org |
| `deletion_blockers` | `CustomUserAdmin.get_deleted_objects` | The user's ledger rows (`RESTRICT`) |
| `promotion_order` | Waitlist promotion (later tracks) | No reordering |

Reads: `tracks_for`, `leaderboard` (raises `UnknownTrack`, `UnknownMetric`,
`FeatureLocked`; hides rows the viewer may not see) and `member_standing`.

## Rules

- **Callers own the transaction.** Every lifecycle hook runs inside the caller's
  `transaction.atomic()` after the state change is written and before OrgLog is
  written. Outside an atomic block a hook raises `RuntimeError`.
- **Tracks run in registry order** with one shared `now`. An exception in a track
  propagates and rolls the caller's transition back.
- **Fixed output keys.** Each track declares the OrgLog and log keys it returns per
  hook (`output_keys`) and always returns all of them. The registry rejects two
  tracks that declare the same key for the same hook.
- **Gating is per track.** Contribution writes are not gated on the feature flag;
  its reads are.

Non-standing account data (`OrgFeature.enabled_by`, `PromoTemplate.created_by`) is
repointed by `org.accounts.repoint_org_attribution`. Removing a user from the helpers
of events they also host is `events.staff.dedupe_host_helpers`; the caller then calls
`on_event_changed(fields={"helpers"})` for each returned event.

## Adding a track

1. Subclass `org.standing.base.TrackBase` in the track's package (`adapter.py`).
   Override only the hooks you need and mark them with `@typing.override`;
   signatures must match the base exactly (`test_standing_registry` checks this).
2. Declare `key`, `label`, `feature`, `metrics` (exactly one `default=True`),
   `output_keys` and any `reopen_reset_fields`.
3. Add the instance to `TRACKS` in `org/standing/registry.py`.
4. Ledger kinds go in `org/standing/kinds.py`; kind names are global.
5. Test call sites with a fake track via `registry.override_tracks(...)`.

## Layering

```
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
- Adapters may not import `events.services`, `events.views`, `events.completion`,
  `events.reopen`, `events.admission` or `events.eligibility.evaluate`/`store`.
- `app/` and `events/` import only `org.standing.api` and `org.standing.cache`.

`test_standing_layering` checks these rules and `test_standing_import_order`
imports each entry point first in a fresh interpreter.

## Shared scorer

`org.standing.scoring` has the recency-weighted rate used by rate metrics:
`weighted_rate`, `score_groups` (one pass over `(key, value, at)` rows, optional
`fill` with the prior), `prior_rate`, `mean_normalized` and the 1–5 scale helpers.

!!! info "Formula"
    `rate = (α·prior + Σ w·v) / (α + Σ w)`, with `w = 0.5^(age_days / half_life_days)`,
    clamped to `[0, 1]`. Rows older than `max_age_days` are ignored; a score is
    `"new"` until it has `min_count` observations.

## Logging

Shared helpers log with `system="org", subsystem="standing"`. The dedupe log
`event_staff_deduped` is `system="events", subsystem="services"`.
