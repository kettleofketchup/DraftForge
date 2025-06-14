import type {
  APIUser as DiscordUser,
  APIGuildMember,
} from 'discord-api-types/v10';

export type GuildMember = APIGuildMember;
export type GuildMembers = GuildMember[];

export declare interface UserType {
  [key: string]: any;
  username: string;
  avatarUrl: string;
  is_staff: boolean;
  is_superuser: boolean;
  nickname?: string | null;
  mmr?: number;
  position?: string;
  steamid?: number;
  avatar?: string;
  pk: number;
  discordNickname?: string | null;
  discordId?: string;
  guildNickname?: string | null;

  setFromGuildMember?: (member: GuildMember) => void;
  getAvatarUrl?: () => string;
}

export declare interface UserClassType extends UserType {
  setFromGuildMember: (member: GuildMember) => void;
  getAvatarUrl: () => string;
  dbFetch: () => Promise<UserType>;
  dbUpdate: (data: Partial<UserType>) => Promise<UserType>;
  dbCreate: () => Promise<UserType>;
  dbDelete: () => Promise<void>;
}

export declare type UsersType = UserType[];
