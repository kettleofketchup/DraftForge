# Signup Ledger & Line Position

Every event signup has a place in line and an original sign-up that never changes. The signup ledger keeps a durable record of every signup change: who made it, how, when, and the signup before and after.

## Place in line

Each signup gets a place in its event's line when it is created:

- **`line_seq`** is the signup's number in the event's line. The next signup gets the current highest number plus one.
- **`signed_up_at`** is the time the signup took that place.

Signups are listed in line order (`line_seq`, then id). The signup API also returns **`line_rank`**: the signup's 1-based position among the event's signups that are still in line. Cancelled, rejected and dropped signups are not in line, so their `line_rank` is empty; they keep their `line_seq`.

Moving a signup to another event gives it a new place at the end of that event's line.

### One signup per member

A member has one signup per event, and every change happens on that signup. Signing up again after a cancel, a decline or a rejection, and switching between Main and Maybe, update the existing signup: its id, its original sign-up and its ledger history stay the same. The only things that delete a signup are deleting its event and an [account merge](#account-merges) that finds both accounts signed up.

### The line is the queue

The line is the only queue an event has:

- **Promotion** takes the next waitlisted signup in line order. Its role, member class and commitment don't change the order.
- **`waitlist_position`** in the signup API is worked out on each read: the signup's 1-based rank among the event's waitlisted signups, in line order. It is empty for a signup that is not waitlisted. The website's waitlist tab and the Discord signup post both use it, so they show the same order.
- **Moving a signup to the waitlist** (demote) sends it to the back of the line.

The upgrade that made the line the queue reorders any waitlist whose line order differed from its old stored waitlist order, so every waitlist keeps the order it showed before. It changes only `line_seq`, never `signed_up_at`, and writes no ledger entries.

### Line rules

Two event settings, both on by default, decide whether a signup that comes back or switches goes to the back of the line ("restamp": a new `line_seq` and `signed_up_at`) or keeps its place. See [RSVP & Signups](../events.md#rsvp-signups) for where staff set them.

| From | Action | Setting read | Back of the line when | Ledger action |
|---|---|---|---|---|
| No signup | RSVP or Maybe | none | new place at the back | `signed_up` |
| Cancelled or rejected, after a real sign-up | RSVP or Maybe | `line_withdraw_forfeits` | the setting is on | `resigned_up` |
| Declined without ever signing up | RSVP or Maybe | none | always | `signed_up` |
| Cancelled, after a real sign-up | Member reinstate | `line_withdraw_forfeits` | the setting is on | `reinstated` |
| Dropped | Member reinstate | none | refused: "You were dropped from this event" | none |
| Cancelled or dropped, signups open, event full | Staff reinstate | none | always | `reinstated` |
| Cancelled or dropped with signups open and a free seat; or cancelled, rejected or dropped during roll call | Staff reinstate | none | never | `reinstated` |
| Declined without ever signing up | Any reinstate | none | always | `reinstated` |
| Cancelled, rejected or Maybe | Staff add | none | always | `staff_added` |
| Maybe | RSVP | `line_switch_restamps` | the setting is on | `switched_commitment` |
| Holding a seat or waitlisted | Maybe | `line_switch_restamps` | the setting is on | `switched_commitment`, plus `promoted` entries if a seat was freed |
| Holding a seat | Demote | none | always | `demoted` |

With both settings off, a member who returns or switches keeps their old place. If the event is full they wait on the waitlist in that place and are promoted before anyone who signed up after them.

Every restamp logs `signup_line_restamped` (`system=events`, `subsystem=line`) with a `reason`: `resign_up`, `switch`, `demote`, `member_reinstate`, `staff_reinstate`, `staff_add` or `bare_decline`.

## Commitment

Each signup is either a **main** or a **maybe** signup (`commitment`). A tentative signup is a maybe; every other signup is a main. A tentative signup that is cancelled and then reinstated by a staff member comes back as a main. Each signup also has an RSVP class (`rsvp_class`), which is `standard` for every signup today.

## Original sign-up

Each signup remembers when and how the member first signed up for the event:

| Field | Meaning |
|---|---|
| `first_signed_up_at` | When the member first signed up |
| `first_commitment` | Their commitment at that first sign-up |
| `first_rsvp_class` | Their RSVP class at that first sign-up |

These fields never change once set. If a member cancels and signs up again, or switches between tentative and RSVP, the signup keeps the original values while the [line rules](#line-rules) decide its place in line. The app refuses any change to them, and the Django admin shows them as read-only.

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

When a cancel, decline, rejection, switch to tentative or account merge frees a seat, the waitlisted signups that take it, in line order, each get their own `promoted` entry. Moving a signup to the waitlist promotes nobody; staff fill that seat by hand. Its `caused_by` points at the entry for the change that freed the seat, and it shares that entry's correlation id. Promotions from the `rebalance_event_waitlists` command have no cause.

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

!!! info "Reasons"
    Staff signup actions on the website fill `reason` with the text staff give. The event's [Staff reasons](../events.md#staff-reasons) setting decides when a reason is required. Members acting on their own signup and system changes are exempt, as are one-click staff actions when the setting does not require a reason.

## For developers

- Every signup service in `events/services.py` takes a required keyword `actor: SignupActor`. Calling one without it raises `TypeError`.
- Build the actor with `SignupActor.for_request_on(request, subject, event)` on the website (pass `staff_only=True` on staff-only endpoints), `SignupActor.discord(user)` in Discord flows (it picks up the bound interaction id), or `SignupActor.system()` where no person acts.
- A new signup mutation must record exactly one entry with `record_signup_change`, inside its own `transaction.atomic` block, after its guards. Take `before = snapshot(signup)` from a row read with `.nocache()` inside the transaction.
- A mutation that frees a seat passes its entry to `_promote_from_waitlist(event, cause=entry)`.
- A staff signup mutation calls `require_staff_reason(...)` from `events/ledger.py` after its state checks and before any write, and records the returned trimmed reason. It raises `StaffReasonRequired` (400 `{"error": "reason_required"}`) when the event's policy needs a reason and none was given.
- `PLACEMENT_ACTIONS` in `events/ledger.py` lists the ledger actions that count as placements: `staff_added`, `demoted`, `reinstated`, plus `voided_withdrawal`, `transferred_out`, `transferred_in` and `swapped` for future staff actions. `is_placement(action, from_status=...)` also counts `approved` from `waitlisted`. This is the extension point for later placement work; the frontend copy in `components/events/staffReasonPolicy.ts` must match.

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
| `before`, `after` | The signup snapshot (`status`, `commitment`, `rsvp_class`, `signed_up_at`, `line_seq`, `waitlist_position`, `event_team_id`, `extra`), or `null` when there is none or the stored snapshot cannot be read. `waitlist_position` is the computed waitlist rank at that moment |
| `rules_overridden` | A list of rule names, empty today. A stored value that is not a list of strings comes back as `[]` and logs `signup_history_rules_invalid` |
| `caused_by` | The id of the causing entry, or `null` |

Left out on purpose: `correlation_id`, the event and member snapshots, and any `extra` key other than `staff_power`, `mmr_override`, `game_type`, `from_user_id`, `discarded_duplicate`, `discarded_signup_id` and `event_id`.

Errors:

- **404** when the event does not exist.
- **403** with an empty body for anyone who is not event staff, including anonymous callers. This check runs before the params are read, so non-staff learn nothing from them.
- **400** for a bad param: `{"user": ["Invalid user."]}`, `{"action": ["Invalid action."]}`, `{"cursor": ["Invalid cursor."]}` or `{"page_size": ["Invalid page size."]}`.

The frontend reads it with `getEventSignupHistory` and the `useSignupHistory` hook (query key `['event-signup-history', eventId, filters]`). Every staff signup mutation invalidates that key for the event.

### Stored waitlist position

The `waitlist_position` database column is still written (the next number at the end when a signup joins the waitlist, empty when it leaves) so that rolling back to an older release keeps a sensible waitlist order. Nothing orders signups by it any more, and a signup's Django admin page shows the computed rank next to it. A follow-up will drop the column and these writes once a release with the line rules has run without a rollback.

## After deploying

Signups created by the old containers while migrations ran have no place in line and sort last. Once the release stack is recreated, run the backfill once in its backend container:

```bash
docker exec <backend-container> python manage.py backfill_signup_line
```

It gives those signups a place in line and adds their `backfilled` entries. It is safe to run again: a rerun adds entries only for signups it gives a place in line, never for signups created after the upgrade.

Use `docker exec` rather than `just dev::run`, which starts a container on the dev stack, or `just db::manage`, which disables the cache so the command's flush of cached signup lists does nothing.

## Coming later

A member's own view of their signup records will build on this ledger. This page will describe them when they land.
