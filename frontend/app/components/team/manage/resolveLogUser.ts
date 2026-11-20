import { userRefPk, type UserRef } from '~/lib/userDisplayName';
import type { UserEntry } from '~/store/userCacheTypes';
import type { UserLike } from './leadershipProblemText';

type RosterLike = {
  members?: readonly UserLike[] | null;
  dropin_members?: readonly UserLike[] | null;
  left_members?: readonly UserLike[] | null;
  captain?: UserLike | null;
  deputy_captain?: UserLike | null;
};

export type UnresolvedLogUser = { pk: number; fallbackLabel: string };

export type ResolveLogUserSources = {
  team?: RosterLike | null;
  tournamentUsers?: readonly UserLike[] | null;
  cache?: { getById(pk: number): UserEntry | undefined } | null;
};

const named = (value: string | null | undefined): boolean =>
  typeof value === 'string' && value.trim() !== '';

// Hydration leaves `{pk}` stubs for users it could not find.
const isResolved = (user: UserLike): boolean => {
  const ref = user as UserRef;
  return named(ref.username) || named(ref.nickname);
};

function find(
  users: Iterable<UserLike | null | undefined>,
  pk: number,
): UserLike | undefined {
  for (const user of users) {
    if (user && userRefPk(user) === pk && isResolved(user)) return user;
  }
  return undefined;
}

export function isUnresolvedLogUser(
  user: UserLike | UnresolvedLogUser,
): user is UnresolvedLogUser {
  return 'fallbackLabel' in user;
}

/** Resolves a pk from a history snapshot: roster, tournament users, user cache, then a label. */
export function resolveLogUser(
  pk: number,
  { team, tournamentUsers, cache }: ResolveLogUserSources = {},
): UserLike | UnresolvedLogUser {
  const roster = team
    ? [
        ...(team.members ?? []),
        ...(team.dropin_members ?? []),
        ...(team.left_members ?? []),
        team.captain,
        team.deputy_captain,
      ]
    : [];
  const cached = cache?.getById(pk);
  return (
    find(roster, pk) ??
    find(tournamentUsers ?? [], pk) ??
    find(cached ? [cached] : [], pk) ?? { pk, fallbackLabel: `Player #${pk}` }
  );
}
