import type { GameMmrs } from '~/components/game/gameMmrs';
import type { ActiveDraftType } from '~/components/user/schemas';
import type { PositionsType, UserType } from '~/components/user/types';

export type { PositionsType };

export interface OrgUserData {
  id: number; // OrgUser.pk (for PATCH operations)
  /** Org MMR per game; read via selectOrgMmr/useOrgMmr. */
  mmrs: GameMmrs;
  _fetchedAt: number;
}

export interface LeagueUserData {
  id: number; // OrgUser.pk of the league's parent org
  mmr: number; // League-scoped MMR snapshot
  _fetchedAt: number;
}

export interface UserEntry {
  // Core identity (stable across all contexts)
  pk: number;
  username: string;
  avatar?: string | null;
  avatarUrl?: string;
  /** Flat rendered-once positions; read via selectPositions/usePlayerPositions for gameType-awareness. */
  positions?: PositionsType;
  steam_account_id?: number | null;
  steam_account_verified?: boolean;
  steam_account_verified_at?: string | null;
  steam_account_verified_org_name?: string | null;
  steam_account_exists_checked?: boolean;
  discordId?: string | null;
  discordNickname?: string | null;
  nickname?: string | null;
  is_staff?: boolean;
  is_superuser?: boolean;
  active_drafts?: ActiveDraftType[];

  // Context-scoped data (keyed by org/league id)
  orgData: Record<number, OrgUserData>;
  leagueData: Record<number, LeagueUserData>;
  /** Discord server nickname per org; `null` means the org member has none. */
  orgNicknames?: Record<number, string | null>;

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
export function isUserEntry(user: UserType | UserEntry): user is UserEntry {
  return typeof user === 'object' && user !== null && 'orgData' in user;
}
