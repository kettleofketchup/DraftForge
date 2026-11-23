import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import {
  searchDiscordMembers,
  searchUsers,
  type DiscordSearchResult,
  type SearchUserResult,
} from '~/components/api/api';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import {
  filterUsers,
  USER_SEARCH_DEBOUNCE_MS,
  USER_SEARCH_MIN_LENGTH,
  type FilterUsersOptions,
  type SearchableUser,
} from '~/lib/userSearch';

/** Client-side search over users already loaded: debounced `filterUsers`. */
export function useFilteredUsers<T extends SearchableUser>(
  users: readonly T[] | null | undefined,
  query: string,
  { excludePks, exclude, orgId }: FilterUsersOptions<T> = {},
): T[] {
  const debounced = useDebouncedValue(query, USER_SEARCH_DEBOUNCE_MS);
  const excludeKey = excludePks ? [...excludePks].join(',') : '';
  return useMemo(
    () => filterUsers(users, debounced, { excludePks, exclude, orgId }),
    // excludePks is compared by content so callers can pass a fresh array each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [users, debounced, excludeKey, exclude, orgId],
  );
}

export type UserSearchStatus = 'too-short' | 'searching' | 'error' | 'done';

export interface RemoteSearch<T> {
  /** The debounced, trimmed term the results belong to. */
  term: string;
  results: T[];
  status: UserSearchStatus;
  error: unknown;
}

/** `findSearchedUser` reads site results back from the cache by this prefix. */
export const userSearchKeys = {
  all: ['userSearch'] as const,
  site: (term: string, orgId?: number | null, leagueId?: number | null) =>
    ['userSearch', term, orgId ?? null, leagueId ?? null] as const,
  discordAll: ['discordSearch'] as const,
  discord: (term: string, orgId: number) =>
    ['discordSearch', term, orgId] as const,
};

function useSearchTerm(query: string) {
  const typed = query.trim();
  const term = useDebouncedValue(typed, USER_SEARCH_DEBOUNCE_MS);
  return { typed, term, ready: term.length >= USER_SEARCH_MIN_LENGTH };
}

function statusOf(
  typed: string,
  term: string,
  query: { isFetching: boolean; isError: boolean },
): UserSearchStatus {
  if (typed.length < USER_SEARCH_MIN_LENGTH) return 'too-short';
  if (typed !== term || query.isFetching) return 'searching';
  if (query.isError) return 'error';
  return 'done';
}

export interface UseUserSearchOptions {
  /** Also matches this org's server nicknames and annotates membership; org staff only. */
  orgId?: number | null;
  leagueId?: number | null;
  enabled?: boolean;
}

/** Server-side site user search (`/users/search/`): debounced, with the shared minimum length. */
export function useUserSearch(
  query: string,
  { orgId, leagueId, enabled = true }: UseUserSearchOptions = {},
): RemoteSearch<SearchUserResult> {
  const { typed, term, ready } = useSearchTerm(query);
  const search = useQuery({
    queryKey: userSearchKeys.site(term, orgId, leagueId),
    queryFn: () => searchUsers(term, orgId ?? undefined, leagueId ?? undefined),
    enabled: enabled && ready,
  });
  return {
    term,
    results: search.data ?? [],
    status: statusOf(typed, term, search),
    error: search.error,
  };
}

/** Server-side search of an org's Discord server members. */
export function useDiscordMemberSearch(
  query: string,
  orgId: number | null | undefined,
  { enabled = true }: { enabled?: boolean } = {},
): RemoteSearch<DiscordSearchResult> {
  const { typed, term, ready } = useSearchTerm(query);
  const search = useQuery({
    queryKey: userSearchKeys.discord(term, orgId ?? 0),
    queryFn: () => searchDiscordMembers(orgId!, term),
    enabled: enabled && ready && orgId != null,
  });
  return {
    term,
    results: search.data ?? [],
    status: statusOf(typed, term, search),
    error: search.error,
  };
}
