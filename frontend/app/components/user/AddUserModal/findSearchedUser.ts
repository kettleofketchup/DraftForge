import type { QueryClient } from '@tanstack/react-query';
import type {
  DiscordSearchResult,
  SearchUserResult,
} from '~/components/api/api';
import { userSearchKeys } from '~/hooks/useUserSearch';

export interface SearchedUser {
  pk: number;
  username: string;
  nickname: string | null;
  discordNickname?: string | null;
  guildNickname?: string | null;
  avatarUrl: string | null;
}

/** Look up a user AddUserModal just returned, from its cached search results. */
export function findSearchedUser(
  queryClient: QueryClient,
  pk: number,
): SearchedUser | null {
  for (const [, results] of queryClient.getQueriesData<SearchUserResult[]>({
    queryKey: userSearchKeys.all,
  })) {
    const match = results?.find((u) => u.pk === pk);
    if (match) {
      return {
        pk,
        username: match.username ?? `User #${pk}`,
        nickname: match.nickname ?? null,
        avatarUrl: match.avatarUrl ?? null,
      };
    }
  }
  for (const [, results] of queryClient.getQueriesData<DiscordSearchResult[]>({
    queryKey: userSearchKeys.discordAll,
  })) {
    const member = results?.find((m) => m.site_user_pk === pk);
    if (member) {
      return {
        pk,
        username: member.user.username,
        nickname: null,
        discordNickname: member.user.global_name ?? null,
        guildNickname: member.nick ?? null,
        avatarUrl: member.user.avatar
          ? `https://cdn.discordapp.com/avatars/${member.user.id}/${member.user.avatar}`
          : null,
      };
    }
  }
  return null;
}
