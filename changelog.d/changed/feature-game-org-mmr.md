- API: member payloads carry `mmr_game_type`, the game their `mmr` was resolved for. In
  Deadlock tournaments and events `mmr` is now the Deadlock org MMR. The org users
  endpoint, the org user PATCH response and claim requests add the full per-game set
  (`game_mmrs`, `target_game_mmrs`); gated event signups add `org_user_game_mmrs`,
  `self_reported_rank` and `self_reported_rank_date`.
- API: `PATCH /api/organizations/{id}/users/{org_user_id}/` takes
  `{"game_mmrs": {"<game_type>": int | null}}`. Values must be integers in 0–20000 and
  keys known game ids, or the request returns 400. `null` or 0 clears a game. A bare
  `{"mmr": n}` without `mmr_game_type` returns 400. Each changed game logs an `OrgLog`
  `set_mmr` entry.
- Signup approval writes the org MMR of the event's game. The Dota verification flags
  are set only for Dota events. `suggested_mmr` and `suggested_mmr_range` can be `null`
  (source `"none"`) for games without a suggestion.
- The MMR approval dialog now requires a value; Deadlock needs at least 1.
- CSV import rejects `mmr` cells outside 0–20000 as row errors instead of storing them,
  and the tournament import refuses the `league` MMR target for non-Dota tournaments.
- The Django admin shows org MMRs read-only; edit them from the organization page.
- Deadlock tournaments no longer show the league MMR on player cards and player strips;
  league MMR is a Dota 2 value and still shows in Dota 2 tournaments.
