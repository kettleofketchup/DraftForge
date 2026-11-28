# Signup Ledger & Line Position

Every event signup has a place in line and an original sign-up that never changes. The signup ledger keeps a durable record of every signup change: who made it, how, when, and the signup before and after.

## Place in line

Each signup gets a place in its event's line when it is created:

- **`line_seq`** is the signup's number in the event's line. The next signup gets the current highest number plus one.
- **`signed_up_at`** is the time the signup took that place.

Signups are listed in line order (`line_seq`, then id). The signup API also returns **`line_rank`**: the signup's 1-based position among the event's signups that are still in line. Cancelled, rejected and dropped signups are not in line, so their `line_rank` is empty; they keep their `line_seq`.

Moving a signup to another event gives it a new place at the end of that event's line.

!!! note "Waitlist tab order"
    The website's waitlist tab lists signups in line order. The upgrade reorders existing waitlists to match waitlist order, which is the order Discord shows and promotion uses. Until the waitlist rework lands, a member that a staff member moves to the waitlist afterwards keeps their place in line on the website, so the website and Discord can show that member in different places.

## Commitment

Each signup is either a **main** or a **maybe** signup (`commitment`). A tentative signup is a maybe; every other signup is a main. A tentative signup that is cancelled and then reinstated by a staff member comes back as a main. Each signup also has an RSVP class (`rsvp_class`), which is `standard` for every signup today.

## Original sign-up

Each signup remembers when and how the member first signed up for the event:

| Field | Meaning |
|---|---|
| `first_signed_up_at` | When the member first signed up |
| `first_commitment` | Their commitment at that first sign-up |
| `first_rsvp_class` | Their RSVP class at that first sign-up |

These fields never change once set. If a member cancels and signs up again, or switches between tentative and RSVP, the new signup keeps the original values while its place in line moves to the end. The app refuses any change to them, and the Django admin shows them as read-only.

A member who declines without having signed up has a declined signup with these fields empty, because a decline is not a sign-up. They are filled in the first time that member signs up, goes tentative or is reinstated. The upgrade treats an existing cancelled signup as a decline of this kind when it was never changed after it was created.

## Signup record

The signup ledger (`SignupLedgerEntry`) is an append-only record of signup changes. Each entry stores:

- **Who:** the member the change is about and the person who made it (a member, a staff member or the system), plus whether it was done on someone else's behalf.
- **How:** the means, such as the website, a Discord button or the system.
- **When:** the time of the change.
- **What:** snapshots of the signup before and after, and of the event and the member at that moment.

Entries cannot be edited or deleted through the app or the admin. They outlive the things they describe:

- Deleting an event or a signup leaves its entries in place, with the event snapshot still readable.
- Deleting a user clears the link to that user, and the snapshot keeps their name and Discord ID.
- Merging accounts, through Discord or an approved profile claim, moves the entries to the remaining account.

Each signup that existed when the ledger was added got a `backfilled` entry, marking where its history starts. A `backfilled` entry is not a change in itself. Every change since then writes its own entry, as described below.

## Cancellation and permanent deletion

Cancelling an event retains every live signup and its status, commitment, line stamps and original-signup fields. Its non-removed signups receive `event_cancelled` entries attributed to the staff actor (`staff`/`web`) or system (`system`/`system`). The before snapshot is captured before tournament cleanup, and the after snapshot reflects the remaining placement. Existing event-team placement is retained; linked tournament references can be removed. Ready-check cancellation entries remain alongside the new per-signup entries. No individual withdrawal or waitlist promotion is fabricated.

Cancellation is atomic with its history: if cleanup or an append fails, the database changes roll back together. A second cancellation is rejected without extra entries; a valid reopen followed by cancellation adds a new cycle. The optional API reason accepts up to 2,000 characters; this does not make staff reasons mandatory for other actions.

