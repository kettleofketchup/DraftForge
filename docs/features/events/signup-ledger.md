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

The role and means show who acted and how:

| Who acted | Role | Means |
|---|---|---|
| A member on their own signup, on the website | `member` | `web` |
| A staff member on someone else's signup, on the website | `staff` | `web` |
| A member using a Discord button (sign up, decline, tentative) | `member` | `discord_button` |
| A member adding or removing a Discord reaction | `member` | `discord_reaction` |
| The system (waitlist promotion, Discord account merge, cleanup script, test setup) | `system` | `system` |

A staff member acting on their own signup is recorded as `member`. When they used a staff-only action to do it (approve, reject, confirm, unconfirm, demote, a staff add, or a reinstate that bypasses the member rules), the after snapshot carries `extra.staff_power: true`. Approving a profile claim is recorded as the approving staff member, with means `web`.

### Promotions

When a cancel, decline, rejection, switch to tentative or account merge frees a seat, the waitlisted signups that take it each get their own `promoted` entry. Moving a signup to the waitlist promotes nobody; staff fill that seat by hand. Its `caused_by` points at the entry for the change that freed the seat, and it shares that entry's correlation id. Promotions from the `rebalance_event_waitlists` command have no cause.

### Correlation ids

The correlation id groups entries that belong to one action:

| Source | Correlation id |
|---|---|
| Discord button | The Discord interaction id |
| Discord reaction | `reaction:<message id>:<user id>`, the same for the add and the later remove |
| Discord account merge | `merge-<id>`, one per merge |
| Profile claim approval | `claim-<id>`, one per approval |
| Stale repeater cleanup | `cleanup-<id>`, one per run |
| Website | Empty |

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

## For developers

- Every signup service in `events/services.py` takes a required keyword `actor: SignupActor`. Calling one without it raises `TypeError`.
- Build the actor with `SignupActor.for_request_on(request, subject, event)` on the website (pass `staff_only=True` on staff-only endpoints), `SignupActor.discord(user)` in Discord flows (it picks up the bound interaction id), or `SignupActor.system()` where no person acts.
- A new signup mutation must record exactly one entry with `record_signup_change`, inside its own `transaction.atomic` block, after its guards. Take `before = snapshot(signup)` from a row read with `.nocache()` inside the transaction.
- A mutation that frees a seat passes its entry to `_promote_from_waitlist(event, cause=entry)`.

## After deploying

Signups created by the old containers while migrations ran have no place in line and sort last. Once the release stack is recreated, run the backfill once in its backend container:

```bash
docker exec <backend-container> python manage.py backfill_signup_line
```

It gives those signups a place in line and adds their `backfilled` entries. It is safe to run again: a rerun adds entries only for signups it gives a place in line, never for signups created after the upgrade.

Use `docker exec` rather than `just dev::run`, which starts a container on the dev stack, or `just db::manage`, which disables the cache so the command's flush of cached signup lists does nothing.

## Coming later

Views that show a signup's history and a member's signup records, and the reasons staff give for their changes, will build on this ledger. This page will describe them when they land.
