# Discord Permission Badges

Permission badges show whether the bot has the effective permissions needed for a particular action at its actual destination. They appear in event, series and organization-default Discord settings, and in an event's **Discord State** and task rows. Open a badge for missing permissions, current granted permissions, blockers, destination and observation time.

!!! note "Read-only diagnostics"
    Checking permissions and using **Recheck** only read Discord information. They do not send messages, create scheduled events or fire tasks. A verified check **does not guarantee delivery**: Discord outages, resource changes and execution-time errors can still prevent an action. Diagnostics do not block saving configuration. Saving and firing tasks retain their existing behavior and may send messages.

## Badge meanings

Only a current `verified` result is green. History labels such as **Posted** describe past activity, not current permissions; **Bot connected** describes membership, not access to every channel.

| Status | Meaning |
|---|---|
| `verified` | All action-specific effective permission requirements are satisfied and the required resource evidence is available. |
| `missing_permissions` | One or more required permissions are missing, or a known permission blocker applies. Details list the missing flags and alternatives. |
| `unconfigured` | No server, no destination, or no saved reference exists yet. This is not verification. |
| `unknown` | Discord could not supply complete, current evidence. It is not proof that permissions are absent. |
| `unsupported` | The current sender, channel type or Discord endpoint cannot support verification of this operation. Granting more permissions does not fix it. |
| `not_applicable` | The action is recipient-dependent, such as a direct message, rather than a guild/channel permission check. |

**Checking**, **Not checked**, disabled options and **Check expired** are neutral, never green. Expired details may retain historical grants, explicitly labeled as historical rather than current.

## Which destination is checked?

- **Configured**: the channel selected for this action in the current form or saved settings.
- **Fallback**: the channel the sender uses when an own channel is blank. Attendance reminders, profile reminders and new-event notices use the announcement channel even when announcements are disabled. Signup fallback is eligible only when announcements are enabled and their channel is configured.
- **Posted**: the channel or thread of an existing stored message. Changing the channel setting does not move the old post; its edit badge still checks the old destination and verifies the bot authored the message.
- **Prospective**: requirements for an operation whose actual resource does not exist yet, such as a start mention before the signup post. It cannot be verified until that reference exists.
- **Guild**: scheduled-event operations check server-level permissions, not the announcement channel.
- **Recipient**: DM delivery depends on the recipient and cannot be established by server permission bits.

Signup primary and announcement fallback have separate badges. A working fallback does not make an unsupported or inaccessible primary green. For example, an attendance reminder configured for **attendance-updates** is checked there, even when the announcement badge for **event-updates** is green. Clearing the attendance channel previews **event-updates (fallback)** without saving the form.

Unsaved form edits are checked against the draft settings. Creation forms, series and organization defaults use organization previews; an existing event uses event-scoped previews. Discord State checks saved settings and historical references even when no Discord history exists yet.

## Minimum permissions by action

These are effective permissions after the bot's roles, channel overwrites and implicit restrictions have been applied. Role order does not override channel denies. Thread actions use their parent's overwrites. Server ownership and an existing server-wide bypass are recognized, but are not a recommended remedy.

| Action | Destination and minimum requirement |
|---|---|
| `signup_create` | Forum parent: **View Channel**, **Send Messages**, **Embed Links**. Does not require Create Public Threads. The current nested forum sender does not support text/announcement channels. A forum requiring an unsupplied tag remains blocked. |
| `signup_fallback` | Text/announcement channel: **View Channel**, **Send Messages**, **Embed Links**. Separate from the primary signup post. |
| `announcement` | Text/announcement channel: **View Channel**, **Send Messages**, **Embed Links**. |
| `attendance_reminder` | Own or fallback text/announcement channel: **View Channel**, **Send Messages**, **Embed Links**. |
| `profile_reminder` | Own or fallback text/announcement channel: **View Channel**, **Send Messages**, **Embed Links**. |
| `new_event_notice` | Series own or fallback text/announcement channel: **View Channel**, **Send Messages**, **Embed Links**. |
| `start_mention` | Posted signup destination: **View Channel**, **Read Message History**, and **Send Messages** (or **Send Messages in Threads** for a thread). The reply is plain text, so Embed Links is not required. Pending until the signup reference exists. |
| `signup_edit`, `announcement_edit` | Posted text/announcement channel or thread: **View Channel**, a verified existing message authored by the bot, and an accessible, active, unlocked destination. Does not require Manage Messages for the bot's own edit. |
| `scheduled_event_create` | Server: **Create Events**. Manage Events alone does not satisfy creation. |
| `scheduled_event_update`, `scheduled_event_delete` | Verified saved scheduled event: **Create Events OR Manage Events** for the bot's own event; **Manage Events** for another creator. If creator identity is unknown, Create Events alone cannot produce green. No saved reference means pending. |
| `mark_interested` | Unsupported: the current operation uses an undocumented endpoint. No permission grant can make it verified. |
| `signup_reminder_dm`, `tournament_dm` | Recipient dependent: never green based on server permissions. Includes draft and hero-draft link DMs. |
| `template_post` | Reusable checker profile for text/announcement embeds: **View Channel**, **Send Messages**, **Embed Links**. RSVP reactions additionally need **Read Message History** and **Add Reactions**. |
| `admin_channel_post` | Internal checker profile: text/announcement **View Channel**, **Send Messages**, **Embed Links**. Not exposed by public previews. |

