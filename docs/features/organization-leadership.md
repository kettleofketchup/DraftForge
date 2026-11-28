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
the window closes they are frozen. They count toward totals and the points leaderboard
only once the event's results are [released](#anonymity), at the same moment as the
rating; captaining, placement and draft points count straight away. Raising the
minimum reviews after an event has closed hides an event below the new minimum, its
rating and its captain rating points together.

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

**Moderators** are the org owner, org admins, org staff and site staff.

Nothing derived from an event's reviews is shown to anyone but moderators until the
event's results are **released**: the window has closed, the event has at least the
minimum number of reviews, it was not voided by a reopen and, when the org
[requires staff release](#release-gate), a moderator has released it or its
auto-release time has passed. All of an event's reviews then count at once, so a
captain cannot work out a single review by watching the numbers move. Per-event trait
averages are shown to the captain only for events with at least 3 reviews.

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
- **Moderators** see every review of other captains with its rater and live,
  unreleased values, for abuse handling. A moderator who also rated a captain sees
  that captain's other raters too; that is by design.
- **Nobody sees reviews of themselves**, whatever their role, site staff and
  superusers included. On their own captain entries the moderation list returns no
  reviews (no scores, times, ids or raters), no review count, minimum or auto-release
  time, a state of only `released` or `hidden`, and the released aggregate, the same
  as any other captain sees. Their own member panel and leaderboard row show released
  results only.

!!! warning "Two-review events"
    With exactly two released reviews, a rater who tells the captain their own scores
    gives away the other rater's average. Per-trait event averages need three reviews.

## Moderation

Moderators can void a review with a reason (1–500 characters). A voided review stops
counting, and if the window has already closed the captain rating points are
recalculated anyway. The rater cannot undo a staff void by submitting again; a moderator
can restore it. A review carries one `void_kind`: `withdrawn` (the rater withdrew it),
`lifecycle` (the event was reopened or cancelled) or `moderated` (staff). Raters can
resubmit over the first two, never over `moderated`. Restoring puts a review back the
way it was before staff voided it: a review the rater had withdrawn, or one a reopen
voided (including a review voided by staff and then by a reopen), goes back to
`withdrawn` or `lifecycle` and does not count again until its rater resubmits. A live
review is restored only while its rater is still in the captain's rater pool
(`409 not_in_pool` otherwise). When a merge leaves two reviews by the same person, a
staff-voided one always wins. Nobody moderates reviews of themselves, whatever their
role, and another moderator has to act. Voiding or restoring a review of oneself
returns the same `404` as a review that does not exist, so its existence is not
revealed; releasing one's own captain entry is refused with
`403 cannot_release_own_reviews`. Every void and restore is written to the organization log with
the points before and after, and every release with the captains it released.

## Release gate

By default an event's results are released on their own once the window closes with
enough reviews. An org can put a person in between with two settings:

- **Require staff release**: closed events with enough reviews wait as **Pending
  release** until a moderator releases them. A release can cover every pending captain
  of an event or only listed captains; it records when and by whom
  (`released_at`, `released_by`) and cannot be undone. Reopening the event and
  completing it again clears the release along with the old window.
- **Auto-release after (hours)**: an optional fallback, 1 to 720 hours, empty for
  never. A pending result counts as released once `window closes + hours` has passed
  (inclusive). It is worked out whenever results are read, so nothing is written and
  no scheduled task runs; the moderation screen shows the time on pending captains.
  It applies only while staff release is required.

The rating, the per-trait figures and the captain rating points of an event appear
together at release. A moderator cannot release their own results: releasing a list
that includes them is refused, and releasing a whole event skips them. Their results
wait for another moderator, site staff or the fallback.

Changing these settings, or the minimum reviews, moves results in or out of the
released set:

| Change | Effect |
|---|---|
| Turn staff release on | Everything already public stays public: it is stamped as released, with no `released_by` |
| Lengthen or clear the hours while it is on | Results the fallback already released stay released (stamped the same way) |
| Shorten or set the hours | Pending results past the new time are released at once |
| Turn staff release off | Every waiting result is released at once; the settings screen warns first |
| Raise the minimum reviews | Results below the new minimum are hidden, released or not |

When staff release was on before the change, a change that would release the saving
admin's own results, now or later, is refused with `409 would_release_own_results` and
nothing is saved; another admin can make the same change. That covers turning staff
release off, setting the hours where there were none, shortening them, and lowering
the minimum reviews, whenever the admin has a captain entry in the org that is not
voided and not yet released, whether its window is still open or it is pending. A
change that would release one of their results at once is refused the same way. The organization log entry
for a settings change that touches these fields carries `release_stamped` (results
stamped as released) and `release_unlocked` (results newly public).

In an org with a single moderator who also captains, that moderator's results can only
be released by site staff or the fallback. The settings screen warns about this when
staff release is on and no fallback is set, naming the case when the org has only one
moderator.

### Known limitations

- **Counting reviews of yourself.** Void and restore check the review's org (`404`),
  then whether it is about you (`403`), then its state. A moderator who tries review
  ids in turn can count the reviews about themselves, live or withdrawn, before
  release. Answering `404` for these would contradict the clear `403` refusal and
  needs a product decision.
- **Inferring "short".** The own moderation entry hides counts, but a moderator can
  still guess that their results are short of reviews when every other captain was
  released and theirs stays hidden, or when the fallback time they can read in the
  settings has passed.
- **Merged accounts.** When a merge folds two members' snapshots together, reviews
  from the other closed window come along; they are reviews of the same person, so
  nothing about anyone else leaks.
- **Reviews a moderator wrote.** The moderation screen hides **Void** on a review the
  moderator wrote as a teammate, but the API does not refuse it.
- There is no list of results waiting for release across events; each event page
  shows its own.

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
| Require staff release | off | |
| Auto-release after (hours) | empty (never) | 1–720 |
| Send review DMs | off | |
| Show captains their feedback | on | |

The max age must stay at least the half-life. The minimum reviews for points can never
go below 2.

## Review DMs

With **Send review DMs** on, closing an event also DMs every teammate of each captain
on Discord, so they can score their captain without opening the site. The captain is
never DMed about their own review.

In **Organization Settings → Leadership**, select **Preview** beside **Send review DMs**
to see the message with your saved traits, even when sending is off. The preview uses
a sample event and captain. Its score buttons are display-only.

Each DM lists the active traits, one row of 1–5 buttons per trait:

```text
Rate your captain: Ava (Thursday Inhouse)
Reviews close in 3 days
Communication
[ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ]
Drafting
[ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ]
...
2 of 4 scored
[ Review on site ]
```

- A message holds up to 5 traits. An org with 6–8 active traits sends two messages,
  headed "Part 1 of 2" and "Part 2 of 2", and each says "Your review saves once both
  messages are complete."
- A click stores that score; the chosen button turns blue and the status line counts
  the traits scored in that message. When every active trait has a score, the review
  is submitted exactly as if it came from the site, and the message says "Review
  saved. You can change it until ...". Clicking again changes the score until the
  window closes.
- Scores on the site and in the DM are the same review. A review edited on the site
  is picked up by the next click.
- Partial scores never count. They are thrown away when the review is withdrawn or
  voided, or the event is reopened or cancelled.
- The same checks as the site apply to every click. A click after the window closed or
  after the event was reopened gets "Reviews for this event are closed for now."; a
  teammate no longer in the review pool gets "You cannot review this captain."; a
  deactivated trait gets "That trait is no longer used. Finish on the site."; a trait
  added after the DM was sent shows "Traits changed. Finish on the site."
- **Review on site** opens the event page, which lists the captains you can still rate.

**DMs are sent once.** Each teammate gets the DM the first time the event closes, and
never again for that captain:

- Turning the setting on applies to events closed afterwards.
- Reopening and re-closing an event sends nothing new. The old DMs work again for the
  new window, and teammates added on the re-close review on the site.
- A teammate with DMs closed or no Discord account reviews on the site.

Every DM is recorded in the [Discord DM ledger](../development/discord-dm-ledger.md)
with its status and click count.

## Private captain feedback

With **Show captains their feedback** off, captains see nothing review-derived about
themselves: their rating, trait ratings, per-event results and captain rating points
are hidden, and they see "Your org keeps captain feedback private." instead.

- Their own row is left out of every rating leaderboard. On the points leaderboard
  their own row shows only points that do not come from reviews (such as captained
  points), and the organization total they see leaves out their rating points.
- On the event page their own captain entry shows no aggregate or release state.
- Staff who captain get no exemption.
- Staff views of other members and other members' view of a public ranking are
  unchanged, including the captain's own row and rating.
- Points that do not come from reviews stay visible.

## Using Leadership

### The Leadership tab

The organization page gets a **Leadership** tab once the feature is unlocked. The
metric picker chooses the board: **Rating** (overall), **Points** (with a period
picker) and one board per active trait. Adding or renaming a trait in the settings
updates the picker without a reload.

Selecting a row opens that member's panel:

- the overall rating, with a **New** badge while the captain has fewer released
  reviews than the org's "Reviews to be ranked";
- "No released ratings yet" until an event's results are released;
- **Points all time** and **Points this month**;
- one bar per trait with a released rating; a trait with no released rating says
  **Not released** and draws no bar;
- **Rated events**: each event the captain was rated for, with the team, its
  placement and the captain rating points. A released event with fewer than 3
  reviews shows the review count but no per-trait averages.

Which events are listed depends on who is looking:

- a captain viewing their own panel sees released events only;
- a moderator viewing another captain also sees events still inside their window,
  without the minimum number of reviews or waiting for release, marked **Not
  released**. For a moderator the headline rating, review count and trait bars
  include those unreleased reviews; the panel labels the count "(includes
  unreleased)" and says the figures are visible to moderators only. A moderator
  viewing their own panel gets the captain's view.

