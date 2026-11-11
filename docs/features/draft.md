# Draft System

The draft system allows tournament captains to pick players for their teams. Three draft styles are available, each with different pick order mechanics.

| Snake Draft | Shuffle Draft |
|-------------|---------------|
| ![Snake Draft](https://assets.kettle.sh/draftforge/gifs/snake_draft.gif) | ![Shuffle Draft](https://assets.kettle.sh/draftforge/gifs/shuffle_draft.gif) |
| [:material-play-circle: Full Video](https://assets.kettle.sh/draftforge/videos/snake_draft.webm) | [:material-play-circle: Full Video](https://assets.kettle.sh/draftforge/videos/shuffle_draft.webm) |

## Draft Styles

### Snake Draft

The classic snake draft where pick order reverses each round.

**Pick Pattern (4 teams):**
```
Round 1: Team 1 → Team 2 → Team 3 → Team 4
Round 2: Team 4 → Team 3 → Team 2 → Team 1
Round 3: Team 1 → Team 2 → Team 3 → Team 4
Round 4: Team 4 → Team 3 → Team 2 → Team 1
```

**Characteristics:**

- Predictable pick order
- First pick team gets picks 1, 8, 9, 16
- Last pick team gets picks 4, 5, 12, 13
- Good balance between first and last pick advantage

### Normal Draft

Standard draft where pick order stays the same each round.

**Pick Pattern (4 teams):**
```
Round 1: Team 1 → Team 2 → Team 3 → Team 4
Round 2: Team 1 → Team 2 → Team 3 → Team 4
Round 3: Team 1 → Team 2 → Team 3 → Team 4
Round 4: Team 1 → Team 2 → Team 3 → Team 4
```

**Characteristics:**

- Simple, predictable order
- First pick team has significant advantage
- Last pick team may struggle with player availability

### Shuffle Draft

Dynamic draft where the team with the lowest total MMR always picks next.

**How It Works:**

1. Before each pick, calculate total MMR for each team (captain + all picked members)
2. Team with lowest total MMR picks next
3. If teams are tied, a dice roll determines who picks

**Tie-Breaking:**

When multiple teams have the same lowest MMR:

1. Each tied team rolls a d6 (1-6)
2. Highest roll wins and picks next
3. If rolls tie, re-roll only among still-tied teams
4. Continue until one winner

**Example:**
```
Team A (15,400 MMR) rolls: 4
Team B (15,400 MMR) rolls: 4
Team C (15,400 MMR) rolls: 2

→ Team C eliminated, A and B re-roll

Team A rolls: 3
Team B rolls: 5

→ Team B wins, picks next
```

**Characteristics:**

- Self-balancing - weaker teams get priority picks
- Unpredictable order until draft starts
- Tie-breaker adds excitement
- Cannot simulate final team MMRs in advance

## Draft Style Modal

The Draft Style modal allows admins to:

1. View all draft style options
2. Compare predicted team balance for Snake vs Normal
3. See that Shuffle is dynamic and cannot be predicted
4. Select and apply a draft style

## Pick timer

Each tournament has one `DraftOptions` row (`Tournament.draft_options`, created lazily). Staff edit it through `PATCH /api/tournaments/<pk>/` with `{"draft_options": {...}}`.

| Field | Default | Description |
|-------|---------|-------------|
| `timer_enabled` | `True` (new tournaments open a ready lobby; tournaments that existed before migration `0099` were backfilled with `False`); set to `False` in Draft Settings for an untimed draft | Turns the server-authoritative clock on |
| `grace_time_ms` | `30000` | Free time per pick (>= 1000) |
| `reserve_time_ms` | `30000` | Per-team reserve pool spent after grace (>= 0) |
| `timeout_action` | `skip_turn` | What happens when a pick expires (read-only) |

`Draft.state` follows `pending -> drafting <-> paused / resuming -> completed`. Drafts that predate the timer, or were built outside `build_rounds`, get their state from `Draft.derive_legacy_state()` (`pending`, `drafting` or `completed`).

The clock only runs when `Draft.clock_armed` is true: state is `drafting` or `resuming`, `timer_enabled` is set, and the active round has a `started_at`. Untimed drafts never arm and never start a tick loop.

While armed, the server broadcasts `draft_tick` at 1 Hz:

```json
{
  "type": "draft_tick",
  "draft_state": "drafting",
  "server_time": "2026-11-08T18:42:13.421Z",
  "resuming_until": null,
  "active_round_pk": 9123,
  "active_pick_number": 5,
  "active_captain_id": 77,
  "active_team_id": 310,
  "round_started_at": "2026-11-08T18:42:08.000Z",
  "round_timed_out_at": null,
  "round_grace_time_ms": 30000,
  "teams": [
    {"team_id": 310, "captain_id": 77, "reserve_ms": 30000, "is_connected": true, "is_ready": true}
  ]
}
```

`reserve_ms` is the pool at round start; the client burns the active team's value down locally once grace is over. `is_connected` is heartbeat freshness (key present and age <= 9 s), not `Team.draft_is_connected`. Pick durations, reserve use and skips are stored on each `DraftRound` (`started_at`, `completed_at`, `timed_out_at`, `grace_time_ms`, `pick_duration_ms`, `reserve_used_ms`, `skip_count`).

`pick_player_for_round` accepts an optional `client_picked_at` (ISO, timezone-aware); stamps older than 2 s or in the future are rejected and the server-receive time is used (`pick_time_naive_datetime`, `pick_time_in_future`, `pick_time_too_old`).

## Ready screen

When the timer is enabled, building rounds opens a lobby (`pending`, event `draft_lobby_opened`) instead of starting the clock. The draft never starts on its own.

| Endpoint | Body | Who | Effect |
|----------|------|-----|--------|
| `POST /api/draft/<pk>/ready/` | `{"ready": bool}` | Captain | Sets `Team.draft_is_ready`; emits `captain_ready` / `captain_unready` |
| `POST /api/draft/<pk>/start/` | none | Staff only | Starts the draft and activates the first round |

`/start/` emits `draft_started_by_staff` when every captain is ready and `draft_force_started` (with the `not_ready` list) otherwise. A `drafting` draft whose clock is not yet armed is armed by `/start/`; an already armed draft returns 409 `already_armed`.

## Pause/resume

| Endpoint | Requires | Result |
|----------|----------|--------|
| `POST /api/draft/<pk>/pause/` | `clock_armed` and `drafting` | `paused`, `paused_at` set, `is_manual_pause = true` |
| `POST /api/draft/<pk>/resume/` | `timer_enabled` and `paused` | `resuming` for 3 s (`resuming_until`), then `drafting` |

Errors are 400 `{"code": "wrong_state" | "timer_disabled" | "clock_not_running"}`. Resuming shifts the active round's `started_at` forward by the pause length plus the 3 s countdown, so paused time is never billed. A `started_at IS NULL` round is armed on resume instead.

The tick loop auto-pauses a `drafting` draft when the active captain's heartbeat is stale: `stale = (key missing OR age > 9 s) AND draft_has_connected`. Only the active captain is checked, only while armed. There is no auto-resume; staff or a captain must resume.

Staff may still pick while paused (captains get 403 `paused_staff_only`); the next round is activated with a fresh grace and the pause is not billed.

## Timeout actions

When grace plus reserve is exhausted the tick loop calls the action registered in `TIMEOUT_ACTIONS[options.timeout_action]` (`app.functions.teamdraft_timeout`). It emits `pick_timed_out`, stamps `timed_out_at`, and runs the action. Pick-vs-timeout races are resolved under the draft row lock: whichever commits first wins.

`skip_turn` (snake and normal) swaps the expired pick with the next eligible pick:

```
A B C D  ->  B A C D  ->  B C A D
```

A's pick moves back one slot; if A times out again it moves back again. Slots owned by the same captain, and rounds already picked (including staff picks), are excluded. When no later slot exists (the last slot) nothing is swapped and `pick_skip_unavailable` is emitted; the round keeps `timed_out_at` so it does not re-fire.

Shuffle drafts have no fixed order: `skip_turn` calls `reassign_round_captain(draft, round, exclude_team_ids, reason="timeout_skip")`, which re-selects a different captain for the same round and emits `captain_assigned` with `reason: "timeout_skip"` before `pick_skipped`.

### Events

All carry `pick_number` (the lowest unpicked round, or `null`) except `draft_lobby_opened`, which has only the keys below. Captain references are denormalised as `<role>_captain_id`, `_captain_name`, `_captain_avatar_url`, `_team_id`, `_team_name` (role is empty, `skipped` or `next`).

| Event | Payload (beyond `pick_number`) |
|-------|--------------------------------|
| `draft_lobby_opened` | `timer_enabled`, `grace_time_ms`, `reserve_time_ms` |
| `captain_ready` / `captain_unready` | `captain_*`, `team_*` |
| `captain_connected` / `captain_disconnected` | `captain_*`, `team_*`, `is_active_captain` |
| `draft_started_by_staff` | `actor_id`, `actor_name` |
| `draft_force_started` | `actor_id`, `actor_name`, `not_ready: [{team_id, team_name, captain_id, captain_name}]` |
| `round_started` | `captain_*`, `team_*`, `started_at`, `grace_time_ms`, `reserve_ms` |
| `draft_paused` | `reason` (`manual` / `captain_disconnected`), `paused_by_id`, `paused_by_name` (null for auto), `captain_*` |
| `draft_resumed` | `resumed_by_id`, `resumed_by_name`, `resuming_until` (all `null` when the timer is switched off mid-pause) |
| `pick_timed_out` | `captain_*`, `team_*`, `elapsed_ms`, `reserve_used_ms` |
| `pick_skipped` | `skipped_captain_*`, `skipped_team_*`, `next_captain_*`, `next_team_*`, `from_pick_number`, `to_pick_number`, `deferred_to_pick_number` (null for shuffle), `pick_duration_ms`, `reserve_used_ms` |
| `pick_skip_unavailable` | `captain_*`, `team_*` |
| `draft_options_changed` | `timer_enabled`, `grace_time_ms`, `reserve_time_ms`, `changed_by_id`, `changed_by_name`, `from_state`, `to_state`; emitted when a Draft Settings save changes any option on a tournament that has a draft, so open draft windows get the new state |

### Backend tests

```bash
just test::run 'python manage.py test app.tests.test_draft_options app.tests.test_teamdraft_timer app.tests.test_teamdraft_timeout -v 2'
```

## Data Models

### Draft

| Field | Type | Description |
|-------|------|-------------|
| `tournament` | ForeignKey | Associated tournament |
| `draft_style` | CharField | `snake`, `normal`, or `shuffle` |
| `state` | CharField | `pending`, `drafting`, `paused`, `resuming`, `completed` |
| `paused_at` | DateTimeField | When the draft was paused (null otherwise) |
| `resuming_until` | DateTimeField | End of the 3 s resume countdown (null otherwise) |
| `is_manual_pause` | Boolean | Pause came from a user rather than a stale heartbeat |

### DraftRound

| Field | Type | Description |
|-------|------|-------------|
| `draft` | ForeignKey | Parent draft |
| `captain` | ForeignKey | Captain making the pick |
| `pick_number` | Integer | Sequential pick number (1, 2, 3...) |
| `pick_phase` | Integer | Phase/round of the draft |
| `choice` | ForeignKey | Player selected (null until picked) |
| `was_tie` | Boolean | Whether tie-breaking was needed |
| `tie_roll_data` | JSONField | Tie resolution details |
| `started_at` | DateTimeField | When the round's clock started (null if unarmed) |
| `completed_at` | DateTimeField | When the pick was made |
| `timed_out_at` | DateTimeField | When the pick expired |
| `grace_time_ms` | Integer | Grace applied to this round |
| `pick_duration_ms` | Integer | Time the pick took |
| `reserve_used_ms` | Integer | Reserve debited for the pick |
| `skip_count` | Integer | Times the pick was skipped |

### Team (timing fields)

| Field | Type | Description |
|-------|------|-------------|
| `draft_reserve_ms` | Integer | Remaining reserve pool |
| `draft_is_ready` | Boolean | Captain readied up in the lobby |
| `draft_is_connected` | Boolean | Captain currently connected |
| `draft_has_connected` | Boolean | Captain has connected at least once |

### DraftOptions

| Field | Type | Description |
|-------|------|-------------|
| `tournament` | OneToOne | `related_name="draft_options"` |
| `timer_enabled` | Boolean | Default `True` |
| `grace_time_ms` | Integer | Default 30000 |
| `reserve_time_ms` | Integer | Default 30000 |
| `timeout_action` | CharField | `skip_turn` |

### tie_roll_data Structure

When a tie occurs in Shuffle draft, the `tie_roll_data` field contains:

```json
{
  "tied_teams": [
    {"id": 1, "name": "Team Alpha", "mmr": 15400},
    {"id": 2, "name": "Team Beta", "mmr": 15400}
  ],
  "roll_rounds": [
    [
      {"team_id": 1, "roll": 4},
      {"team_id": 2, "roll": 4}
    ],
    [
      {"team_id": 1, "roll": 3},
      {"team_id": 2, "roll": 5}
    ]
  ],
  "winner_id": 2
}
```

## API Endpoints

### Pick Player

```
POST /api/tournaments/{id}/draft/pick/
```

**Request:**
```json
{
  "player_id": 123
}
```

**Response (Shuffle Draft with tie):**
```json
{
  "success": true,
  "tournament": { ... },
  "next_pick": {
    "captain_id": 5,
    "team_id": 2,
    "team_name": "Team Beta",
    "team_mmr": 15400
  },
  "tie_resolution": {
    "tied_teams": [...],
    "roll_rounds": [...],
    "winner_id": 2
  }
}
```

### Lobby and Clock Actions

```
POST /api/draft/{id}/ready/    {"ready": true}
POST /api/draft/{id}/start/
POST /api/draft/{id}/pause/
POST /api/draft/{id}/resume/
```

Success returns 200 with the tournament payload. Errors are 400 `{"code": "wrong_state" | "timer_disabled" | "clock_not_running"}` or 409 `{"code": "already_armed"}`. Picks can also fail with 409 `not_active_round`, `draft_not_accepting_picks` or `already_picked`, and 403 `paused_staff_only`. See [Pick timer](#pick-timer).

### Update Draft Style

```
PUT /api/drafts/{id}/
```

**Request:**
```json
{
  "draft_style": "shuffle"
}
```

## Frontend Components

### TieResolutionOverlay

Displays when a tie occurs during Shuffle draft:

- Shows all tied teams with their MMR
- Displays each round of dice rolls
- Highlights the winner
- "Continue" button to proceed

### DraftStyleModal

Allows selecting draft style:

- Snake Draft option with predicted MMR balance
- Normal Draft option with predicted MMR balance
- Shuffle Draft option (dynamic balance, no prediction)
- Apply button to change style

### DraftLobby

Shown while the draft is `pending` and the timer is on. Lists each team with a connected dot and a ready check. Captains get a ready toggle; staff get Start (or Force start, which opens a confirm dialog naming the teams that are not ready). Non-staff see "waiting for staff". The staff button that opens the draft modal is labelled "Open draft".

### DraftClockBar

Shows the active captain, the grace countdown, and a reserve bar and chip per team. Untimed or unarmed drafts show "No pick clock" with a "Start clock" button for staff. When time runs out it shows the expired copy until the server skips the turn.

### DraftPauseOverlay

Shown while the draft is `paused` or `resuming`, with a 3 s resume countdown. Resume is disabled while the active captain's heartbeat is stale. Freshness comes from `initial_state.captain_fresh`, tick frames and the `captain_heartbeat` frame, not from socket presence. A captain who goes stale during a manual pause is not reported until the tick loop runs again, so Resume stays enabled and the draft re-pauses on the first tick. A captain's own socket may receive `captain_heartbeat` before `initial_state`, and the frame fires when a stale or absent captain connects as well as on a later heartbeat. Staff also get Pick-for-captain.

### Settings

`DraftStyleModal` has Grace seconds, Reserve seconds and Timer enabled, saved via `PATCH /api/tournaments/<pk>/`. `timeout_action` is not exposed.

### Test IDs

| Test ID | Element |
|---------|---------|
| `draft-lobby` | Lobby container |
| `lobby-team-row-<pk>` | Team row |
| `lobby-connected-dot-<pk>` | Captain connected dot |
| `lobby-ready-check-<pk>` | Captain ready check |
| `lobby-ready-toggle` | Captain ready toggle |
| `lobby-waiting-for-staff` | Waiting message for non-staff |
| `lobby-start-button` | Staff Start / Force start |
| `lobby-force-start-dialog` | Force start dialog |
| `lobby-force-start-not-ready` | Not-ready team list |
| `lobby-force-start-confirm` | Force start confirm |
| `draft-clock-bar` | Clock strip |
| `draft-clock-active-captain` | Active captain name |
| `draft-clock-your-turn` | Your-turn marker |
| `draft-clock-grace` | Grace countdown |
| `draft-clock-reserve-<teamPk>` | Team reserve (carries `data-pct`) |
| `draft-clock-unarmed` | "No pick clock" |
| `draft-clock-start-button` | Staff Start clock |
| `draft-clock-pause-button` | Staff Pause |
| `draft-clock-expired` | Expired copy |
| `draft-paused-overlay` | Pause overlay |
| `draft-paused-banner` | Collapsed pause banner |
| `draft-paused-expand` | Expand banner |
| `draft-paused-title` | Pause title |
| `draft-paused-message` | Pause message |
| `draft-resume-button` | Resume |
| `draft-pick-for-captain-button` | Staff Pick-for-captain |
| `draft-resuming-countdown` | Resume countdown |
| `turn-indicator` | Turn indicator (mounted by `DraftRoundView`) |
| `turn-indicator-deferred` | Deferred-turn indicator |
| `available-players-section` | Available players |
| `prevRoundButton` / `nextRoundButton` / `latestRoundButton` | Round navigation |
| `pick-duration-<userPk>` | Pick duration in completed view and history |
| `pick-skips-<userPk>` | Skip count in completed view and history |
| `draft-options-form` | Draft settings form |
| `draft-options-timer-enabled` | Timer enabled switch |
| `draft-options-grace-s` | Grace seconds input |
| `draft-options-reserve-s` | Reserve seconds input |
| `draft-options-save` | Save settings |
| `draft-event-row-<event_type>` | Event feed row |
| `draft-event-text` | Event feed text |
| `startTeamDraftButton` | Staff "Open draft" button |

### Frontend E2E Tests (Playwright)

Every title carries `@cicd`.

| Spec | Populate key |
|------|--------------|
| `07-draft/07-ready-screen.spec.ts` | `draft_timer_ready` |
| `07-draft/08-timer-countdown.spec.ts` | `draft_timer_countdown` |
| `07-draft/09-timeout-skip.spec.ts` | `draft_timer_skip` |
| `07-draft/10-pause-resume.spec.ts` | `draft_timer_pause` |
| `08-shuffle-draft/04-timeout-skip.spec.ts` | `shuffle_timer_skip` |

```bash
just test::pw::spec 07-draft
just test::pw::spec 08-shuffle-draft
```

## Implementation Notes

### Snake/Normal vs Shuffle

| Aspect | Snake/Normal | Shuffle |
|--------|--------------|---------|
| Round creation | All rounds created upfront | First round only, rest created dynamically |
| Pick order | Predetermined | Calculated after each pick |
| Predictable | Yes | No |
| MMR simulation | Can predict final team MMRs | Cannot predict |

### Team total_mmr Calculation

```python
total_mmr = captain.mmr + sum(member.mmr for member in members if member != captain)
```

The captain is always included, and members exclude the captain to avoid double-counting.