### Role mentions

For signup and announcement payloads that ping configured roles, a role already marked mentionable needs no extra mention permission. For a non-mentionable role, either make that role mentionable (the narrower remedy) or allow **Mention Everyone**. A deleted configured role must be replaced. Fallback signup messages do not inherit role-ping requirements they do not use.

### Threads and timeouts

Archived or locked threads stay unverified even when permission bits are present. Private-thread access requires confirmed bot membership; missing or unreadable membership evidence is not treated as access. No automatic unarchive or unlock is assumed.

An active communication timeout restricts the effective set to already-granted **View Channel** and **Read Message History**, including for server-event checks. Details distinguish current grants from pre-timeout grants; pre-timeout grants do not satisfy an action now.

## Freshness and Recheck

Successful snapshots are cached for at most **60 seconds**; errors for at most **10 seconds**. Each result uses its oldest dependency's observation time and earliest expiry. Checks refresh while viewed and on window focus; green expires when the evidence expires. External role or overwrite changes may therefore take time to appear.

**Recheck** requests fresh observations for the batch. Refresh is limited to **5 requests per minute per viewer**, with at most one upstream refresh per server per 10 seconds. Concurrent refreshes can share an observation without extending its age; throttled results disclose that state. Discord rate limits expose a retry delay rather than sleeping or testing by sending. A failed refresh replaces an earlier success with an unknown result, not stale green.

Checks are bounded to 20 actions and 25 role IDs per action, with a 15-second overall read budget and at most 5 seconds per read. Missing credentials, unavailable resources or budget exhaustion cannot verify an action.

## Details and troubleshooting codes

Details expose required permissions (including alternatives), missing flags, all known effective grants, destination, blockers and observation times. Unknown grants are not represented as an empty permission set. Raw permission bitfields and Discord IDs use decimal strings to avoid numeric precision loss.

| Reason | What to do |
|---|---|
| `no_server_configured` | Choose a Discord server. |
| `no_channel_configured` | Choose a destination, or configure an eligible fallback. |
| `bot_unavailable` | Check the bot's server membership and connection. |
| `credential_unavailable` | Ask a site operator to check bot credentials. |
| `forbidden_read` | Discord denied a required read; check the bot's access to the resource. |
| `resource_unavailable` | Check that the destination or saved resource still exists in this server. |
| `rate_limited` | Wait for the indicated retry delay before rechecking. |
| `network_error` | Discord could not be reached or the read budget expired; recheck when available. |
| `malformed_snapshot` | Discord information was incomplete or invalid; verification must wait for complete evidence. |
| `pending_signup_post` | Wait for the signup post to exist before checking its actual reply destination. |
| `unsupported_channel_type` | Choose a channel type supported by this action. |
| `unsupported_endpoint` | The operation has no supported endpoint in the current integration. |
| `unsupported_signup_transport` | The current primary signup sender supports forum posts, not text/announcement posts. |

| Blocker | Meaning |
|---|---|
| `missing_reference` | A saved message/event reference is needed. |
| `forum_requires_tag` | The forum requires a tag the current sender does not supply. |
| `communication_timeout` | The bot is timed out; pre-timeout grants do not apply now. |
| `role_not_mentionable` | Make the role mentionable or allow the required mention permission. |
| `role_missing` | Replace a configured role that no longer exists. |
| `thread_archived` | The posted thread is archived. |
| `thread_locked` | The posted thread is locked. |
| `private_thread_access` | Bot membership/access could not be confirmed. |

## Staff access and API

Organization previews require organization staff access. Saved event checks and event previews require event staff access, which can include staff of the event's league without organization-wide access. Permissions are authorized before any snapshot/cache lookup. A supplied channel from another server exposes no channel metadata. Checks do not broaden access to Discord history.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/discord/organizations/{id}/permission-checks/` | Organization-scoped draft checks for event creation, series and defaults. |
| GET | `/api/events/{id}/permission-checks/` | Server-derived saved event checks; `?refresh=true` requests a refresh. |
| POST | `/api/events/{id}/permission-checks/` | Draft checks for an existing event; only server-held references establish ownership. |

POST requests contain `checks` and optional `refresh`; each check has a unique key, action, optional channel ID and role IDs, and optional RSVP flag. Clients cannot assert a guild, message ownership or scheduled-event ownership. Diagnostic errors never prevent a configuration save.