The points totals count captaining, placement and draft points from every event,
including events that are still in their review window, did not get enough reviews
or are waiting for release; captain rating points count only once released. A
captain's own list leaves those events out, so it does not add up to the totals; the
panel says so under the totals.

Who can open which panel:

- every member can open their own;
- moderators can open anyone's;
- other members can open other captains only when the leaderboard is public.

Any row on a visible board can be clicked; when the backend refuses the panel it
shows "Only org staff can see other captains' details."

A captain's own panel shows aggregates only: their rating, per-trait averages for
released events with at least 3 reviews, and their points. It never shows who rated
them or any single review. A note at the top says who else can see it: only the
captain and moderators on a private board, or, when the leaderboard is public,
every member for the rating and points (the per-event detail stays with the captain
and moderators).

### Rate your captain

A teammate who can still rate a captain sees a **Rate your captain** banner on the
event page and a card at the top of the Leadership tab, one entry per captain. The
dialog has a 1 to 5 score for each active trait, as a radio group that works with the
keyboard (arrow keys move between scores). Every trait must be scored.

While the window is open, a countdown shows the time left and the rater can submit,
edit (**Update**) or **Withdraw** the review. When the countdown reaches zero the
dialog shows "The review window has closed." and its buttons are disabled. A review
an organizer voided is read-only: the dialog says so and offers only **Close**. Other
refusals, such as a captain the rater can no longer rate, are shown as plain messages
inside the dialog. The dialog stays open with the message even when the refusal also
removes the captain from the pending list.

