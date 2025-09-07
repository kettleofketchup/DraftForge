import type { APIGuildMember } from 'discord-api-types/v10';
import { PositionEnum } from './constants';
export type GuildMember = APIGuildMember;
export type GuildMembers = GuildMember[];
export type PositionsMap = {
  [key in PositionEnum]?: boolean;
};

import { z } from 'zod';

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
export const PositionSchema = z.object({
  pk: z.number().optional(),
  carry: z.number().min(0, { message: 'Carry position must be selected.' }),
  mid: z.number().min(0, { message: 'Mid position must be selected.' }),
  offlane: z.number().min(0, { message: 'Offlane position must be selected.' }),
  soft_support: z
    .number()
    .min(0, { message: 'Soft Support position must be selected.' }),
  hard_support: z
    .number()
    .min(0, { message: 'Hard Support position must be selected.' }),
});

export const UserSchema = z.object({
  positions: PositionSchema,
  username: z.string().min(2).max(100),
  avatarUrl: z.string().url(),
  is_staff: z.boolean(),
  is_superuser: z.boolean(),
  nickname: z.string().min(2).max(100).nullable(),
  mmr: z.number().min(0).nullable(),
  steamid: z.number().min(0).nullable(),
  avatar: z.string().url().nullable(),
  pk: z.number().min(0),
  discordNickname: z.string().min(2).max(100).nullable(),
  discordId: z.string().min(2).max(100).nullable(),
  guildNickname: z.string().min(2).max(100).nullable(),
});

export interface UserType extends z.infer<typeof UserSchema> {
  [key: string]: any;
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
