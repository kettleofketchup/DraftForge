# MMR update requests

Members ask their organization or league to change their MMR and attach a screenshot as
proof. Org and league staff review the request, or set an official MMR directly. Each
MMR shows on the member's profile with an **Official** or **Unverified** badge.

Requested in [#750](https://github.com/kettleofketchup/DraftForge/issues/750). Org MMR
itself (one value per game) is described in [Org MMR per game](org-mmr.md).

---

## Org MMR and league MMR

| Kind | What it is | Who sets it |
|------|------------|-------------|
| **Org MMR** | One value per game (Dota 2, Deadlock) for your membership in an organization. Tournaments and events of that org use it to balance teams. | Org staff |
| **League MMR** | One Dota 2 value for your membership in a league. League ratings and match snapshots start from it. | League staff, or staff of the league's organization |

A value is **Official** when a staff member set or approved it. The badge shows who
verified it and when. Values verified before review history existed show Official with
no name. Values written any other way (CSV import, the league recompute) are
**Unverified**.

League MMR is your Dota 2 org MMR plus your best league performance adjustment. When
your org MMR changes (staff edit, approved request, CSV import) or a league stats
update changes your adjustment, every Unverified league MMR you hold is recomputed. An
Official league MMR stays pinned and is never recomputed. Without an org MMR your
league MMR is left as it is.

---

## For members

### Requesting a change

1. Open your profile and go to the **Orgs & MMR** tab. It lists every organization and
   league you belong to, with your current values and badges.
2. Click **Request update** on the row you want to change.
3. Enter the new value (1 to 20000), attach a screenshot (PNG, JPEG or WebP, at most
   8 MB) and optionally add a note (at most 500 characters).
4. Submit. The row now shows **Pending** with the requested value and date, and a
   **View screenshot** link that opens the screenshot you sent. **Request update** is
   hidden on that row until the request is decided or cancelled.

You can only request for your own memberships, and you can have one pending request per
target (one per org game, one per league). You can create at most 10 requests per hour.

To withdraw a request, click **Cancel request** on the pending line. Its screenshot is
deleted.

### Statuses

| Status | Meaning |
|--------|---------|
| Pending | Waiting for staff |
| Approved | The value is now Official. The profile shows "Last decision: Approved 4800", or "approved as 4750, you asked 4800" when staff adjusted the value |
| Rejected | Not applied. The reason staff gave is shown on your profile |
| Superseded | Staff set an official value for that target before reviewing your request |
| Cancelled | You withdrew it, or your membership was removed |

The profile shows your pending request and the last approved, rejected or superseded
decision for each target. Cancelled requests are not shown there.

### Who sees what

| Viewer | Sees |
|--------|------|
| You | Every org and league MMR, pending requests, last decisions, the screenshot of your pending request |
| Org staff, and staff of that org's leagues | Your values for that org and its leagues, plus pending requests and screenshots for targets they can review |
| Other members of the org | Your org values while the org's member list is public |
| Other members of a league | Your league value, even when the org's member list is private |
| Site admins | Everything except screenshots of requests they cannot review |
| Anyone else, including logged-out visitors | Nothing |

Screenshots are never public. Only you and the staff who can review the request can
open them.

---

## For staff

### The queue

Org staff (owner, admins, staff) get an **MMR requests** tab on the organization page,
next to Claims. League staff get the same tab on the league page. The tab badge shows the
pending count.

| Scope | Lists |
|-------|-------|
| Organization | Org requests for the org, and league requests for every league the org owns |
| League | League requests for that league only |

Filter by Pending (default), Approved, Rejected, Superseded, Cancelled or All. Each card
shows the member, the target, current and requested values, the screenshot (click to
enlarge) and the note. A change of 20% or more is highlighted.

### Approve, adjust, reject

- **Approve** writes the value as Official. Change the number in the dialog to approve a
  different value; the member's profile then says "approved as X, you asked Y". A large
  change asks you to confirm.
- **Reject** needs a reason (1 to 500 characters). The member sees it.
- A request that someone else already handled returns "already reviewed".

Every approval writes an `OrgLog` `set_mmr` entry with `source: "mmr_request"` and the
request id. League approvals also write a `LeagueLog` `set_mmr` entry.

### Set official MMR

Set a member's value directly, without a request:

- From the queue header: **Set official MMR**, then pick the member.
- From the organization or league Users tab: edit the member, then **Set official MMR…**.

Pick the target (an org game or a league), enter the value, and optionally attach a
screenshot and a note. The value is Official immediately. An approved request row with
source "staff" is kept for the audit trail, and any pending member request for that
target becomes Superseded.

Saving an org MMR in the normal member edit form, or approving an event signup with an
MMR, also marks it Official when you could review that member's requests. Otherwise
(your own MMR, or a staff member's MMR when you are not an admin) the value is saved as
Unverified and any pending request stays in the queue.

### Who can review

- You need staff access to the target: org staff for org MMR; league staff, or staff of
  the league's organization, for league MMR.
- Nobody verifies their own MMR. Site superusers are the exception.
- If the member is staff of that org or league, the reviewer must be an admin there. The
  owner counts as an admin.

The card shows "Needs another admin to review" when you cannot review a request.

---

## For operators

### Storage

Screenshots are stored through Django's default storage under `MEDIA_ROOT`
(`backend/media` unless the `MEDIA_ROOT` env var says otherwise), at
`mmr_requests/YYYY/MM/<random>.<ext>`. Files are written 0640, directories 0750.

Uploads are re-encoded before they are stored: Pillow decodes and verifies the image,
fixes its orientation, scales it down to 3840 px on the long edge and writes a new
PNG, JPEG or WebP without EXIF or other metadata. Images over 25 megapixels or 8192 px
on an edge are refused.

| Stack | Location |
|-------|----------|
| Dev / test compose | `backend/media` inside the mounted source tree |
| Prod / release compose | `./backend/media` bind-mounted to `/app/backend/media` |
| Helm | `MEDIA_ROOT=/data/media`, on the same volume as the SQLite database |

### Deploying this release

Pillow is a new Python dependency, and `migrate` runs on the host venv. After
`git pull` on the release host, install it before deploying:

```bash
just update::python      # or: .venv/bin/poetry sync
just dev::release
```

`just dev::release` creates `backend/media` and prints a warning unless the directory is
owned by uid 1000, the user the backend container runs as. Fix it with:

```bash
sudo chown 1000:1000 backend/media
```

Under rootless podman the container user maps to host uid 100999 instead. Grant it access
with `setfacl -R -m u:100999:rwX -m d:u:100999:rwX backend/media`.

### Disk budget

A stored screenshot is at most 8 MB and usually 0.5 to 3 MB, so about 500 fit in a
gigabyte. Uploads are refused with "storage full" (HTTP 507) when the volume holding
`MEDIA_ROOT` has less than 512 MB free. Cancelling a request or deleting its membership
deletes its file; approved and rejected requests keep theirs for the audit trail.

The free-space floor protects compose hosts and the prod volume. It does not apply to
helm previews: there `/data` is an `emptyDir` with `sizeLimit: 1Gi`, the free-space
check reads the node's disk, and the kubelet evicts the pod before the floor is reached.
Previews are ephemeral, so this is accepted.

### Body size limits

The nginx stacks cap the upload endpoints (`/api/mmr-requests/` and
`/api/{organizations,leagues}/<id>/mmr-requests/staff-set/`) at 9 MB. Django also
refuses a body over 9 MB before parsing it and stops reading a file part past 8 MB.
Helm previews have no proxy body cap (see `helm/README.md`); only the Django guard
applies there.

### Backups

Back up `backend/media` together with `backend/prod.db.sqlite3`. A database restored
without its media shows "Screenshot unavailable" on the affected requests; nothing else
breaks.

### Privacy model

- nginx serves no `/media` location, and the storage refuses to build public URLs.
- Screenshots are only streamed by `GET /api/mmr-requests/<id>/screenshot/`, which
  returns 404 to anyone other than the requesting member and the staff who can review
  that request. Responses are `private, no-store`, `nosniff` and sandboxed.
- API payloads never contain the file path, only `has_screenshot` and that URL.

---

## API

| Method | Path | Who |
|--------|------|-----|
| GET | `/api/users/<pk>/mmrs/` | Anyone (filtered as in [Who sees what](#who-sees-what)) |
| POST | `/api/mmr-requests/` (multipart) | The member |
| GET | `/api/mmr-requests/mine/` | The member |
| POST | `/api/mmr-requests/<id>/cancel/` | The member |
| GET | `/api/mmr-requests/<id>/screenshot/` | The member, reviewing staff |
| POST | `/api/mmr-requests/<id>/approve/` (`{"mmr"?}`) | Reviewing staff |
| POST | `/api/mmr-requests/<id>/reject/` (`{"reason"}`) | Reviewing staff |
| GET | `/api/organizations/<id>/mmr-requests/?status=&league=` | Org staff |
| GET | `/api/organizations/<id>/mmr-requests/pending-count/` | Org staff |
| POST | `/api/organizations/<id>/mmr-requests/staff-set/` (multipart) | Org staff |
| GET | `/api/leagues/<id>/mmr-requests/?status=` | League staff |
| GET | `/api/leagues/<id>/mmr-requests/pending-count/` | League staff |
| POST | `/api/leagues/<id>/mmr-requests/staff-set/` (multipart) | League staff |

Errors: 409 `pending_exists` (with the existing request id) or `not_pending`, 403
`self_review`, 400 `{"screenshot": [code]}` (`too_large`, `unsupported_type`,
`invalid_image`), 413 `too_large`, 429 throttled, 503 `busy`, 507 `storage_full`.
