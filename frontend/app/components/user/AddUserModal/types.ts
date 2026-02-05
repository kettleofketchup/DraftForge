import type { UserType } from '~/components/user/types';
import type { SearchUserResult, DiscordSearchResult, AddMemberPayload } from '~/components/api/api';

export interface EntityContext {
  orgId?: number;
  leagueId?: number;
  tournamentId?: number;
}

export interface AddUserModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  entityContext: EntityContext;
  onAdd: (payload: AddMemberPayload) => Promise<UserType>;
  isAdded: (user: UserType) => boolean;
  entityLabel: string;
  /** Whether the org has a Discord server configured (checks discord_server_id) */
  hasDiscordServer: boolean;
}

export interface SiteUserResultsProps {
  results: SearchUserResult[];
  loading: boolean;
  onAdd: (payload: AddMemberPayload) => Promise<void>;
  isAdded: (user: UserType) => boolean;
  entityLabel: string;
}

export interface DiscordMemberResultsProps {
  results: DiscordSearchResult[];
  loading: boolean;
  onAdd: (payload: AddMemberPayload) => Promise<void>;
  isAdded: (user: UserType) => boolean;
  isDiscordUserAdded: (discordId: string) => boolean;
  entityLabel: string;
  orgId?: number;
  onRefresh: () => Promise<void>;
  refreshing: boolean;
  hasDiscordServer: boolean;
}
