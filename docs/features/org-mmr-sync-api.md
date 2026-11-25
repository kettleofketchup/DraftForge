# MMR sync API

An external service (a bot, a spreadsheet script, a rank tracker) can push org MMRs for
members in bulk with an app token. The values land in the same per-game org MMR as manual
edits (see [Org MMR per game](org-mmr.md)).

---

## Turning it on

The API is a locked feature: a site admin enables **MMR sync API** (`mmr_sync`) for the
organization in the [Locked Features](organization-locked-features.md) panel. While it is
off, token creation is refused and existing tokens get `403 feature_locked`. They are kept,
and work again when the feature is switched back on.

## Tokens

Org admins manage tokens in **Org Settings → API access**.

- A token belongs to one org and one user, and acts as that user. Every request re-checks
  that the user is still an org admin, so removing the role disables their tokens.
- The token is shown **once** at creation, as `dfk_<prefix>_<secret>`. Only a SHA-256 hash
  of the secret is stored.
- Revoking is immediate. Org admins can revoke any token in the org.
- Creating and revoking tokens is recorded in the org log (`create_api_token`,
  `revoke_api_token`).

### Token operations

Each token is granted a fixed list of operations when it is created:

| Operation | Allows | Needs the feature |
|-----------|--------|-------------------|
| `mmr:read` | `GET mmr-sync/` | MMR sync API |
| `mmr:write` | `POST mmr-sync/` | MMR sync API |
| `promotion:read` | the adaptor's recipient reads | Promotion |
| `promotion:import` | the adaptor's contact imports | Promotion |
| `contributions:read` | the adaptor's contribution totals | Contributions |

The create form has a switch per operation, defaulting to the MMR pair, and disables
operations whose feature is locked. Through the API, `POST api-tokens/` takes an optional
`"operations": [...]`; without it the token gets `["mmr:read", "mmr:write"]`. An empty or
unknown list is `400`, and asking for an operation whose feature is locked is `403`.
Tokens created before operations existed keep the MMR pair. Token rows list their
operations, and **API access** is shown to org admins when any of these features is
unlocked, so a promotion-only token can be issued while MMR sync API is off. A request
for an operation the token lacks gets `403 operation_not_granted`. The promotion and
contribution operations are described in [promotion contact sync](promotion-contact-sync.md).

## Limits and usage

| Limit | Default | Applies to |
|-------|---------|------------|
| Requests per minute | 60 | each token |
| Requests per day (UTC) | 5,000 | each token |

Site admins can change both per organization (API access section, `PUT api-limits/`, or
the Django admin "Org API limits"). A request over a limit gets `429` with a `Retry-After`
header.

Every token request is counted in `OrgApiTokenUsage` (per token, user and UTC day:
accepted and throttled counts). The API access section shows the last 30 days per user.
The Django admin lists the raw rows.

## Endpoints

Send the token as `Authorization: Bearer dfk_...`. Session cookies are not accepted on
these endpoints.

### `GET /api/organizations/<org_id>/mmr-sync/?game_type=1`

Returns the members you can match against:

```json
{"game_type": 1, "members": [
  {"user_id": 12, "username": "alice", "steam_id": 1001, "discord_id": "1234", "mmr": 4200}
]}
```

### `POST /api/organizations/<org_id>/mmr-sync/`

```json
{
  "game_type": 1,
  "mark_verified": true,
  "entries": [
    {"steam_id": 76561197960266729, "mmr": 4200},
    {"discord_id": "1234567890", "mmr": 3100},
    {"steam_id": 1002, "mmr": null}
  ]
}
```

- `game_type`: `1` Dota 2 (default), `2` Deadlock.
- Each entry needs `steam_id` (32-bit account ID or 64-bit Steam ID) or `discord_id`, plus
  `mmr`. `null` or `0` clears the value. At most 500 entries per request.
- `mark_verified` (default `true`) writes through the Official-MMR writer, recording the
  token owner as verifier and superseding pending requests even when the value is unchanged.
  The existing verification rules apply: no self-verification except for superusers, and
  staff subjects require an admin reviewer. Disallowed entries are reported individually
  in `invalid`; other entries are still processed.
- With `mark_verified: false`, changed values use the unverified bulk writer. This clears
  existing Official verification metadata, including when overwriting an Official value,
  without superseding pending requests. Unchanged values are left untouched.
- Only existing members of the org are updated. The API never adds members.

Response:

```json
{"updated": 1, "unchanged": 1,
 "unmatched": [{"index": 1, "discord_id": "1234567890"}],
 "invalid": [{"index": 2, "error": "MMR 99999 is outside 0..20000"}]}
```

Entries are `invalid` when they are malformed, out of range, list the same member twice,
or carry a `steam_id` and a `discord_id` that belong to different members. The valid
entries in the same request are still applied. Each changed value writes a `set_mmr`
org log entry with `source: "api_sync"`.

### Errors

| Status | Meaning |
|--------|---------|
| 401 | Missing, unknown or revoked token |
| 403 `feature_locked` | MMR sync API is off for the org |
| 403 `operation_not_granted` | The token lacks `mmr:read` (GET) or `mmr:write` (POST) |
| 403 `not_permitted` | The token's user is no longer an org admin |
| 404 | The token belongs to a different org |
| 429 | Per-minute or per-day limit reached; see `Retry-After` |

## Management endpoints (session auth)

| Method | Path | Who |
|--------|------|-----|
| GET, POST | `/api/organizations/<id>/api-tokens/` | org admin (POST needs the feature of every requested operation) |
| DELETE | `/api/organizations/<id>/api-tokens/<token_id>/` | org admin |
| GET | `/api/organizations/<id>/api-tokens/usage/?days=30` | org admin (max 90 days) |
| GET | `/api/organizations/<id>/api-limits/` | org admin |
| PUT | `/api/organizations/<id>/api-limits/` | site admin |

Code: `backend/org/api_tokens/`, `frontend/app/features/api-tokens/`.
