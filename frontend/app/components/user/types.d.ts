import type { APIGuildMember } from 'discord-api-types/v10';
import { z } from 'zod';
import { PositionEnum } from './constants';
import { PositionSchema, UserSchema } from './schemas';
export type GuildMember = APIGuildMember;
export type GuildMembers = GuildMember[];
export type PositionsMap = {
  [key in PositionEnum]?: boolean;
};

/**
 * Represents a player's ranks across all Dota 2 positions.
 */
export type PositionsType = z.infer<typeof PositionSchema>;

export type UserType = z.infer<typeof UserSchema>;

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

export interface UserClassType extends UserType {
  [key: string]: any;

  setFromGuildMember: (member: GuildMember) => void;
  getAvatarUrl: () => string;
  dbFetch: () => Promise<UserType>;
  dbUpdate: (data: Partial<UserType>) => Promise<UserType>;
  dbCreate: () => Promise<UserType>;
  dbDelete: () => Promise<void>;
}

export declare type UsersType = UserType[];
