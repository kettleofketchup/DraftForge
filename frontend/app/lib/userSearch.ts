import { currentDisplayOrgId } from '~/lib/displayOrg';
import {
  cachedUserFor,
  isDiscordMember,
  mergeCachedUser,
  resolveDisplayName,
  userRefPk,
  type DiscordMemberLike,
  type UserRef,
} from '~/lib/userDisplayName';

/** `/users/search/` and the Discord member search both reject shorter queries. */
export const USER_SEARCH_MIN_LENGTH = 3;
export const USER_SEARCH_DEBOUNCE_MS = 300;

export type SearchableUser = UserRef | DiscordMemberLike;

export type UserSearchOptions = {
  /** Org whose server nicknames match; defaults to the current page's org, like `DisplayName`. */
  orgId?: number | null;
};

const present = (name: string | null | undefined): name is string =>
  typeof name === 'string' && name.trim() !== '';

/** Every name a user can be shown or known by: username, site nickname, Discord names and the display name. */
export function userSearchNames(
  user: SearchableUser | null | undefined,
  opts?: UserSearchOptions,
): string[] {
  if (!user || typeof user !== 'object') return [];
  if (isDiscordMember(user)) {
    return [user.nick, user.user.global_name, user.user.username].filter(
      present,
    );
  }
  const merged = mergeCachedUser(user, cachedUserFor(user));
  const orgId = opts?.orgId === undefined ? currentDisplayOrgId() : opts.orgId;
  return [
    merged.username,
    merged.nickname,
    merged.discordNickname,
    resolveDisplayName(user, { orgId }),
  ].filter(present);
}

/** Case-insensitive substring match on `userSearchNames`; a blank query matches everyone. */
export function userMatchesQuery(
  user: SearchableUser | null | undefined,
  query: string,
  opts?: UserSearchOptions,
): boolean {
  const q = query.trim().toLowerCase();
  if (q === '') return true;
  return userSearchNames(user, opts).some((n) => n.toLowerCase().includes(q));
}

export type FilterUsersOptions<T> = UserSearchOptions & {
  /** User pks to leave out (already added, already on the roster). */
  excludePks?: Iterable<number | null | undefined>;
  /** Extra predicate for exclusions a pk can't express. */
  exclude?: (user: T) => boolean;
};

/** The users matching `query`, minus exclusions. Use this for every client-side user search. */
export function filterUsers<T extends SearchableUser>(
  users: readonly T[] | null | undefined,
  query: string,
  opts?: FilterUsersOptions<T>,
): T[] {
  if (!users) return [];
  const excluded = new Set(opts?.excludePks ?? []);
  return users.filter((user) => {
    if (!user) return false;
    const pk = userRefPk(user);
    if (pk != null && excluded.has(pk)) return false;
    if (opts?.exclude?.(user)) return false;
    return userMatchesQuery(user, query, opts);
  });
}

/** The user one of whose names equals `name` (case-insensitive), e.g. text typed and submitted with Enter. */
export function findUserByName<T extends SearchableUser>(
  users: readonly T[] | null | undefined,
  name: string,
  opts?: UserSearchOptions,
): T | undefined {
  const target = name.trim().toLowerCase();
  if (target === '' || !users) return undefined;
  return users.find((user) =>
    userSearchNames(user, opts).some((n) => n.toLowerCase() === target),
  );
}