When an organization staff member tries to delete a record-bearing event, the API returns HTTP 409 and `{"error": "has_signup_records", "count": N}`. **N counts ledger entries, not people or active signups**, including rows with no live signup. An organization administrator must explicitly confirm permanent deletion. The browser requires the exact event name; staff without administrator access can cancel instead where legal, but cannot confirm.

Confirmed deletion removes the live event and signups, without adding cancellation entries or changing existing snapshots. The surviving history is readable in the read-only ledger admin and in the organization's [sign-up records export](#exporting-sign-up-records), **not** through the ordinary history endpoint: that endpoint requires a live event and remains staff-only. Series deletion cancels and retains occurrences with any signup or ledger history, makes them standalone, and deletes only truly empty active occurrences. Schedule realignment skips ledger-bearing occurrences without moving their timestamp; the subsequent configuration cascade is unchanged.

The `cleanup_stale_repeater_events` script uses shared cancellation and emits system-attributed `event_cancelled` entries for the remaining non-removed signups. With no supplied reason, those entries have an empty reason; ready-check closure keeps its separate `event_cancelled` machine reason. Signups and their statuses remain in place. Maintenance refuses events outside `upcoming`/`signups_open` and linked tournaments that have started. Arbitrary ORM deletes and organization cascades are not guarded by the event DELETE confirmation flow.

## What gets recorded

