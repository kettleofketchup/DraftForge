# Steam Friend ID verification

A member's Steam Friend ID (`CustomUser.steam_account_id`, the 32-bit account ID shown on
the Dota 2 profile and the Steam friends page) links them to their Dota history. Members
enter it themselves, so DraftForge checks that a Steam account with that ID exists, and
lets staff mark the ID **verified** once they have checked that it belongs to the member.

This page is for organization, league and site staff.

---

## Where members set the ID

| Place | Behaviour |
|-------|-----------|
| Profile edit (`POST /api/profile_update`) | Sets or changes the ID. A change resets verification |
| Web event signup | Fills the ID when it is empty; the same ID again is accepted; a different ID is refused |
| Discord signup modals (Dota 2, Deadlock, default) | Same rules as the web signup |
| Org Dota profile (`/api/organizations/<org>/my-dota-profile/update/`) | Same rules as the web signup |

A self-set ID is always **Unverified**, whatever the Steam check says.

Staff can also write a member's ID (organization Users tab, player modal edit, the user
edit dialog, CSV import, claim approval). See [Who can verify](#who-can-verify) for when
such a write counts as verified.

---

## The Steam existence check

Before a self-set ID is saved, DraftForge asks the Steam Web API
(`ISteamUser/GetPlayerSummaries`) whether an account with that ID exists. Private
profiles still count as existing.

- **No such account**: the ID is refused with
  "No Steam account has Friend ID N. Check the number on your Dota 2 profile or Steam
  friends page."
- **Steam is down, slow (over 2 seconds), or `STEAM_API_KEY` is missing**: the check
  *fails open*. The ID is saved and shown as "Not checked against Steam".
- **Results are cached**: a found account for 1 hour, a missing one for 15 minutes.
  Failures are not cached. Re-submitting an ID the member already has runs no check.
- **Rate limit**: each member gets 10 uncached checks per hour; past that they get
  "Too many Friend ID checks. Try again in an hour." Across all users, past 60 uncached
  checks a minute, further checks fail open so league and match sync keep their Steam
  quota.

Untrusted staff writes (see below) go through the same check. CSV rows are not checked.

The check is controlled by the `STEAM_ACCOUNT_LOOKUP_ENABLED` setting (on by default,
off in the test stack).

---

## Badge states

Staff see a badge next to the Friend ID in the MMR approval dialog, the player modal and
the tournament Players tab.

| Badge | Tooltip | Meaning |
|-------|---------|---------|
| **Unverified** | "Self-reported. Found on Steam." | Steam confirmed an account with this ID exists. Nobody has checked it is this member's |
| **Unverified** | "Self-reported. Not checked against Steam." | The Steam check failed open, or the ID predates this feature |
| **Verified** | "Verified by &lt;org&gt; on &lt;date&gt;" or "Verified by site staff on &lt;date&gt;" | Staff vouched for it |

Members see "Unverified: an organizer will confirm this ID." on their own profile and
nothing else. Other members never see the badge.

In the Players tab the badge has no Verify button; click it to open the player modal,
where Verify appears if you are allowed to use it.

---

## What to check before verifying

"Found on Steam" only means the number is a real account. A member can enter someone
else's real ID. Before clicking **Verify**:

1. Open the **Steam** link next to the badge and the **Dotabuff** link.
2. Compare the Steam persona name and avatar with the member's Discord name and avatar.
3. Check the account has plausible Dota history, and that its rank roughly matches the
   MMR or medal the member declared.
4. If in doubt, ask the member for a screenshot of their Dota 2 profile showing the
   Friend ID.

---

## Who can verify

| Who | Can verify |
|-----|------------|
| Site staff and superusers | Any member except themselves. Recorded as "site staff" |
| Org staff of an event's organization, league staff of an event's league | Members who **signed up to that event themselves** (web or Discord). Recorded as the event's organization |
| Anyone else, including plain org staff | Nobody |

Nobody can verify their own ID, superusers included.

Event staff need a signup the member made themselves because staff can add anyone to an
organization or a tournament without their consent. Signing up is the member's own
action, so it is what gives that event's staff the right to vouch for them. Signups that
staff added on a member's behalf do not count, and cancelled or rejected signups do not
count.

!!! warning "Signups made before this feature do not count"
    DraftForge did not record who made a signup before this release. Every existing
    signup is treated as staff-made, so event and league staff can verify those members
    only once those members sign up to one of their events themselves after the upgrade. Site staff can
    always verify.

### Where

- **MMR approval dialog** (event signups): Verify next to the Friend ID line.
- **Player modal**: Verify next to "Friend ID".

On a verified ID, "Mark unverified" sits in the menu next to the badge.

### Staff writes

When staff enter or change a member's ID through an admin edit (organization Users tab,
player modal, user edit dialog, user creation, claim approval) and they would be allowed
to verify that member, the ID is saved **verified by them** and skips the Steam check.
Otherwise it is saved unverified and goes through the Steam check like a self-set ID.
CSV import stubs are verified only when the importer is site staff.

---

## "Verified by &lt;org&gt;"

Each verification records the organization that vouched (or site staff). Any organizer
can see it in the badge tooltip, so an admin of another organization can decide how much
to trust a verification made by an org they do not know. The staff member who verified is
recorded in the Django admin and the logs, not shown in the app.

---

## Changing or clearing the ID

Any change to the ID, including clearing it, removes the verification and the Steam check
result, on every path (self-service, staff edit, Django admin, management commands).
Saving the same ID again keeps both.

Verify and Mark unverified send the ID that was on screen. If the ID changed in the
meantime, the request fails with "The Friend ID changed; check the new one before
verifying." and the new ID is shown.

---

## Disputes

If a member's real ID is already held by another account, they get the duplicate error,
which now ends with "If this is your account, contact an organizer." An organizer (or
site staff) can then clear or correct the wrong account's ID from the organization Users
tab or the user edit dialog, and the real owner can enter it.

---

## Existing IDs

The upgrade does not backfill anything. Every Friend ID saved before this release starts
**Unverified** and "Not checked against Steam".

---

## Error codes

| Code | Status | Where | Meaning |
|------|--------|-------|---------|
| `steam_account_not_found` | 400 | Self-service writes, untrusted staff writes | No Steam account has this ID |
| `steam_lookup_rate_limited` | 429 | Profile edit, staff profile edits | Too many uncached checks this hour |
| `invalid_friend_id` | 400 | All writes | Not a whole number in 1 to 4294967295 |
| `friend_id_already_set` | 400 | Signups | A different ID is already set; ask an admin |
| `duplicate_friend_id` | 409 | Profile edit, signups | Another account holds this ID |
| `no_steam_account_id` | 400 | Verify endpoint | The member has no Friend ID |
| `id_changed` | 409 | Verify endpoint | The ID changed since it was loaded |

Signups report these as a refusal message rather than a status code. The endpoint is
documented under [Users](../api/endpoints.md#steam-friend-id-verification).
