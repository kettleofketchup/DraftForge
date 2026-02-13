/**
 * Hydrate slim API responses (PK-only user references) back to full user
 * objects using the _users dict.
 *
 * The backend returns deduplicated user data in `_users: { pk: UserObj }`.
 * All other fields (users, captains, team.members, team.captain, etc.)
 * contain only integer PKs. These functions resolve those PKs so that
 * downstream components continue to receive full user objects.
 */
import type { DraftType } from '~/components/teamdraft/types';
import type { TournamentType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';

type UsersMap = Record<number, UserType>;

function resolve(ref: unknown, map: UsersMap): unknown {
  if (ref == null) return ref;
  if (typeof ref === 'number') return map[ref] ?? { pk: ref };
  return ref;
}

function resolveArray(refs: unknown, map: UsersMap): unknown[] {
  if (!Array.isArray(refs)) return [];
  return refs.map((r) => resolve(r, map));
}

function hydrateTeam(team: unknown, map: UsersMap): unknown {
  if (team == null || typeof team !== 'object') return team;
  const t = team as Record<string, unknown>;
  return {
    ...t,
    members: resolveArray(t.members, map),
    captain: resolve(t.captain, map),
    deputy_captain: resolve(t.deputy_captain, map),
    dropin_members: resolveArray(t.dropin_members, map),
    left_members: resolveArray(t.left_members, map),
  };
}

function hydrateDraftFields(raw: DraftType, map: UsersMap): DraftType {
  return {
    ...raw,
    users_remaining: resolveArray(raw.users_remaining, map),
    draft_rounds: (raw.draft_rounds ?? []).map((round) => ({
      ...round,
      captain: resolve(round.captain, map),
      choice: resolve(round.choice, map),
      ...(round.team && typeof round.team === 'object'
        ? { team: hydrateTeam(round.team, map) }
        : {}),
    })),
  } as DraftType;
}

/** Hydrate a tournament response (with nested draft, teams, games). */
export function hydrateTournament(
  raw: TournamentType & { _users?: Record<number, unknown> },
): TournamentType {
  const map = raw._users as UsersMap | undefined;
  if (!map) return raw;

  const teams = (raw.teams ?? []).map((t) => hydrateTeam(t, map));

  const games = (raw.games ?? []).map((g) => {
    const gObj = g as Record<string, unknown>;
    return {
      ...gObj,
      radiant_team: hydrateTeam(gObj.radiant_team, map),
      dire_team: hydrateTeam(gObj.dire_team, map),
      winning_team: hydrateTeam(gObj.winning_team, map),
    };
  });

  const draft = raw.draft ? hydrateDraftFields(raw.draft, map) : raw.draft;

  return {
    ...raw,
    users: resolveArray(raw.users, map),
    captains: resolveArray(raw.captains, map),
    teams,
    games,
    draft,
  } as TournamentType;
}

/** Hydrate a standalone draft response (from GET /drafts/:pk/). */
export function hydrateDraft(
  raw: DraftType & { _users?: Record<number, unknown> },
): DraftType {
  const map = (raw as Record<string, unknown>)._users as UsersMap | undefined;
  if (!map) return raw;
  return hydrateDraftFields(raw, map);
}
