# Discord Activity integration review

Reviewed the original integration (`adc4509` against `eb1c43e`) and the follow-up
notification launch workflow, covering backend security, frontend behavior,
Discord launch semantics, and deployment/testing, then re-ran the combined
regression suites against the fixes.

## Findings and resolutions

| Priority | Confirmed finding | Resolution |
| --- | --- | --- |
| P1 | A credential signed only a reusable Discord instance ID. Deleting/recreating that binding could restore an old token for a different draft. | Credentials now include the immutable database binding ID, instance ID, draft kind/ID and expiry; all must still match. Deleting a binding permanently revokes its existing credentials. |
| P1 | Discord opens the mapped root URL, but the original implementation only initialized under `/activity`. Standard frontend images also lacked a build-time client ID. | Root Activity launches preserve all SDK query parameters when routing to `/activity`. The client reads the public application ID from a no-store backend runtime config endpoint. |
| P1 | Draft notifications had only browser links. A native DM callback cannot select the user's current voice channel. | Both notifications now carry a draft-specific Launch / Join Activity button. Backend verifies linked identity, draft membership, guild and current voice state, then returns a short-lived embedded-app invite for that voice channel. Gateway and signed HTTP interactions both defer before preparing it. |
| P1 | Reused hero portraits and avatars used absolute CDN URLs that Discord's proxy policy blocks. | Activity-only SDK image URL mappings cover Steam hero images, Discord avatars and avatar fallbacks. Website networking remains unchanged. |
| P2 | An already-open Activity socket survived credential expiry, account deactivation, feature disablement and binding deletion. | Open sockets enforce signed expiry and periodically revalidate identity/binding/enablement, preserving existing consumer cleanup. Origin validation is also covered by a real database-backed socket test. |
| P2 | Malformed team-action bodies and oversized IDs could reach ORM lookup before view serializer validation. | Draft-scoped authentication validates mapping-shaped bodies and positive database-range IDs before lookup; wrong kind/draft still fails closed. |
| P2 | A delayed cookie-based login response could overwrite the verified Discord captain identity. SDK retries could also accumulate listeners or reuse stale session data. | The shared user store protects active Activity identity, SDK retries reuse one iframe SDK, and real route unmounts clear cached credentials with StrictMode-safe handling. |
| P2 | Embedded team draft staff controls exposed actions without scoped credentials. | Undo and read-only balance queries receive explicit draft scope. Website-only draft initialization/rebuild/settings are hidden in embedded mode; existing staff checks still govern supported mutations. |
| P2 | A stale notification could reassign a channel and join an existing Activity still pinned to another match. | A launch never moves a running instance. It only replaces a channel's draft within the same tournament; a channel showing another tournament's unfinished draft is refused with `channel_busy`. |
| P1 | The Activity socket offered a credential subprotocol but the server echoed none, so browsers (including Discord's client) failed every handshake. | The server echoes the `draftactivity` marker on accept. Rejected credentials are accepted then closed with 4401 rather than failing the handshake. |
| P2 | A rejected credential was retried unchanged until the reconnect limit. | On 4401 the client repeats the Discord handshake once, shared across sockets, and reconnects with the new credential. |
| P2 | Deferred HTTP launches expired after 120 seconds, leaving "thinking…" unresolved when the worker was busy or restarting. | The task now lives 14 minutes, inside the 15-minute interaction token lifetime. |
| P3 | Launch preparation read voice state twice, bypassed the bot-wide rate limiter and read the user through the query cache. | One voice-state read; bot calls go through the shared token bucket; user lookups bypass cacheops. |
| P2 | Documented manual setup could bind a production/default database instead of the development database. The declared Discord dependency also permitted versions lacking native launch support. | Setup loads the same dev environment as migration/stack commands. The dependency now directly requires discord.py >=2.6.4; its locked implementation version is unchanged. |

The review also checked that the gateway and Celery processes remain free of
Activity ORM access, notification payloads retain the browser fallback, short
invite preparation uses bounded network waits, interaction credentials are
redacted from Celery argument representations, and no tests send real Discord
messages.

## Validation

- 91 backend tests cover credentials, revocation, live socket expiry/cleanup,
  origin validation, runtime config, launch/join invitations, channel/membership
  validation, notification delivery payloads and existing Discord regressions.
- 65 frontend tests cover root bootstrap, SDK lifecycle/runtime config,
  credential scope, delayed identity responses, embedded team controls and both
  existing draft clock/heartbeat implementations.
- The first full CI run executed 2,933 backend tests and exposed one additional
  cache-enabled deactivation failure. Activity authorization now bypasses the
  user query cache, and the regression explicitly warms a cached active-user
  lookup before bulk deactivation. The targeted backend suite also runs against
  a dedicated Redis instance with caching enabled to cover that condition.
- React Router/TypeScript checking, relevant ESLint and Ruff checks, changed-file
  formatting, migration drift, dependency lock consistency, changelog fragments
  and whitespace checks are part of the final consolidation.

## Live validation still required

The automated suite mocks Discord's external API and SDK. A real Discord client
with the configured Developer Portal mappings must still verify invite acceptance,
joining an already-running instance, image proxy loading, two matches across four
voice channels and mixed website/Activity captains. The undistributed app's pilot
users need developer-team access. See [the local pilot instructions](discord-activities.md).

Discord requires the user to open the invite; a DM cannot silently launch into an
arbitrary voice channel. The destination reflects the verified channel when the
invite is created. A user who subsequently moves channels should click the
original notification again. Activity credentials expire after twelve hours;
an open Activity then repeats the Discord handshake to obtain a new one.