Each signup change writes one entry (moving a signup to another event writes one on each event, see [Moved signups](#moved-signups)), in the same database transaction as the change. If the change fails or is rolled back, no entry is kept, and if the entry cannot be written, the change fails too.

| Action | Written when |
|---|---|
| `signed_up` | A member signs up or goes tentative for the first time. A member who only declined before still gets `signed_up`, because a decline is not a sign-up. A sign-up that lands on the waitlist is still `signed_up`, with the waitlist status in the after snapshot. |
| `resigned_up` | A member who signed up before, then cancelled or was rejected, signs up or goes tentative again |
| `switched_commitment` | A member switches between tentative (maybe) and RSVP (main) |
| `staff_added` | A staff member adds someone to the event |
| `declined` | A member declines, with or without an earlier signup |
| `withdrew` | A signup is cancelled, by the member or by staff |
| `approved` | Staff approve a signup |
| `rejected` | Staff reject a signup |
| `confirmed` / `unconfirmed` | Staff confirm a signup or undo the confirmation |
| `demoted` | Staff move a signup to the waitlist |
| `reinstated` | A cancelled or rejected signup is reinstated |
| `promoted` | A waitlisted signup takes a freed seat |
| `account_merged` | A signup moves to another account in an account merge |
| `moved_event` | The stale repeater cleanup moves a signup to another event |
| `event_cancelled` | Shared event cancellation, including a registered occurrence kept during series deletion. One per non-removed signup per cancellation cycle; cancelled, rejected and dropped signups are retained without a new entry. |
| `voice_presence_set` | An operator sets presence by hand, with a required reason; a resulting confirmation links to this entry through `caused_by` |

The role and means show who acted and how:

| Who acted | Role | Means |
|---|---|---|
| A member on their own signup, on the website | `member` | `web` |
| A staff member on someone else's signup, on the website | `staff` | `web` |
| A member using a Discord button (sign up, decline, tentative) | `member` | `discord_button` |
| A member adding or removing a Discord reaction | `member` | `discord_reaction` |
| A member confirmed through the bot's voice feed | `member` | `discord_voice` |
| An operator setting voice presence by hand | `staff` | `web` |
| The system (waitlist promotion, Discord account merge, cleanup script, test setup) | `system` | `system` |

A staff member acting on their own signup is recorded as `member`. When they used a staff-only action to do it (approve, reject, confirm, unconfirm, demote, a staff add, or a reinstate that bypasses the member rules), the after snapshot carries `extra.staff_power: true`. Approving a profile claim is recorded as the approving staff member, with means `web`.

### Promotions

When a cancel, decline, rejection, switch to tentative or account merge frees a seat, the waitlisted signups that take it each get their own `promoted` entry. Moving a signup to the waitlist promotes nobody; staff fill that seat by hand. Its `caused_by` points at the entry for the change that freed the seat, and it shares that entry's correlation id. Promotions from the `rebalance_event_waitlists` command have no cause.

When a ready check close or resolve drops members, the promotions into their seats point at the step's first `dropped` entry and are recorded as the operator who ran the step, not the system. Every other promotion is a system entry.

### Correlation ids

The correlation id groups entries that belong to one action:

| Source | Correlation id |
|---|---|
| Discord button | The Discord interaction id |
| Discord reaction | `reaction:<message id>:<user id>`, the same for the add and the later remove |
| Discord account merge | `merge-<id>`, one per merge |
| Profile claim approval | `claim-<id>`, one per approval |
| Stale repeater cleanup | `cleanup-<id>`, one per run |
| Ready check | `rc<check id>:<step>`, for example `rc12:close`, on every entry the step writes |
| Manual voice presence | `vp<event id>:<user id>`; any resulting confirmation uses `rc<check id>:confirm` and links back through `caused_by` |
| Website | Empty |

Feed joins and leaves do not write ledger entries; their presence rows hold the evidence. Only confirmations and manual overrides are recorded here.

### Approve with an MMR override

When staff approve a signup and set an MMR, the `approved` entry's after snapshot carries `extra.mmr_override` and `extra.game_type`. The `set_mmr` org log entry is still written as before.

### Account merges

Both account merges, a Discord account merge and an approved profile claim, move the merged account's signups to the kept account and write an `account_merged` entry for each one, with `extra.from_user_id` set to the merged account in the before snapshot (and in the after snapshot when the row moved). When both accounts had signed up for the same event, one signup is deleted: the kept account's, if only the merged account's signup holds a seat, otherwise the merged account's. The entry is written against the surviving signup, and its before snapshot is the deleted signup with `extra.discarded_duplicate: true` and `extra.discarded_signup_id`. Earlier entries about the merged account, and entries it made as the actor, move to the kept account.

Approving a profile claim used to delete the claimed profile's signups; it now moves them to the claimer.

### Moved signups

When the stale repeater cleanup script moves a signup to another event, it writes a `moved_event` entry on each event. The entry on the old event closes that signup's history there, and the entry on the new event starts it, with `caused_by` pointing at the old event's entry. The before and after snapshots carry `extra.event_id` for the old and new event.

### What is not recorded

- Deleting an event, a user or a signup, including deletes in the Django admin, writes no entry.
- The Django admin cannot add a signup or change its status, user, event, team, type or waitlist place. Staff change signup state through the event pages, which record it.
- Signups created by test data population or fixtures have no starting entry.

## Staff history

Event staff can read an event's signup record on the event page. Event staff are the staff of the event's organization, or of its league for a league event. Members and visitors never see it: the tab and the row buttons are hidden for them, and the API refuses them.

- **History tab:** the last tab on the event page lists every entry for the event, newest first. **Load more** fetches older entries.
- **Row button:** each signup row on the Signups, Tentative, Waitlist and Removed tabs has a history button. It opens a side sheet with the same list, filtered to that member.

Each row shows:

- the member, the action (for example "Withdrew", "Signed up again", "Added by staff" or "Promoted from waitlist") and the time in the event's timezone;
- who made the change and a badge for how it was made: **Web**, **Discord button**, **Discord reaction**, **Staff** or **System**. **Staff** means a staff member changed someone else's signup on the website; a staff member changing their own signup shows **Web**;
- what changed: status, main or maybe, and place on the waitlist or in line. A promotion also says which change freed the seat, when that entry is in the list; otherwise it reads "automatic";
- the reason staff gave, and a chip listing any sign-up rules the change overrode, when the entry has them;
- notes from the snapshot's `extra`, such as a staff-only action, an MMR override, an account merge or a move from another event.

When the list is filtered to one member, with no action filter, and every page has loaded, their first sign-up is marked **Original sign-up**.

The tab has two filters, **member** and **action**. **Clear filters** resets both. The list wraps long names and reasons, so it fits a phone screen without sideways scrolling.

!!! note "Signups without history"
    Signups created by test data population or fixtures have no entries, and signups from before the ledger start at their `backfilled` entry ("Starting record"). A member with no entries shows "No changes recorded for this member".

!!! info "Reasons and overridden rules"
    Staff cannot give a reason for most changes yet, so `reason` is usually empty, and nothing fills `rules_overridden` yet. The page shows both as soon as later work records them.

## Exporting sign-up records

Organization staff can download every sign-up for the organization's events as a CSV file:

1. Open the organization page and select **Export sign-up records** in the header.
2. Pick **From** and **To** dates. The range covers events scheduled from the start of **From** to the end of **To**, in the organization's timezone. It defaults to the last 90 days.
3. Select **Download CSV**.

The file has one row per event and member. Cancelled events are included, and so are events that were deleted or moved to another organization, using the event snapshot from the ledger. Ready-check entries have no member, so they are not in the export.

| Column | Content |
|---|---|
| `event_id`, `event_name`, `scheduled_at`, `series_id` | The event, from the live event or its last snapshot |
| `event_state` | The event's state, `deleted` for a deleted event, or `moved` for an event now in another organization |
| `user_id`, `discord_id` | The member. A deleted user falls back to the snapshot. Only the member's Discord ID is included, never the ID of whoever made a change |
| `original_signed_up_at`, `original_commitment`, `original_rsvp_class`, `original_means` | The member's first recorded sign-up for the event |
| `final_status`, `final_commitment`, `final_rsvp_class`, `final_signed_up_at`, `final_line_seq` | The member's signup as of their last recorded change |
| `withdrawn_at` | When the member withdrew, if their signup ends cancelled or dropped. Empty otherwise |
| `change_count` | The number of entries after the original sign-up |
| `last_changed_at` | The time of the member's last entry for the event |

Times in the file are UTC. Rows are ordered by the event's scheduled time, then event, then member. A member whose entries hold no readable signup snapshot still gets a row, with the original and final columns empty.

!!! note "Cells starting with `= + - @`"
    In the CSV only, a cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'`, so spreadsheet apps do not run it as a formula. An event named `-Weekly Inhouse-` appears as `'-Weekly Inhouse-` in the CSV and unchanged in the JSON API.

If the range holds more than 50,000 rows the download fails with "Too many records — choose a shorter range."

Only organization staff, organization admins and site admins can export. League staff cannot, because the export covers every event in the organization.

## Retention and purge

Sign-up records are kept forever by default. An organization admin can set a retention period in **Org Settings → Sign-up records**: choose **For a set period** and enter a number of days. The minimum is 30 days. See [Organization Settings: Sign-up records](../organization-settings.md#sign-up-records).

Every night at 04:30 a job deletes the ledger entries of events that ended longer ago than the retention period:

- An event's end is its `ends_at`, or its `scheduled_at` when it has no end time. An event is purged when that end is strictly before now minus the retention period.
- Deleted events and events moved to another organization are judged by the latest ledger snapshot the organization holds for them.
- An event whose end cannot be read from the event or its snapshot is kept. Entries with no organization are never purged.
- The job deletes whole events: an event's entries are all deleted together or not at all.
- It deletes ledger entries only. Signups, events and members are never touched.

!!! danger "Purged records cannot be recovered"
    Lowering the retention period takes effect at the next nightly run. Entries deleted by the purge are gone for good; export them first if you need them.

The job runs through the internal API in requests limited to 20 seconds each, up to 12 per night. A large backlog that does not fit finishes on the following nights.

!!! info "Operator settings"
    Two environment variables on the backend tune this feature:

    | Variable | Default | Meaning |
    |---|---|---|
    | `SIGNUP_RECORD_MIN_RETENTION_DAYS` | `30` | The shortest retention period an organization can set |
    | `SIGNUP_RECORDS_MAX_ROWS` | `50000` | The most rows one records request or export can return before it fails with `too_many_records` |

## For developers

- Every signup service in `events/services.py` takes a required keyword `actor: SignupActor`. Calling one without it raises `TypeError`.
- Build the actor with `SignupActor.for_request_on(request, subject, event)` on the website (pass `staff_only=True` on staff-only endpoints), `SignupActor.discord(user)` in Discord flows (it picks up the bound interaction id), or `SignupActor.system()` where no person acts.
- A new signup mutation must record exactly one entry with `record_signup_change`, inside its own `transaction.atomic` block, after its guards. Take `before = snapshot(signup)` from a row read with `.nocache()` inside the transaction.
- A mutation that frees a seat passes its entry to `_promote_from_waitlist(event, cause=entry)`.

### History API

`GET /api/events/<id>/signup-history/` returns the event's ledger entries, newest first. It is read-only and not cached.

| Param | Meaning |
|---|---|
| `user` | Only entries about this user (pk) |
| `action` | Only entries with this action |
| `cursor` | The opaque token from the previous page's `next` |
| `page_size` | 1 to 100, default 50 |

Empty values count as absent. The response is the cursor envelope `{count, next, previous, results}`: `count` is the number of matching entries at request time, `next` is the URL of the next page or `null`, and `previous` is always `null`. Paging is keyset on (`occurred_at`, `id`), so entries written between page loads never shift or repeat rows on later pages.

Each item has:

| Field | Content |
|---|---|
| `id`, `occurred_at`, `action`, `means`, `on_behalf`, `reason` | As stored on the entry |
| `subject` | `user_id`, `username`, `nickname`, `discordNickname`, `guildNickname`, `avatarUrl`, `discord_id` of the member. A deleted user falls back to the snapshot's name and Discord ID |
| `actor` | The same user fields without `discord_id`, plus `role` (`member`, `staff` or `system`). All user fields are `null` for the system |
| `before`, `after` | The signup snapshot (`status`, `commitment`, `rsvp_class`, `signed_up_at`, `line_seq`, `waitlist_position`, `event_team_id`, `extra`), or `null` when there is none or the stored snapshot cannot be read |
| `rules_overridden` | A list of rule names, empty today. A stored value that is not a list of strings comes back as `[]` and logs `signup_history_rules_invalid` |
| `caused_by` | The id of the causing entry, or `null` |

Left out on purpose: `correlation_id`, the event and member snapshots, and any `extra` key other than `staff_power`, `mmr_override`, `game_type`, `from_user_id`, `discarded_duplicate`, `discarded_signup_id` and `event_id`.

Errors:

- **404** when the event does not exist.
- **403** with an empty body for anyone who is not event staff, including anonymous callers. This check runs before the params are read, so non-staff learn nothing from them.
- **400** for a bad param: `{"user": ["Invalid user."]}`, `{"action": ["Invalid action."]}`, `{"cursor": ["Invalid cursor."]}` or `{"page_size": ["Invalid page size."]}`.

The frontend reads it with `getEventSignupHistory` and the `useSignupHistory` hook (query key `['event-signup-history', eventId, filters]`). Every staff signup mutation invalidates that key for the event.

### Records API

Four read endpoints serve the sign-up records to the website and to BI tools. They are read-only and not cached.

| Method | Path | Auth |
|---|---|---|
| GET | `/api/organizations/<id>/signup-records/` | Session login only, org staff |
| GET | `/api/organizations/<id>/signup-ledger/` | Session login only, org staff |
| GET | `/api/internal/signup-records/?organization=<id>` | Internal service token |
| GET | `/api/internal/signup-ledger/?organization=<id>` | Internal service token |

The organization endpoints accept a browser session only, not an org API token or the internal token. Org staff, org admins and site admins are allowed; league staff, members and anonymous callers get 403, and each denial logs `signup_records_denied`. They share a throttle of 10 requests a minute per user. Machine access goes through the internal endpoints, which use `InternalServiceAuth` and `IsInternalService` like the other internal routes. On those, `organization` is required: a missing or invalid value is 400 and an unknown organization is 404.

Both endpoints take the same filters. Empty values count as absent.

| Param | Meaning |
|---|---|
| `since` | Events with `scheduled_at` at or after this time |
| `until` | Events with `scheduled_at` before this time (exclusive) |
| `series` | Events in this series |
| `event` | One event |
| `user` | Entries about this user (pk), including a deleted user's entries by snapshot |

`since` and `until` take an ISO date or a datetime with a UTC offset. A date means 00:00 in the organization's timezone, on the internal endpoints too. A datetime without an offset, `since` after `until`, or a bad id is 400, for example `{"until": ["Must not be before since."]}`. Events with no scheduled time are left out whenever `since` or `until` is set. The filters apply to the event's scheduled time, not to when entries were written.

**Records.** `signup-records/` returns `{organization, count, results}`, one item per event and member, unpaginated. Each item has the [export columns](#exporting-sign-up-records), with the original and final fields nested under `original` and `final` (each `null` when there is no readable snapshot). Times are UTC ISO strings ending in `Z`. Add `format=csv` for the CSV file, with the same rows in the same order and a `Content-Disposition` filename of `signup-records-<org id>-<YYYYMMDD>.csv`. The leading `'` formula guard applies to the CSV only. More rows than `SIGNUP_RECORDS_MAX_ROWS` gives 400 `{"detail": "Too many records; narrow the date range.", "code": "too_many_records"}`. Errors are always JSON, including on a `format=csv` request.

**Raw ledger.** `signup-ledger/` returns the ledger entries themselves, oldest first by `id`, including ready-check entries (with `subject: null`). It takes `cursor` and `page_size` (1 to 100, default 50) as well as the filters, and returns the cursor envelope `{count, next, previous, results}` like the [history API](#history-api). Each item has the history fields plus `event_id`, `organization_id` and `event: {name, state, scheduled_at}`, where `state` is `deleted` or `moved` for an event resolved from its snapshot. The member keeps `discord_id`; the actor never has it.

The cursor is keyed on `id` alone, so a sync can save `next` and resume from it later. Entries written after a page was read always appear on a later page.

!!! warning "Re-read a small overlap"
    SQLite reuses the highest `id` if the newest row in the table is deleted. If the nightly purge deletes the newest entry, the next entry can get an `id` a consumer has already passed. This needs a late change to an event old enough to be purged that same night, so it is rare. Consumers that need every entry should restart a little before their last cursor and dedupe on `id`.

**Purge.** `POST /api/internal/signup-records/purge/` (internal token) runs one purge pass of at most 20 seconds and returns `{purged, organizations, events, skipped_unknown_end, per_org, more}`. `per_org` maps organization ids (as strings) to deleted entry counts, and `more` is true when the time ran out before every organization was done. The Celery task `events.tasks.purge_expired_signup_records` calls it in a loop while `more` is true, up to 12 times. Each organization's purge logs `signup_records_purged` and each pass logs `signup_records_purge_completed` (`system="events"`, `subsystem="ledger"`).

The code is in `events/ledger.py` (event resolution and purge), `events/records.py` (records and CSV cells) and `events/views_records.py` (views). The frontend reads the records with `getSignupRecords` and downloads the CSV with `downloadSignupRecordsCsv` in `frontend/app/components/api/eventsAPI.ts`.

## After deploying

Signups created by the old containers while migrations ran have no place in line and sort last. Once the release stack is recreated, run the backfill once in its backend container:

```bash
docker exec <backend-container> python manage.py backfill_signup_line
```

It gives those signups a place in line and adds their `backfilled` entries. It is safe to run again: a rerun adds entries only for signups it gives a place in line, never for signups created after the upgrade.

Use `docker exec` rather than `just dev::run`, which starts a container on the dev stack, or `just db::manage`, which disables the cache so the command's flush of cached signup lists does nothing.

## Coming later

A member's own view of their signup records, the reasons staff give for their changes, and org API token access to the records will build on this ledger. This page will describe them when they land.