**Your reviews**, a collapsed list on the same card, shows the rater's own past
reviews with their scores, and marks a review that was withdrawn, no longer counted
after a reopen, or removed by an organizer. It never shows anyone else's review.

### Moderation on the event page

Moderators see a **Captain reviews** section on the event page's Details tab for
any event with captain snapshots, including an event reopened after its reviews were
voided. For each captain it shows a release badge (**Released**, **Pending release**,
**Window open**, **Not enough reviews** or **Voided**), the live review count against
the minimum, and a table of the reviews with the rater, the scores and the status. A
pending captain shows its auto-release time when a fallback is set; a released one
shows who released it and when. If the reviews fail to load, the section says so
instead of disappearing.

When the org requires staff release, **Release all pending (n)** releases every
pending captain of the event except the moderator's own, and **Release** on a captain
releases only that one. Both ask for confirmation, listing the captains, because a
release cannot be undone. A refusal is shown as a toast.
**Void** asks for a reason (1 to 500 characters) and marks the review "Voided by
staff" with the reason under the rater; **Restore** puts it back. On teams the
moderator captained, the section shows only a **Released** or **Hidden** badge, the
released aggregate and the note "You captained this team. Another org moderator, or
site staff, has to release it. Your results show here once released.", with no
reviews, counts or actions. A review the moderator wrote as a teammate shows "Your
review" in place of **Void** and **Restore**.

### Settings

Org admins edit Leadership under **Settings → Leadership**:

- the review window, minimum reviewers, reviews to be ranked, the baseline rating and
  strength, half-life, max age and whether the leaderboard is public;
- the captain rating maximum and the points per kind (captained, placements, draft
  completed). Each field shows a **Default** badge and a reset button that restores
  the default;
