import type { APIGuildMember } from 'discord-api-types/v10';
import { PositionEnum } from './constants';
export type GuildMember = APIGuildMember;
export type GuildMembers = GuildMember[];

export type PositionsMap = {
  [key in PositionEnum]?: boolean;
};

export interface UserType {
  [key: string]: any;
  username: string;
  avatarUrl: string;
  is_staff: boolean;
  is_superuser: boolean;
  nickname?: string | null;
  mmr?: number;
  positions?: PositionsMap;
  steamid?: number;
  avatar?: string;
  pk: number;
  discordNickname?: string | null;
  discordId?: string;
  guildNickname?: string | null;

  setFromGuildMember?: (member: GuildMember) => void;
  getAvatarUrl?: () => string;
}

export enum PositionEnum {
  Carry = 1,
  Mid = 2,
  Offlane = 3,
  SoftSupport = 4,
  HardSupport = 5,
}

export type PositionsMap = {
  [key in PositionEnum]?: boolean;
};

export declare interface UserClassType extends UserType {
  setFromGuildMember: (member: GuildMember) => void;
  getAvatarUrl: () => string;
  dbFetch: () => Promise<UserType>;
  dbUpdate: (data: Partial<UserType>) => Promise<UserType>;
  dbCreate: () => Promise<UserType>;
  dbDelete: () => Promise<void>;
}

export declare type UsersType = UserType[];
