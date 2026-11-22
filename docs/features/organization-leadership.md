# Organization Leadership

**Leadership** is a locked feature that credits members for captaining teams and lets
their teammates rate them. A captain earns points for captaining, for where the team
placed and for finishing the draft, and teammates score the captain from 1 to 5 on a
short list of traits once the event is over.

A site admin unlocks Leadership per organization, the same way as the other
[locked features](organization-locked-features.md#unlocking-a-feature). Leadership is
a [standing track](../development/org-standing.md), so its leaderboards are served by
the generic [standing endpoints](../api/endpoints.md#organization-standing).

## What is tracked

When an event that has a tournament is completed, every team's captain at that moment
is recorded, together with the team's placement and the teammates who may rate them.
That record is fixed: later changes to the team or the bracket do not change it. To
pick up a correction, reopen the event and complete it again.

| Points | Default | When |
|---|---|---|
| Captained | 5 | Captain of a team when the event completes |
| Team placed 1st / 2nd / 3rd | 10 / 6 / 3 | The team's placement at completion |
| Draft completed | 2 | The tournament's team draft finished |
| Captain rating | up to 10 | From teammates' reviews, see below |

Org admins can change the fixed point values and the captain rating maximum in the
Leadership settings. New values apply to events completed after the change; points
already awarded keep their value.

While Leadership is locked, completing an event records no captains, opens no review
window and awards nothing. Cleanup still runs whatever the switch says: reopening,
cancelling or deleting an event, merging accounts and deleting a user always update
existing leadership data.

A captain must have an approved or confirmed signup for the event. Raters are the
captain's team members who also had an approved or confirmed signup, minus the
captain; when [Conduct](organization-conduct.md) is unlocked they must also be marked
as attended. Drop-ins and deputy captains get no special treatment.

## The review window

Completing the event opens a review window, 72 hours by default. While it is open each
rater can submit one review of their captain, edit it or withdraw it. A review scores
**every** active trait from 1 to 5. The default traits are Communication, Drafting,
Composure and Sportsmanship; org admins can rename, reorder, add (up to 8 active) or
deactivate traits. A trait that has scores cannot be deleted, only deactivated.

Reopening or cancelling the event voids its reviews and takes back its leadership
points. Completing it again opens a fresh window; raters whose reviews were voided by
the reopen can submit again. Deleting the event removes everything.

## How ratings work

Each review is reduced to its average across traits, so every rater counts equally.
The captain rating points for the event are the average of those, scaled to the org's
maximum. They are only awarded once enough teammates have reviewed (2 by default) and
are recalculated on every submit, edit or withdrawal while the window is open. After
the window closes they are frozen.

!!! info "Formula"
    `points = round(max_points × (event_average − 1) / 4)`, where `event_average` is
    the mean of each review's mean trait score and halves round up. It is computed
    with exact fractions, so a 2.5 never rounds down through float error. Fewer than
    the minimum reviews, or a result of 0, gives no row.

    Example: three reviews scoring every trait 5, 4 and 4 give per-review values of
    1.0, 0.75 and 0.75 on the 0–1 scale, a mean of 0.833, and 8 points at maximum 10.

The leaderboard rating per trait uses the shared standing scorer: recent events weigh
more (half-life 180 days, events older than 730 days are ignored), and a captain with
few reviews leans on the org's baseline (3.0 at strength 2). The overall rating is the
mean of the trait ratings. Captains need at least 3 reviews to be ranked; below that
they show as new.

Leaderboard metrics: **Rating** (overall), **Points** (per period) and one
`rating.<trait>` metric per active trait.

## Anonymity

Nothing derived from an event's reviews is shown to anyone but org admins until the
window has closed **and** the event has at least the minimum number of reviews. All of
an event's reviews then count at once, so a captain cannot work out a single review by
watching the numbers move. Per-event trait averages are shown to the captain only for
events with at least 3 reviews.

Released numbers also stay put when a rater leaves. If a rater deletes their account, or
a merge makes one of two reviews by the same person redundant, after the window has
closed, the review stays and only loses its rater. Inside the window it is deleted and
the captain rating recalculated as usual.

- **Captains** see their overall and per-trait rating, their released review count and
  their points. They never see who rated them or any single review.
- **Other members** see a captain's overall rating and points when the leaderboard is
  public, but no per-event detail.
- **Raters** see their own scores, before and after the window closes, and whether a
  review was withdrawn, voided by a reopen or voided by staff. Never anyone else's.
- **Org admins** see every review with its rater and live, unreleased values, for
  abuse handling. Reviews of themselves are left out entirely: on their own captain
  entries the moderation list returns no reviews (no scores, times, ids or raters) and
  only the released aggregate, the same as any other captain sees.

!!! warning "Two-review events"
    With exactly two released reviews, a rater who tells the captain their own scores
    gives away the other rater's average. Per-trait event averages need three reviews.

## Moderation

Org admins can void a review with a reason (1–500 characters). A voided review stops
counting, and if the window has already closed the captain rating points are
recalculated anyway. The rater cannot undo a staff void by submitting again; an admin
can restore it. A review carries one `void_kind`: `withdrawn` (the rater withdrew it),
`lifecycle` (the event was reopened or cancelled) or `moderated` (staff). Raters can
resubmit over the first two, never over `moderated`. Restoring puts a review back the
way it was before staff voided it: a review the rater had withdrawn, or one a reopen
voided (including a review voided by staff and then by a reopen), goes back to
`withdrawn` or `lifecycle` and does not count again until its rater resubmits. A live
review is restored only while its rater is still in the captain's rater pool
(`409 not_in_pool` otherwise). When a merge leaves two reviews by the same person, a
staff-voided one always wins. An admin cannot
moderate reviews of themselves: another admin has to act. Every void and restore is
written to the organization log with the points before and after.

## Settings

| Setting | Default | Range |
|---|---|---|
| Review window (hours) | 72 | 1–336 |
| Captain rating maximum | 10 | 0–100 |
| Minimum reviews for points | 2 | 2–20 |
| Reviews to be ranked | 3 | 1–50 |
| Baseline rating | 3.0 | 1–5 |
| Baseline strength | 2 | 0–20 |
| Half-life (days) | 180 | 7–730 |
| Max age (days) | 730 | 30–1825 |
| Public leaderboard | off | |

The max age must stay at least the half-life. The minimum reviews for points can never
go below 2.

## Using Leadership

### The Leadership tab

The organization page gets a **Leadership** tab once the feature is unlocked. The
metric picker chooses the board: **Rating** (overall), **Points** (with a period
picker) and one board per active trait. Adding or renaming a trait in the settings
updates the picker without a reload.

Selecting a row opens that member's panel:

- the overall rating, with a **New** badge while the captain has fewer released
  reviews than the org's "Reviews to be ranked";
- "No released ratings yet" until a review window closes with enough reviews;
- **Points all time** and **Points this month**;
- **Rated events**: each event the captain was rated for, with the team, its
  placement and the captain rating points. An event still inside its window, or
  without the minimum number of reviews, is marked **Not released**. A released event
  with fewer than 3 reviews shows the review count but no per-trait averages.

The rated events list does not add up to the points totals: the totals also count
captaining, placement and draft points from events that are still in their review
window or did not get enough reviews, and those events are not listed. The panel says
so under the totals.

Who can open which panel:

- every member can open their own;
- org admins can open anyone's;
- other members can open other captains only when the leaderboard is public. Org
  staff who are not admins cannot open other captains from the tab.

A captain's own panel shows aggregates only: their rating, per-trait averages for
released events with at least 3 reviews, and their points. It never shows who rated
them or any single review.

### Rate your captain

A teammate who can still rate a captain sees a **Rate your captain** banner on the
event page and a card at the top of the Leadership tab, one entry per captain. The
dialog has a 1 to 5 score for each active trait, as a radio group that works with the
keyboard (arrow keys move between scores). Every trait must be scored.

While the window is open, a countdown shows the time left and the rater can submit,
edit (**Update**) or **Withdraw** the review. When the countdown reaches zero the
dialog shows "The review window has closed." and its buttons are disabled. A review
an organizer voided is read-only: the dialog says so and offers no buttons. Other
refusals, such as a captain the rater can no longer rate, are shown as plain messages
inside the dialog.

**Your reviews**, a collapsed list on the same card, shows the rater's own past
reviews with their scores, and marks a review that was withdrawn, no longer counted
after a reopen, or removed by an organizer. It never shows anyone else's review.

### Moderation on the event page

Org admins see a **Captain reviews** section on the event page's Details tab for
events that are in progress, completed or cancelled. For each captain it shows whether the rating is
released and a table of the reviews with the rater, the scores and the status.
**Void** asks for a reason (1 to 500 characters) and marks the review "Voided by
staff" with the reason under the rater; **Restore** puts it back. On teams the admin
captained, the section shows only the released aggregate and the note "Another admin
has to moderate its reviews", with no reviews and no actions.

### Settings

Org admins edit Leadership under **Settings → Leadership**:

- the review window, minimum reviewers, reviews to be ranked, the baseline rating and
  strength, half-life, max age and whether the leaderboard is public;
- the captain rating maximum and the points per kind (captained, placements, draft
  completed). Each field shows a **Default** badge and a reset button that restores
  the default;
- the trait list: add a trait, rename it, move it up or down, and switch it active or
  inactive. At least one trait stays active, and at most 8 can be. **Delete** is
  offered only for saved traits and asks for confirmation; a trait that already has
  scores is refused ("This trait has scores. Deactivate it instead.") and switched to
  inactive for the next save.

The settings and the trait list are saved together with the section's save button.
Server-side validation errors are shown under the field they belong to.

## API

All endpoints live under `api/organizations/<org_id>/leadership/` and answer
`403 feature_locked` while the feature is locked.

| Method / path | Who | Purpose |
|---|---|---|
| `GET reviews/pending/` | member | Open windows where you can rate, optional `?event_id=`; your current scores or `null` |
| `GET reviews/mine/` | member | Your own reviews in this org, open and closed windows, with `void_kind`; no aggregates |
| `PUT events/<event_id>/captains/<org_user_id>/review/` | rater | Submit or replace your review: `{"scores": {"<trait>": 1-5}}` |
| `DELETE events/<event_id>/captains/<org_user_id>/review/` | rater | Withdraw your review |
| `GET members/<org_user_id>/` | self, admin; members when public | Rating summary; history for self and admins |
| `GET events/<event_id>/reviews/` | admin | Every review with its rater, except reviews of yourself |
| `POST reviews/<pk>/void/` | admin | Void a review: `{"reason": "..."}` |
| `POST reviews/<pk>/unvoid/` | admin | Restore a staff-voided review (no body) |
| `GET traits/`, `PUT traits/` | member / admin | List or upsert traits |
| `DELETE traits/<key>/` | admin | `409 trait_in_use` once scored |
| `GET/PATCH settings/` | admin | Every setting plus `defaults`, `ranges` and `points` (one entry per fixed kind). PATCH takes any subset of the settings and `points: {"<kind>": int or null}` (`null` restores the default); unknown keys and out-of-range values are `400` |

Refusals carry a `code`: `review_window_closed` (409), `snapshot_voided` (409, the event
was reopened or cancelled), `not_in_pool` (403), `review_moderated` (403),
`cannot_moderate_own_reviews` (403), `invalid_scores` (400), `reason_required` (400),
`not_moderated` (409, restoring a review staff did not void), `trait_in_use` (409) and
`not_found` (404). Any id from another organization is `404`, for admins too. Review
submits and withdrawals are limited to 30 a minute per user.

While the feature is unlocked, the event detail response (`GET /api/events/<id>/`) also
carries `can_review_captains` and `pending_captain_reviews` for the signed-in member: the
number of captains on that event they can still rate. A review staff voided is not
pending; a withdrawn one is. Both fields come from the one query that resolves the
viewer's membership.

## Logging

Leadership logs with `system="org", subsystem="leadership"`. Rater ids appear only at
debug level (`captain_review_rater`); info lines carry the review, snapshot and event
ids.
