# Discord DM Ledger

Every Discord DM the platform sends gets one row in `discordbot.DiscordDM`. The row is
written before the send and updated after it, so a DM that went out without a ledger
row is a bug. App code never deletes ledger rows.

The ledger stores no message bodies, embeds, URLs or passwords. It stores who the DM
was for, why it was sent, what happened, and (for DMs with buttons) how often the
recipient clicked.

## The model

| Field | Meaning |
|---|---|
| `kind` | Why the DM was sent (table below) |
| `idempotency_key` | Unique. A second send with the same key is suppressed |
| `status` | See [Statuses](#statuses) |
| `attempts` | Claims granted for this key (reclaims add one) |
| `recipient`, `discord_user_id` | The user and their Discord id at send time |
| `organization` | The org the DM belongs to, when there is one |
| `subject_type`, `subject_id` | The domain object: `event`, `tournament` or `game_lobby` |
| `tournament_log` | The `DiscordTournamentLog` for tournament and lobby DMs |
| `context` | A small per-kind allow-list (below); never content |
| `has_components` | The DM had buttons or selects |
| `discord_channel_id`, `discord_message_id` | Where the DM landed. Only the admin shows these |
| `http_status`, `error_code`, `error` | The Discord response on failure (`error` is cut to 300 characters) |
| `retryable` | A `failed` row that may be claimed again |
| `created_at`, `claimed_at`, `send_started_at`, `sent_at`, `finished_at` | Timeline |
| `first_clicked_at`, `last_clicked_at`, `click_count` | Component clicks on the DM |
| `backfilled_from` | `discordeventdm` or `discordmessagelog` for rows copied from the old tables |

Every foreign key is `SET_NULL`, so deleting a user, org, event or tournament keeps the
row. `DiscordDM.delete()` and `DiscordDM.objects.delete()` raise
`LedgerImmutableError`. The `DiscordDM` Django admin is read-only and has a
**stuck sending (>15 min)** filter.

### Kinds and keys

| Kind | Sent by | Idempotency key | Context |
|---|---|---|---|
| `signup_reminder` | `events/tasks.py send_subscriber_notifications` | `signup_reminder:event:{event_id}:user:{user_pk}` | `discord_event_id`, `repeater_id` |
| `tournament_draft_link` | `events/tournament_tasks.py` | `tournament_draft_link:run:{task_id}:discord:{discord_id}` | `draft_id`, `activity` |
| `tournament_herodraft_link` | `events/tournament_tasks.py` | `tournament_herodraft_link:run:{task_id}:discord:{discord_id}` | `draft_id`, `game_id`, `activity` |
| `lobby_info` | `lobby/tasks.py send_lobby_info` | `lobby_info:lobby:{lobby_id}:run:{task_id}:discord:{discord_id}` | `side` |
| `signup_confirmation` | the gateway bot, after a signup button or modal | `signup_confirmation:interaction:{interaction_id}` | `result`, `interaction_id` |
| `test_notification` | the TEST-only `send_test_notification` view | `test_notification:event:{event_pk}:discord:{discord_id}:req:{uuid}` | none |

Keys are built by one helper per kind in `discordbot/dm_keys.py`, and `context` is
validated per kind in `discordbot/dm_context.py`; unknown keys are refused. Tournament
and lobby keys include the Celery task id, so a manual re-fire DMs again while a
redelivery of the same task does not.

### Statuses

| Status | Meaning |
|---|---|
| `pending` | Claimed; the send has not finished |
| `sent` | Discord accepted the message |
| `failed` | Not delivered. Claimed again only when `retryable` is true |
| `unknown` | The request may have reached Discord (read timeout, connection reset, 5xx). Never claimed again |
| `skipped_test_mode` | A test stack (`TEST=True`) and the recipient is not `TEST_DISCORD_USER_ID`. With that setting or `DISCORD_BOT_TOKEN` empty, every DM is skipped |
| `skipped_no_discord` | The recipient has no Discord id |
| `skipped_disabled` | The feature that sends this DM was turned off before the send |

## Claim, send, finalize

Both senders talk to the ledger over internal HTTP (`api/internal/discord/dms/...`,
internal token and IP allowlist), because Celery workers and the gateway bot have no
database.

1. **Claim** `POST dms/claim/` with the key and a claim token. A new key answers `201`;
   the same token on a `pending` row answers `200` with the same row (a lost response
   retried); anything else answers `409` and nothing is sent. A claim is also granted
   for a `pending` row older than 10 minutes that never started sending, and for a
   `failed` row with `retryable` set.
2. **Mark sending** `POST dms/<id>/sending/` just before the Discord POST. After this
   the row can never be claimed again, so a DM goes out at most once.
3. **Send.** The message POST carries `nonce: "dm<id>"` with `enforce_nonce`, so Discord
   also drops a repeated create for a few minutes.
4. **Finalize** `POST dms/<id>/finalize/` with the outcome. A repeat with the same token
   and status is fine; anything else on a finished row is `409`.

Skips (no Discord id, test mode, disabled) are claimed straight into their terminal
status and never call Discord.

### Fail closed

If the ledger cannot be reached, no DM is sent:

- `send_dm` returns `ledger_unavailable` and logs `dm_ledger_unavailable` at error
  level. Reminder batches with such a recipient finish as failed and their lease
  retries; keys turn the already-sent recipients into duplicates.
- The gateway sends the signup confirmation as an ephemeral reply with the `<@user>`
  mention instead of a DM.

### Error classes

`finalize` computes `retryable` from the error class; callers do not set it.

| Class | When | Retryable |
|---|---|---|
| `pre_send` | Channel open failed, `ConnectTimeout`, a 4xx without a permanent code, a refused `sending` mark | yes |
| `rate_limit_timeout` | The local token bucket timed out, or a 429 kept failing | yes |
| `before_send_failed` | The caller's `on_claimed` hook raised | yes |
| `permanent` | Discord codes 50007 (DMs closed), 10013 (unknown user), 50278, or an empty payload | no |

Read timeouts, other connection errors and 5xx finalize `unknown`. A 401 logs
`discord_auth_failed` and finalizes `failed`; `send_dm` returns `auth_rejected=True`
rather than re-raising. Tournament and lobby sender loops record the failure and
stop sending to further recipients.

### Stuck sending

A process that dies after the `sending` mark and before finalize leaves a `pending`
row with `send_started_at` set. Nothing sweeps it, because resending could DM twice.
The admin **stuck sending (>15 min)** filter lists these rows.

## Choke points and the guard

There are two places that send DMs:

- `discordbot/dm.py send_dm(DMRequest)` for Celery tasks and Django views (REST).
- `discordbot/gateway_dm.py send_interaction_dm(interaction, ...)` inside the gateway
  bot. Its claim token is the interaction id.

`discordbot/dm_ledger.py` is the only code that writes `DiscordDM`.

`discordbot/tests/test_dm_choke_point.py` parses every backend module and fails with
`path:line` when code outside those modules opens a DM channel, calls `create_dm`,
`fetch_user` and similar, calls `.send(...)` on anything but `followup`/`response` in
the gateway, reads DM channel or message ids, or saves, updates or deletes a
`DiscordDM`. A gateway `.send` that is not a DM can carry
`# dm-guard: not-a-dm <reason>`. `discordbot/tests/test_gateway_dm_runtime.py` drives
every gateway view, modal and component callback and fails if a DM is sent outside
`send_interaction_dm`.

To add a DM: add a `DMKind`, a key helper in `dm_keys.py`, a context model in
`dm_context.py` and send through `send_dm` or `send_interaction_dm`. The coverage test
fails until all three exist.

## Click tracking

DM button clicks increment `click_count` and set the click timestamps:

- Gateway: `interaction_router.route_component_interaction` records clicks on DMs
  (no `guild_id`) in the background, so the ACK is never delayed.
- HTTP-interactions mode: `discordbot/views.handle_message_component` records them
  directly.

Link buttons (such as **Review on site**) open a URL without an interaction, so they
cannot be tracked.

## Backfill

Migration `discordbot/0018_backfill_discord_dm_ledger` copied the old tables. Source
rows were not changed.

- Each `DiscordEventDM` became a `signup_reminder` row with key
  `legacy:discordeventdm:{pk}`, linked through `DiscordEventDM.ledger_entry`.
  Test-mode fakes became `skipped_test_mode` without a message id.
- Each `DiscordMessageLog` with `source="tournament_dm"` became a draft or herodraft
  link row with key `legacy:discordmessagelog:{pk}`. Those logs never stored the
  recipient, so the rows have a blank `discord_user_id` and no recipient. A log with no
  tournament log is recorded as `tournament_draft_link` with
  `context={"legacy_kind_unknown": true}`. Embeds were not copied.
- A message id already used by an earlier row is stored as empty on the later one.

New code no longer writes `tournament_dm` message logs.

## Not in the ledger

Promotion DMs (`org/promotion`) are sent by a person from their own Discord account.
The platform renders the text and records a `PromoSend`, but never sends the DM, so
there is no ledger row.

Promotion records answer different questions from `DiscordDM`:

- `DiscordDM` is the bot's delivery outcome for a platform-sent DM.
- `PromoSend` is a promoter's manual record that they sent outreach.
- `ExternalPromotionReceipt` is a contact imported from the bound external contact
  log.
- `PromotionContactOutbox` tracks writing a local `PromoSend` back to that log.
- `ContributionEntry` holds promotion points.

None of these promotion records captures a personal Discord account's messages or
proves that a manual DM was delivered.

## Logging

Ledger and send code logs with `system="discord", subsystem="dm"` and the fields
`dm_kind`, `ledger_id`, `discord_user_id` and `status`.
