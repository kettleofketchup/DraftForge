import { isAxiosError, type AxiosError } from 'axios';
import { z } from 'zod';
import { PositionSchema } from '~/components/user/schemas';
import axios from './axios';

// OrgUserSerializer / TournamentUserSerializer output; avatarUrl is null for
// users without a discordId, so UserSchema cannot be reused here.
export const RosterUserSchema = z
  .object({
    pk: z.number(),
    username: z.string().nullable(),
    nickname: z.string().nullable().optional(),
    avatar: z.string().nullable().optional(),
    avatarUrl: z.string().nullable().optional(),
    discordId: z.string().nullable().optional(),
    discordNickname: z.string().nullable().optional(),
    guildNickname: z.string().nullable().optional(),
    positions: PositionSchema.nullable().optional(),
    mmr: z.number().nullable().optional(),
    league_mmr: z.number().nullable().optional(),
    steam_account_id: z.number().nullable().optional(),
    orgUserPk: z.number().optional(),
  })
  .passthrough();
export type RosterUser = z.infer<typeof RosterUserSchema>;

// TournamentSerializerBase in backend/app/serializers.py
const ManagedTeamTournamentSchema = z.object({
  pk: z.number(),
  name: z.string(),
  date_played: z.string().nullable(),
  users: z.array(z.number()),
  captains: z.array(z.number()),
  tournament_type: z.string(),
});

export const LeadershipProblemSchema = z.object({
  field: z.enum(['captain', 'deputy_captain']),
  code: z.enum([
    'captain_not_member',
    'deputy_not_member',
    'deputy_is_captain',
  ]),
  message: z.string(),
});
export type LeadershipProblem = z.infer<typeof LeadershipProblemSchema>;

export const ManagedTeamSchema = z.object({
  pk: z.number(),
  name: z.string(),
  tournament: ManagedTeamTournamentSchema.nullable(),
  members: z.array(RosterUserSchema),
  dropin_members: z.array(RosterUserSchema),
  left_members: z.array(RosterUserSchema),
  captain: RosterUserSchema.nullable(),
  deputy_captain: RosterUserSchema.nullable(),
  draft_order: z.number().nullable(),
  current_points: z.number(),
  total_mmr: z.number(),
  placement: z.number().nullable(),
  leadership_problems: z.array(LeadershipProblemSchema),
  can_manage_team: z.boolean(),
});
export type ManagedTeam = z.infer<typeof ManagedTeamSchema>;

export const TeamLogSchema = z.object({
  id: z.number(),
  action: z.string(),
  via: z.string(),
  actor: RosterUserSchema.nullable(),
  target: RosterUserSchema.nullable(),
  reason: z.string(),
  override_rules: z.array(z.unknown()),
  details: z.record(z.string(), z.unknown()),
  team_name: z.string(),
  team_id: z.number().nullable(),
  created_at: z.string(),
});
export type TeamLog = z.infer<typeof TeamLogSchema>;

export const TeamHistoryPageSchema = z.object({
  count: z.number(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(TeamLogSchema),
});
export type TeamHistoryPage = z.infer<typeof TeamHistoryPageSchema>;

export const TeamManagementErrorSchema = z.object({
  code: z.string(),
  detail: z.string(),
});
export type TeamManagementErrorBody = z.infer<typeof TeamManagementErrorSchema>;

/** A refusal from the team management service (400 `{code, detail}`). */
export function isTeamManagementError(
  err: unknown,
): err is AxiosError<TeamManagementErrorBody> {
  return (
    isAxiosError(err) &&
    err.response?.status === 400 &&
    TeamManagementErrorSchema.safeParse(err.response.data).success
  );
}

export type TeamActionBody = { reason: string; acknowledged_codes: string[] };
export type TeamUserActionBody = { user_id: number } & TeamActionBody;
export type TeamDeputyBody = { user_id: number | null } & TeamActionBody;
export type TeamSubInBody = {
  standin_id: number;
  replacing_id?: number | null;
} & TeamActionBody;
export type TeamRenameBody = { name: string } & TeamActionBody;

async function postTeamAction(
  teamId: number,
  path: string,
  body: TeamActionBody,
): Promise<ManagedTeam> {
  const response = await axios.post(`/teams/${teamId}/${path}/`, body);
  return ManagedTeamSchema.parse(response.data);
}

export const setTeamCaptain = (teamId: number, body: TeamUserActionBody) =>
  postTeamAction(teamId, 'set-captain', body);

export const setTeamDeputy = (teamId: number, body: TeamDeputyBody) =>
  postTeamAction(teamId, 'set-deputy', body);

export const markTeamDropout = (teamId: number, body: TeamUserActionBody) =>
  postTeamAction(teamId, 'dropout', body);

export const restoreTeamMember = (teamId: number, body: TeamUserActionBody) =>
  postTeamAction(teamId, 'restore', body);

export const addTeamStandin = (teamId: number, body: TeamUserActionBody) =>
  postTeamAction(teamId, 'standins', body);

export const removeTeamStandin = (teamId: number, body: TeamUserActionBody) =>
  postTeamAction(teamId, 'standins/remove', body);

export const subInTeamStandin = (teamId: number, body: TeamSubInBody) =>
  postTeamAction(teamId, 'sub-in', body);

export const renameTeam = (teamId: number, body: TeamRenameBody) =>
  postTeamAction(teamId, 'rename', body);

export async function fetchTeamHistory(
  teamId: number,
  page = 1,
  pageSize?: number,
): Promise<TeamHistoryPage> {
  const params =
    pageSize === undefined ? { page } : { page, page_size: pageSize };
  const response = await axios.get(`/teams/${teamId}/history/`, { params });
  return TeamHistoryPageSchema.parse(response.data);
}
