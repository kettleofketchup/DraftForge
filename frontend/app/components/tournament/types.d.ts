import { z } from 'zod';
import { DraftSchema } from '../draft/types';
import { GameSchema } from '../game/types';
import { UserSchema } from '../user/user';
import { STATE_CHOICES, TOURNAMENT_TYPE } from './constants';

export const TeamSchema = z.object({
  name: z.string().min(1).max(100).nullable(),
  date: z.string().min(1).max(100).nullable(),
  members: z.array(UserSchema).nullable(),
  pk: z.number().min(0).nullable(),
  captain: UserSchema.nullable(),
  dropin_members: z.array(UserSchema).nullable(),
  left_members: z.array(UserSchema).nullable(),
  draft: DraftSchema.nullable(),
  draft_order: z.number().nullable(),
  tournament: z.number().nullable(),
  current_points: z.number().nullable(),
  members_ids: z.array(z.number()).nullable(),
  dropin_member_ids: z.array(z.number()).nullable(),
  left_member_ids: z.array(z.number()).nullable(),
  captain_id: z.number().nullable(),
});

export const TournamentSchema = z.object({
  name: z.string().nullable(),
  date_played: z.string().nullable(),
  users: z.array(UserSchema).nullable(),
  teams: z.array(TeamSchema).nullable(),
  captains: z.array(UserSchema).nullable(),
  captain_ids: z.array(z.number()).nullable(),
  pk: z.number().nullable(),
  winning_team: z.number().nullable(),
  state: z.nativeEnum(STATE_CHOICES).nullable(),
  tournament_type: z.nativeEnum(TOURNAMENT_TYPE).nullable(),
  games: z.array(GameSchema).nullable(),
  user_ids: z.array(z.number()).nullable(),
  team_ids: z.array(z.number()).nullable(),
});

export type TeamType = z.infer<typeof TeamSchema>;
export type TournamentType = z.infer<typeof TournamentSchema>;

export declare interface TournamentClassType extends TournamentType {
  dbFetch: () => Promise<void>;
  dbUpdate: (data: Partial<TournamentType>) => Promise<void>;
  dbCreate: () => Promise<void>;
  dbDelete: () => Promise<void>;
}

export type TournamentsType = TournamentType[];
export type TeamsType = TeamType[];
