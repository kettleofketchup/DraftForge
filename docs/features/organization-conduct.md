# Organization Conduct

**Conduct** is a locked feature that records whether the people who signed up for an
event actually showed up. From that record it gives each member a show rate, forecasts
turnout for upcoming events, and publishes a ranking on the organization page. Orgs can
also opt in to consequences for members with a low show rate; these are off by default.

A site admin unlocks Conduct per organization, the same way as the other
[locked features](organization-locked-features.md#unlocking-a-feature). The API is
listed in [API Endpoints: Conduct](../api/endpoints.md#conduct), and the permission
rules in [Roles & Permission Matrix](../dev/auth/roles.md#promoter-and-locked-features).
Conduct is a [standing track](../development/org-standing.md#conduct-track), so its
ranking is also served by the generic
[standing endpoints](../api/endpoints.md#organization-standing).

## On the organization page

The organization page shows one tab per enabled standing track, so an org with
Conduct unlocked has a **Conduct** tab next to **Contributions**. A track with more
than one metric gets a metric switcher above its leaderboard. The tab is shown to
anyone who can see the ranking or their own record; outsiders of an org with a
private ranking get no tab, and a `?tab=conduct` link falls back to the default tab.

- **Leaderboard.** Ranked members with rank, show rate and counted events. Members
  with fewer than the minimum counted events show **New** instead of a rate and are
  not numbered. Members with the same rate and event count share a rank.
- **Private ranking.** With **Public ranking** off, members see the note "This
  organization keeps its Conduct ranking private." and only their own row and history.
- **Member history.** Your own history opens with the tab: each event with its
  outcome, source and weight, plus totals per outcome. A new member's history says
  why they show as New. Plain members open only their own history; org staff can open
  any member's, and also see reasons and who made an edit.
- **How the show rate works.** The info button next to the ranking explains how the
  rate is built: what counts as a show or a miss, what is left out, how older events
  weigh less, and why new members lean on the org's baseline. The formula below is the
  reference.

### Conduct settings

Org admins open **Organization Settings > Conduct**; other roles do not see the
section. It holds four groups: **Scoring**, **Late cancel** (window and weight),
**Visibility** (**Public ranking**) and **Enforcement**. A field still at its default
shows a **Default** badge; a changed one has a **Reset** button that puts the default
back. The three enforcement toggles are off by default, and the group stays collapsed
until one is on.

Values are checked in the browser against the same ranges as the server (at most two
decimal places, and the maximum age can't be shorter than the half-life). An error
the server returns for a field is shown under that field and opens its group, even a
collapsed Enforcement group; an error that belongs to no field is shown as a toast.

## On the event page

Event staff (org staff, or staff of the event's league) see the Conduct tools on an
event of an organization with Conduct unlocked. Nobody else sees them.

- **Turnout forecast.** On an event that is upcoming, has sign-ups open or is in roll
  call, a card reads like "30 signed up · expect ~24 (21–27)", with the number of
  signups awaiting approval and, when the event has a capacity, the expected open
  seats. See [Turnout forecast](#turnout-forecast) for how it is worked out.
- **Show-rate badge.** On the signup tabs and the roll-call page, each member's row
  shows their show rate (for example "Show 87%"), or "Show New" for members without
  enough history. A **Needs approval** badge marks members whose signup enforcement
  would hold for review, and a **Blocked** badge marks members it would block.
- **Attendance.** From roll call onwards, a table lists every expected member with
  their outcome, its source, any flag and their show rate. Tick the checkbox on
  several rows and use **Mark attended**, **Mark no-show**, **Mark late cancel** or
  **Excuse**, or set one row's outcome directly. A member nobody has recorded yet shows
  **Attended (default)**; members flagged **Did not confirm at roll call** or
  **Dropped, needs review** show as pending until staff resolve them (see
  [The roll-call rule](#the-roll-call-rule)). **Save** opens the reason dialog
  ([every edit needs a reason](#finalize-and-staff-edits)).
- **Add walk-in.** Searches the org's members only and adds someone who played without
  signing up as attended. Only org staff see the button: league-only event staff can
  edit outcomes but cannot add walk-ins.
- **Read-only cases.** A cancelled event shows "Voided, event cancelled", and an event
  whose attendance was never tracked says so; neither can be edited.

On phones the attendance table keeps the member and outcome columns and stacks the
source, flag and show rate under the member's name.

Signups, cancels, roll call, completing or reopening the event, event edits and
attendance saves all refresh the forecast, the attendance table and the Conduct
ranking.

---

## What is tracked

Each member who was **expected** at an event gets one attendance outcome:

| Outcome | Meaning | Counts toward the score |
|---|---|---|
| `attended` | Showed up | yes, as a show |
| `no_show` | Did not show up | yes, as a miss |
| `late_cancel` | Cancelled shortly before the start | yes, as a partial miss |
| `excused` | Staff excused the absence | no |
| `pending` | Not resolved yet | no |

A member is expected when, at the time the outcome is resolved, their signup is
`approved` or `confirmed`. On a manual-approval event, `rsvp` signups are expected too,
because staff often run those events without approving everyone. Waitlisted,
pending-approval, Maybe (tentative), rejected and staff-cancelled signups are never
expected and never get an outcome.

Each outcome also records where it came from (its **source**): the default, a staff
edit, the system's late-cancel capture, a ready check or voice presence. The start
cull will also supply outcomes once it ships. Ready check and voice data only ever
fill in outcomes; staff can always correct them. Voice attendance requires feed
evidence: a recorded first join, or a present row whose source is `feed`. A manual
presence override alone never grants voice attendance credit.

Nothing is recorded while Conduct is locked, and tracking starts with the next event
after it is unlocked. Past events are not backfilled: there is no record of who showed
up, so a backfill would mark everyone as attended.

---

## Defaults

Owners and admins change these in the **Conduct** section of the organization settings.
Each field shows its default and can be reset to it.

| Setting | Default | Range | What it does |
|---|---|---|---|
| Prior show rate | 0.85 | 0.05 to 1 | The show rate assumed for someone with no history |
| Prior strength | 3 | 0 to 20 | How many events the prior is worth |
| Half-life (days) | 90 | 7 to 730 | After this many days an event counts half as much |
| Max age (days) | 365 | 30 to 1095, and at least the half-life | Older events are ignored |
| Minimum events | 3 | 1 to 20 | Events needed before a member is ranked |
| Late cancel window (hours) | 2 | 0 to 168 | A member cancel this close to the start is a late cancel; 0 turns pre-start capture off |
| Late cancel weight | 0.50 | 0 to 1 | How much of a no-show a late cancel is |
| Public ranking | on | | Off: only org staff see the ranking |
| Back of the line | off, below 0.75 | 0 to 1 | See [Enforcement](#enforcement) |
| Require approval | off, below 0.65 | 0 to 1 | See [Enforcement](#enforcement) |
| Block self sign-up | off, below 0.40 | 0 to 1 | See [Enforcement](#enforcement) |
| Apply to new members | off | | Whether enforcement also applies to members still marked "New" |

Changing a setting re-scores everyone straight away. Scores are computed from the stored
outcomes each time they are read, so there is no rescore step. Every settings change is
written to the `OrgLog`.

Saving a change that affects scores or enforcement also rechecks the open sign-ups in
the organization, so the "Attendance record below org threshold" badge appears or clears
straight away. Locking or unlocking Conduct does the same; while it is locked no badge
is shown.

---

## The score

A member's score is their **show rate**: the share of recent events they showed up to,
with recent events weighing more than old ones. Before someone has much history the
score leans on the org's prior (85% by default), so one missed game does not sink a
new member, and one good game does not make them perfect.

- An attended event counts as a full show, a no-show as a miss, and a late cancel as half
  a miss (with the default weight).
- Excused, pending and voided outcomes, and walk-ins, are left out entirely.
- An event 90 days old counts half as much as one today; an event older than a year is
  ignored.
- Until a member has 3 counted events they are shown as **New** and are not ranked.

!!! info "The formula"
    For a member with counted outcomes *i* from the last `max_age_days`:

    ```
    age_i  = max(0, days since the event started)
    w_i    = 0.5 ** (age_i / half_life_days)
    s_i    = 1 for attended, 0 for no_show, 1 - late_cancel_weight for late_cancel

    show_rate = (prior_strength * prior_show_rate + Σ w_i * s_i)
                / (prior_strength + Σ w_i)
    ```

    The member is **New** while the unweighted count of outcomes is below
    `min_events`. With the defaults, a member with three recent attended events and one
    recent no-show scores (3 × 0.85 + 3) / (3 + 4) ≈ 79%; a member with no history
    scores 85%.

### Turnout forecast

Event staff see a **Turnout forecast** card on an event that is upcoming, has sign-ups
open, or is in roll call. It reads, for example, "30 signed up · expect ~24 (21–27)":
the number of signups holding a seat (including those still awaiting approval), the sum
of their show rates, and an 80% range around it. The card also shows the expected open
seats when the event has a capacity, how many of the signups are new members and, when
any are, how many are awaiting approval.

Signup rows on the event page and on roll call show each member's show rate to event
staff, or "New" for members without enough history.

---

## Late cancels

When a member cancels their own signup (on the web, with the Discord Decline button, by
removing their Discord reaction, or by switching to Maybe):

- **Within the window** (2 hours before the start by default), it is recorded as a
  `late_cancel`.
- **After the start**, it is recorded as a `no_show`, whatever the window is set to.
  Notice given after the start is not notice.
- Earlier than the window, nothing is recorded.

Only cancels by the member count. Staff rejecting, demoting, unconfirming, dropping or
cancelling someone never produces a late cancel or a no-show.

Once an event is completed, cancelled or finalized, a member cancelling (for example by
removing a reaction on an old announcement) changes nothing.

If a member cancels late and then signs up again before the event, the late cancel is
cleared when the event completes. If the event is rescheduled, late cancels are
re-checked against the final start time when it completes.

---

## Finalize and staff edits

Outcomes are **finalized** when the event is completed, either by an admin pressing
**Complete** or by the automatic close. At that point every expected member who has no
other outcome is recorded as `attended`. The org's rule is that everyone attended unless
staff say otherwise, so staff only need to flip the no-shows.

Event staff record attendance in the **Attendance** panel on the event page, from roll
call onwards. Before the event completes, members without an outcome show as "Attended
(default)". Staff can select several members and **Mark attended**, **Mark no-show**, **Mark late
cancel** or **Excuse**, or set one outcome at a time.

!!! warning "Every edit needs a reason"
    Saving asks "Why are you changing attendance?" and needs at least 3 characters. One
    reason covers the whole batch. Each changed outcome is written to the `OrgLog` with
    who changed it, the old and new outcome, and the reason.

Outcomes can still be edited after the event completes; a "Finalized" banner says that
these edits are audited, and they count immediately. Events that were completed before
Conduct existed were not tracked and cannot be edited.

### Walk-ins

**Add walk-in** marks any org member as attended, even if they never signed up (for
example a substitute). Walk-ins are kept in the member's history, labelled "Walk-in",
but never count toward their score: they made no commitment, so they carry no no-show
risk.

### The roll-call rule

On a roll-call event where at least one member confirmed at roll call, approved members
who **never confirmed** were left off the roster. Defaulting them to attended would
inflate exactly the wrong scores, so they stay `pending` and the Attendance panel flags
them "Did not confirm at roll call". Pending outcomes are not counted until staff
resolve them. If nobody confirmed at roll call, the normal default applies.

A signup the system dropped with no recorded reason is flagged "Dropped, needs review"
and also stays pending for staff.

---

## Cancelled and deleted events

- **Cancelled events** void their outcomes, including late cancels: the event did not
  happen, so nothing from it counts. A cancelled event is read-only for conduct; the
  Attendance panel shows "Voided, event cancelled". To count its attendance, reopen the
  event, run it and complete it; the normal finalize then applies.
- **Reopening** an event clears its finalize. Staff edits and late cancels are kept and
  counted again after the next completion; default and automatic outcomes are worked out
  again then.
- **Deleting** an event removes outcomes that were never finalized and voids finalized
  ones. Voided outcomes stay in the member's history, with the event shown as "Removed",
  but no longer count. Deletes from the Django admin do the same. The admin shows the
  event's conduct finalize time as read-only.

---

## Enforcement

All three modes are **off by default**. Turning one on starts from the default threshold
in the table above. A mode applies to a member whose show rate is below its threshold.
New members are exempt unless **Apply to new members** is on. When several modes
apply, the strictest wins: block, then require approval, then back of the line.

**Block self sign-up.** The member cannot sign themselves up (web, Discord button or
reaction, or Maybe). They see: "Your attendance record in this organization is below
what it requires for self sign-up. Ask an organizer to add you." The refusal carries
the eligibility reason `conduct_below_threshold` (rule `conduct-block`), so the web
signup error lists it with the other requirements. Staff can still add the member or
promote them from the waitlist; on an auto-approve event that signup waits as pending
approval, and approving it is the override.

**Require approval.** On an auto-approve event, the member's signup waits as pending
approval with the requirement "Attendance record below org threshold". On a
manual-approval event everyone waits anyway, so the requirement only shows as a badge.
Approving the signup is the override.

**Back of the line.** Among waitlisted members, flagged members are promoted after
everyone without the flag, keeping their order otherwise. A flagged member who signs up
while seats are free is still seated, and seated members are never moved.

!!! note "Public line rank is not the promotion order"
    With back of the line on, the line rank members see is the plain line order, so the
    deferral is never shown to other members. A flagged member may therefore be promoted
    later than their public rank suggests. Staff see "Deferred by conduct: promoted after
    members without the flag" on those signups.

---

## Privacy

- The ranking on the **Conduct** tab shows each ranked member's show rate, number of
  counted events and rank, plus a list of new members. It never shows no-show counts.
- Ranking rows follow the org's member-list rule (`can_view_org_members`), as the
  Contributions leaderboard does; everyone else sees only their own row.
- With **Public ranking** off, only org staff see the ranking. Members still see their
  own row and history on the tab, with a note that the org keeps its ranking private.
- A member's full history (each event, outcome, source and weight) is visible to that
  member and to org staff. In member history, staff reasons and who made an edit are
  shown to org staff only. An event's Attendance panel shows them to that event's
  staff, which includes staff of the event's league.
- The forecast and the Attendance panel are visible to event staff only.
- Deleting a user account deletes that user's conduct history.

!!! note "Removing a member"
    There is no way today to remove someone from an organization while keeping their
    account, so conduct history stays as long as the user exists. If a "remove member"
    action is added later, it has to decide whether to keep or delete the member's
    conduct history.

Merging two accounts (claim approval or Discord merge) moves the outcomes to the
surviving account. If both accounts have an outcome for the same event, a staff edit
wins; otherwise the surviving account's outcome is kept.

---

## Known bypasses

Two paths change an event's state without going through the conduct hooks, the same way
they already bypass Contributions:

- the generic internal transition endpoint (`/api/internal/events/{id}/transition/`);
- the `cleanup_stale_repeater_events` script.

An event closed by either of these is neither finalized nor voided for conduct.
