import type { ActiveDraftType } from '~/components/user/schemas';
import type { PositionsType, UserType } from '~/components/user/types';

export interface OrgUserData {
  id: number; // OrgUser.pk (for PATCH operations)
  mmr: number; // Org-scoped MMR
  _fetchedAt: number;
}

export interface LeagueUserData {
  id: number; // LeagueUser.pk
  mmr: number; // League-scoped MMR snapshot
  _fetchedAt: number;
}

export interface UserEntry {
  // Core identity (stable across all contexts)
  pk: number;
  username: string;
  avatar?: string | null;
  avatarUrl?: string;
  positions?: PositionsType;
  steamid?: number | null;
  steam_account_id?: number | null;
  discordId?: string | null;
  discordNickname?: string | null;
  guildNickname?: string | null;
  nickname?: string | null;
  is_staff?: boolean;
  is_superuser?: boolean;
  active_drafts?: ActiveDraftType[];

  // Context-scoped data (keyed by org/league id)
  orgData: Record<number, OrgUserData>;
  leagueData: Record<number, LeagueUserData>;

  // Staleness tracking
  _fetchedAt: number;
}

export interface UpsertContext {
  orgId?: number;
  leagueId?: number;
}

/**
 * Type guard: distinguishes UserEntry (has orgData) from legacy UserType.
 * Use in backward-compat code instead of `as any` casts.
 */
export function isUserEntry(
  user: UserType | UserEntry,
): user is UserEntry {
  return 'orgData' in user;
}
