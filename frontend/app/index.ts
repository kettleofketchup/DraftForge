import type {
  GuildMember,
  GuildMembers,
  UserClassType,
  UserType,
  UsersType,
} from '~/components/user';
import { PositionEnum, User } from '~/components/user';
import { DisplayName } from '~/components/user/avatar';
import { AvatarUrl, UserAvatar } from '~/components/user/UserAvatar';
import type { UserAvatarSize, UserAvatarBorder } from '~/components/user/UserAvatar';
import type { GameType, GamesType } from './components/game/types';
import type { TeamType } from './components/team';
import type {
  TeamsType,
  TournamentClassType,
  TournamentType,
  TournamentsType,
} from './components/tournament/types';
export { AvatarUrl, DisplayName, PositionEnum, User, UserAvatar };
export type { UserAvatarSize, UserAvatarBorder };
export type { GuildMember, GuildMembers, UserClassType, UserType, UsersType };

export type {
  GameType,
  GamesType,
  TeamType,
  TeamsType,
  TournamentClassType,
  TournamentType,
  TournamentsType,
};

import type { TeamDraftRoundType, TeamDraftType, DraftRoundType, DraftType } from '~/components/teamdraft/types';
// Primary exports with explicit TeamDraft naming
export type { TeamDraftRoundType, TeamDraftType };
// Backwards compatibility aliases
export type { DraftRoundType, DraftType };
