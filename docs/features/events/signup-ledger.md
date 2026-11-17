# Signup Ledger & Line Position

Every event signup has a place in line and an original sign-up that never changes, and every signup keeps a durable record of its changes.

## Place in line

Each signup gets a place in its event's line when it is created:

- **`line_seq`** is the signup's number in the event's line. The next signup gets the current highest number plus one.
- **`signed_up_at`** is the time the signup took that place.

Signups are listed in line order (`line_seq`, then id). The signup API also returns **`line_rank`**: the signup's 1-based position among the event's signups that are still in line. Cancelled and rejected signups are not in line, so their `line_rank` is empty.

Moving a signup to another event gives it a new place at the end of that event's line.

!!! note "Waitlist tab order"
    The website's waitlist tab lists signups in line order. The upgrade reorders existing waitlists to match waitlist order, which is the order Discord shows and promotion uses. Until the waitlist rework lands, a member that a staff member moves to the waitlist afterwards keeps their place in line on the website, so the website and Discord can show that member in different places.

## Commitment

Each signup is either a **main** or a **maybe** signup (`commitment`). A tentative signup is a maybe; every other signup is a main. Each signup also has an RSVP class (`rsvp_class`), which is `standard` for every signup today.

## Original sign-up

Each signup remembers when and how the member first signed up for the event:

| Field | Meaning |
|---|---|
| `first_signed_up_at` | When the member first signed up |
| `first_commitment` | Their commitment at that first sign-up |
| `first_rsvp_class` | Their RSVP class at that first sign-up |

These fields never change. If a member cancels and signs up again, or switches between tentative and RSVP, the new signup keeps the original values while its place in line moves to the end. The app refuses any change to them, and the Django admin shows them as read-only.

## Signup record

The signup ledger (`SignupLedgerEntry`) is an append-only record of signup changes. Each entry stores:

- **Who:** the member the change is about and the person who made it (a member, a staff member or the system), plus whether it was done on someone else's behalf.
- **How:** the means, such as the website, a Discord button or the system.
- **When:** the time of the change.
- **What:** snapshots of the signup before and after, and of the event and the member at that moment.

Entries cannot be edited or deleted through the app or the admin. They outlive the things they describe:

- Deleting an event or a signup leaves its entries in place, with the event snapshot still readable.
- Deleting a user clears the link to that user, and the snapshot keeps their name and Discord ID.
- Merging Discord accounts moves the entries to the remaining account.

Existing signups got a single `backfilled` entry when the ledger was added. It marks where each signup's history starts and is not a change in itself.

## After deploying

Signups created by the old containers while migrations ran have no place in line and sort last. Once the release stack is recreated, run the backfill once:

```bash
just dev::run 'python manage.py backfill_signup_line'
```

It gives those signups a place in line and adds their `backfilled` entries. It is safe to run again.

## Coming later

Views that show a signup's history and a member's signup records will build on this ledger, and this page will describe them when they land.
