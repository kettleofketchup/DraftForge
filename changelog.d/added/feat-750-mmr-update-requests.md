- MMR update requests (#750): on the new **Orgs & MMR** profile tab, members see their
  org MMR per game and their league MMRs, and can request a change with a required
  screenshot (PNG, JPEG or WebP, up to 8 MB) and an optional note. They can cancel a
  pending request and see the last decision, including a rejection reason.
- Org and league staff get an **MMR requests** tab with a pending-count badge. They can
  approve (optionally at an adjusted value) or reject with a reason. Nobody verifies
  their own MMR, and a staff member's request needs an admin reviewer.
- Staff can set a member's official org or league MMR directly, with an optional
  screenshot, from the queue or the member edit dialog. Every change is kept as an
  audited request row and an `OrgLog` / `LeagueLog` `set_mmr` entry.
- Profiles show org and league MMRs with an Official (verifier and date) or Unverified
  badge, within the existing member-list visibility rules. The league MMR recompute
  no longer overwrites an Official league MMR.
- API: `GET /api/users/<pk>/mmrs/`, `/api/mmr-requests/` (create, mine, cancel,
  screenshot, approve, reject) and `/api/{organizations,leagues}/<id>/mmr-requests/`
  (list, pending-count, staff-set).
- New docs page: MMR update requests.