- **Release**: **Require staff release** and **Auto-release after (hours)** (empty for
  no fallback; disabled while staff release is off). The screen warns when a saved
  "on" is being turned off ("Turning this off releases every result that is
  waiting.") and when staff release is on with no fallback, naming the sole-moderator
  case. A save refused with `would_release_own_results` shows the reason under the
  group instead of a toast;
- **Send review DMs** (in the Reviews group) and **Show captains their feedback** (in
  the Visibility group), described in [Review DMs](#review-dms) and
  [Private captain feedback](#private-captain-feedback);
- the trait list: add a trait, rename it, move it up or down, and switch it active or
  inactive. At least one trait stays active, and at most 8 can be. **Delete** asks
  for confirmation on a saved trait; a trait added since the last save is simply
  removed. A trait that already has scores is refused ("This trait has scores.
  Deactivate it instead.") and switched to inactive for the next save; a trait
  another admin already deleted is dropped from the list.

The settings and the trait list are saved together with the section's save button.
Server-side validation errors are shown under the field they belong to; an error
that names no field is shown as a toast.

## API

All endpoints live under `api/organizations/<org_id>/leadership/` and answer
`403 feature_locked` while the feature is locked.

| Method / path | Who | Purpose |
|---|---|---|
| `GET reviews/pending/` | member | Open windows where you can rate, optional `?event_id=`; your current scores or `null` |
| `GET reviews/mine/` | member | Your own reviews in this org, open and closed windows, with `void_kind`; no aggregates |
| `PUT events/<event_id>/captains/<org_user_id>/review/` | rater | Submit or replace your review: `{"scores": {"<trait>": 1-5}}` |
| `DELETE events/<event_id>/captains/<org_user_id>/review/` | rater | Withdraw your review |
| `GET members/<org_user_id>/` | self, moderator; members when public | Rating summary; history for self and moderators. Unreleased events only for a moderator viewing someone else |
| `GET events/<event_id>/reviews/` | moderator | Every review with its rater and the release fields below, except reviews of yourself |
| `POST events/<event_id>/release/` | moderator | Release results: `{"captains": [org_user_id, ...]}` (optional, 1–64 ids) or `{}` for every pending captain |
| `POST reviews/<pk>/void/` | moderator | Void a review: `{"reason": "..."}` |
| `POST reviews/<pk>/unvoid/` | moderator | Restore a staff-voided review (no body) |
| `GET traits/`, `PUT traits/` | member or moderator / admin | List or upsert traits |
| `DELETE traits/<key>/` | admin | `409 trait_in_use` once scored |
| `GET/PATCH settings/` | admin | Every setting plus `defaults`, `ranges`, `points` (one entry per fixed kind) and `moderator_count`. PATCH takes any subset of the settings and `points: {"<kind>": int or null}` (`null` restores the default); unknown keys and out-of-range values are `400` |

**Who**: *moderator* is the org owner, an org admin, org staff or site staff
(`has_org_staff_access`); *admin* is the owner, an org admin or site staff
(`has_org_admin_access`).

The moderation response carries `require_staff_release` and, per captain,
`release_state` (`voided`, `open`, `short`, `pending` or `released`), `released_at`,
`released_by` (`{pk, username}`, or `null` for auto-release and settings stamps),
`auto_release_at` (only on a pending captain with a fallback set), `live_reviews`,
`release_floor` and `can_release` (only when pending). On your own captain entry the
state is `released` or `hidden`, the counts, floor and auto-release time are `null`,
`can_release` is false and `reviews` is `null`.

Every captain entry also carries `feedback_private`. When it is true (your own entry
while **Show captains their feedback** is off), the aggregate is `null` and the release
fields read `hidden`. The member summary (`members/<org_user_id>/`) carries
`feedback_private` too; when it is true, `rating` and every trait rating are `null`,
`status` is `new`, `reviews` is `null`, `events` is omitted and `points` leaves out
captain rating points. Standing leaderboards and the org's standing tracks carry
`own_private` for the same case.

A release answers `200 {"released": [org_user_id, ...], "skipped": [{"org_user_id",
"code"}]}`. A list of captains is all or nothing: the first refusal in the order own,
voided, window open, too few reviews, already released is returned and nothing is
released. Without a list, those captains are skipped with the codes `own_snapshot`,
`voided`, `window_open`, `not_enough_reviews` or `already_released`.

Refusals carry a `code`: `review_window_closed` (409), `snapshot_voided` (409, the event
was reopened or cancelled), `not_in_pool` (403), `review_moderated` (403),
`invalid_scores` (400), `reason_required` (400),
`not_moderated` (409, restoring a review staff did not void), `trait_in_use` (409),
`not_permitted` (403, not a moderator), `cannot_release_own_reviews` (403),
`release_not_required` (409, the org does not require staff release),
`already_released` (409), `window_open` (409), `not_enough_reviews` (409),
`nothing_to_release` (409), `would_release_own_results` (409, settings) and
`not_found` (404). Any id from another organization is `404`, for admins too. Review
submits and withdrawals are limited to 30 a minute per user.

While the feature is unlocked, the event detail response (`GET /api/events/<id>/`) also
carries `can_review_captains` and `pending_captain_reviews` for the signed-in member: the
number of captains on that event they can still rate. A review staff voided is not
pending; a withdrawn one is. Both fields come from the one query that resolves the
viewer's membership.

Review DM clicks go through the internal endpoint
`POST /api/internal/discord/leadership/review-click/` (bot only, 30 a minute per
Discord user), and the send task plans its messages with
`POST /api/internal/leadership/review-dms/plan/`.

## Logging

Leadership logs with `system="org", subsystem="leadership"`. Rater ids appear only at
debug level (`captain_review_rater`); info lines carry the review, snapshot and event
ids.

A release logs `leadership_results_released` after commit with `org_id`, `event_id`,
`actor_id`, `captain_org_user_ids` and `count`, and writes an organization log entry
`release_captain_reviews` with the event and captains. `leadership_settings_updated`
carries `release_stamped` and `release_unlocked` when a release-related setting
changed.
