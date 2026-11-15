# Organization Locked Features

Two locked features can be unlocked per organization: **Promotion** (a dashboard for
inviting past players to upcoming events over Discord DMs) and **Contributions** (a
points ledger and leaderboard for the people who host, help and promote). This page is
the guide for org owners and admins. The API is listed in
[API Endpoints: Organization locked features](../api/endpoints.md#organization-locked-features),
and the permission rules in [Roles & Permission Matrix](../dev/auth/roles.md#promoter-and-locked-features).

Host and helper assignment, the **Complete** action and the event end time are not
locked: they work for every organization. See [Events](events.md#end-time-completion-and-staff).

---

## Unlocking a feature

Only a site admin (`is_staff` or `is_superuser`) can unlock or lock a feature. There
are two places to do it:

- the **Locked features** panel at the bottom of the organization page (shown only to
  site admins), with a switch and a notes field per feature;
- Django admin, under **Org features**.

Both write through the same service, which records who unlocked the feature, when, and
an `OrgLog` entry (`enable_feature` / `disable_feature`). The notes field is for
payment provenance (for example "paid via PayPal, Nov 2026"); it is never shown to
anyone but site admins. Feature rows are never deleted: locking sets `enabled` off and
keeps the notes.

The two switches are independent. Promotion works without Contributions.

!!! info "Locked means invisible"
    While a feature is locked its tabs, buttons and admin sections are hidden, and its
    API returns `403` with `{"code": "feature_locked"}`. Nothing is deleted. Unlocking
    it again brings back everything, including templates, promoters and the ledger.

!!! note "The ledger is written even while Contributions is locked"
    Promo sends and host/helper awards always create ledger entries. When an org
    unlocks Contributions later, its earlier history is already there.

---

## Promoters

A **promoter** can use the Promotion dashboard and earn points for it, and nothing
else: promoters cannot edit events, tournaments or organization settings. For a private
member list (`members_private`) they count as plain members.

Owners and admins add and remove promoters in the **Promoters** section of the org's
admin team panel. The section only appears while Promotion is unlocked. Adding someone
creates their org membership if they lack one and writes an `add_promoter` log entry.

Staff, admins and the owner can also use the dashboard; promoter is simply the lowest
role that gets in. If Promotion is locked, promoter membership stays stored but grants
nothing.

---

## Promotion

The **Promotion** tab on the organization page lists upcoming events
(`upcoming` or `signups_open`). Upcoming and signups-open event pages also get a
**Promote** button for anyone with promoter access.

### Message templates

Org staff and above create and edit templates; promoters can only use them. When an
org first unlocks Promotion it gets one starter template, "First invite". A template
body is at most 2000 characters.

Templates use these placeholders, and only these:

| Placeholder | Fills with |
|---|---|
| `{player}` | The recipient's server nickname, then Discord display name, then Discord username, then site nickname |
| `{promoter}` | The sender's name |
| `{event}` | Event name |
| `{event_time}` | `<t:UNIX:F>`, full start date and time |
| `{event_time_relative}` | `<t:UNIX:R>`, time until start ("in 3 days") |
| `{event_date}` | `<t:UNIX:D>`, start date only |
| `{signups_open}` | `<t:UNIX:R>` for when sign-ups open, empty if not set |
| `{event_link}` | Full URL of the event page |
| `{org}` | Organization name |
| `{discord_link}` | The organization's Discord invite link |

Anything else in braces (`{foo}`, `{player:>10}`, `{event.organization}`, a stray `{`)
is left as literal text, and the editor shows a warning for it. Rendering never fails
on odd input.

### Discord timestamps

`{event_time}`, `{event_time_relative}`, `{event_date}` and `{signups_open}` expand to
Discord timestamp codes such as `<t:1763236800:F>`, where the number is the start time
in Unix seconds. Discord shows each reader the time in their own timezone, so one
message works for players everywhere.

The message box holds the raw text with the codes in it; that is what **Copy** puts on
the clipboard. Below it, *How it will look in Discord* renders the codes in your own
timezone and language so you can check the result.

### Sending a message

1. Pick an event, then a template.
2. Pick a player from the candidate list. The list is the Discord-linked players of the
   org's most recent past tournaments (3 by default, adjustable from 1 to 10). It never
   includes upcoming tournaments, tournaments of cancelled events or the promoted
   event's own tournament. By default it hides people already signed up and people
   already messaged for this event; there is also a name search. You never appear in
   your own list.
3. Edit the filled-in message if you want. Edits apply to this message only. The
   counter warns past 2000 characters (Discord's limit without Nitro); the server
   refuses anything over 4000.
4. **Copy** the text and send it to the player in Discord yourself. DraftForge never
   sends the DM.
5. Press **Mark sent** to record it.

Each candidate row shows who already messaged that player for this event and when. The
sender can undo their own send while they still have promoter access; staff and above
can undo anyone's. Undo deletes the send and its points.

!!! warning "One point per player per event"
    A player earns the sender a point only once per event. If someone else already has
    an earning send to that player for that event, a new send is recorded without
    points, and the dashboard says so before you mark it sent. If the earning send is
    undone, the earliest remaining send for that player and event earns instead.

Site admins who reach the dashboard only through their site role can mark sends, but
earn no points and are not added as org members.

---

## Contributions

The **Contributions** tab shows the org-wide points total and a leaderboard, for all
time or a single month. Months are calendar months in the organization's timezone (UTC
if the timezone is missing or invalid), so a game at 11pm on Oct 31 Eastern counts
toward October.

Points come from:

| Kind | Earned by | Default points |
|---|---|---|
| `promo_message` | Marking a promo message sent (once per player per event) | 1 |
| `event_host` | Being the event's host when it closes | 10 |
| `event_helper` | Being a helper when the event closes | 5 |
| `manual` | A manual award from an org admin | typed by the admin |

Clicking a member opens their breakdown: each entry with its kind, event, points and
date, plus a per-month total. The breakdown never shows promo recipients or message
text. Manual award reasons are visible to org staff and above only.

### Point values and rescoring

Owners and admins open **Manage contributions** in the tab. Under **Point values**,
each kind shows its current value, the default, and a badge when it has been changed;
**Reset to default** goes back to the default.

Saving a new value asks how to apply it:

- **Future only**: new entries use the new value; existing entries keep theirs.
- **Apply to past entries**: every existing entry of that kind in this org is set to
  the new value, optionally only entries since a chosen date (the start of that day in
  the org's timezone).

Manual awards are never rescored. Every value change and rescore is written to the
`OrgLog` with the old value, new value and the number of entries changed.

### Manual awards and the ledger

**Manual award** gives any member points (1 to 1000) with a reason and a date,
optionally linked to an event. The date is read in the org's timezone, so an award
dated the 1st counts in that month. Manual awards can be edited or deleted from the
**Ledger**, which lists every entry with filters for period, kind and member.

### Points survive deletions and merges

- Deleting an event keeps its entries; they keep the event name as a label.
- Merging two accounts (claim approval or Discord merge) moves every entry to the
  surviving account. Duplicate host/helper entries for the same event collapse into one.
- Deleting the organization deletes its ledger. A site admin deleting a user deletes
  that user's entries first.

---

## Host and helpers

On the event page, owners and admins assign one **host** and any number of **helpers**.
This works whatever the Contributions switch says; while Contributions is locked the
card shows the names without points. Anyone can be assigned, and assigning creates
their org membership if it is missing. A person cannot be both host and helper on one
event.

Host and helper points are written when the event closes (below). After that, changing
the host or helpers updates the ledger straight away, so mistakes can be fixed later.
Changing an awarded event's name, start or end time moves its points with it.

---

## Completing an event

Owners and admins see **Complete** on an event in `roll_call` or `in_progress`. It moves
the event to `completed` and awards the host and helper points. Each event awards once:
if the hourly cleanup job closes the same event at the same moment, only one close
counts.

Events nobody closes are closed automatically one day after they end (`ends_at` if set,
otherwise the start time):

| State | Becomes | Host/helper points |
|---|---|---|
| `roll_call`, `in_progress` | `completed` | awarded |
| `upcoming`, `signups_open` | `cancelled` | awarded only if a host or helper was assigned |

A manual **Cancel** from the event page never awards points.

---

## Privacy

- Leaderboard rows and member breakdowns follow the org's member-list rule
  (`can_view_org_members`): anyone who may see the Users tab sees the rows. Everyone
  else, including anonymous visitors, sees only the org-wide total, plus their own row
  if they have points. With **Private members list** on, plain members see only their
  own row.
- Points are never part of the cached organization, member-list or event payloads.
  The event page shows host and helper identity only.
- Feature notes and who unlocked a feature are visible to site admins only.
- The promoter list is served only to org admins, and only while Promotion is unlocked.
