import type { APIGuildMember } from 'discord-api-types/v10';
import { PositionEnum } from './constants';
export type GuildMember = APIGuildMember;
export type GuildMembers = GuildMember[];

export type PositionsMap = {
  [key in PositionEnum]?: boolean;
};

/**
 * Represents a player's ranks across all Dota 2 positions.
 */
export interface PositionsType {
  /** Rank of the carry position */
  carry: number;
  /** Rank of the mid position */
  mid: number;
  /** Rank of the offlane position */
  offlane: number;
  /** Rank of the soft support position */
  soft_support: number;
  /** Rank of the hard support position */
  hard_support: number;
}

export interface UserType {
  [key: string]: any;
  username: string;
  avatarUrl: string;
  is_staff: boolean;
  is_superuser: boolean;
  nickname?: string | null;
  mmr?: number;
  positions?: PositionsType;
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
