import { isAxiosError } from 'axios';
import { z } from 'zod';
import type { TeamUsageCheck } from '~/components/api/teamAPI';

const TeamInUseSchema = z.object({
  code: z.literal('team_in_use'),
  detail: z.string(),
});

export type DeleteTeamsResult =
  | { ok: true }
  | { ok: false; blocked: string[] }
  | { ok: false; error: unknown; deleted: number[] };

/** The backend's explanation when a DELETE was refused because the team is still referenced. */
export function teamInUseMessage(err: unknown): string | null {
  if (!isAxiosError(err) || err.response?.status !== 409) return null;
  const parsed = TeamInUseSchema.safeParse(err.response.data);
  return parsed.success ? parsed.data.detail : null;
}

/** Checks every team first, so a team still in use stops the run before anything is deleted. */
export async function deleteTeamsInOrder(
  teams: { pk: number }[],
  api: {
    checkUsage: (pk: number) => Promise<TeamUsageCheck>;
    remove: (pk: number) => Promise<void>;
  },
): Promise<DeleteTeamsResult> {
  let checks: TeamUsageCheck[];
  try {
    checks = await Promise.all(teams.map((team) => api.checkUsage(team.pk)));
  } catch (error) {
    return { ok: false, error, deleted: [] };
  }
  const blocked = checks.flatMap((check) =>
    check.in_use && check.detail ? [check.detail] : [],
  );
  if (blocked.length) return { ok: false, blocked };

  const deleted: number[] = [];
  for (const team of teams) {
    try {
      await api.remove(team.pk);
    } catch (error) {
      return { ok: false, error, deleted };
    }
    deleted.push(team.pk);
  }
  return { ok: true };
}

export function deleteTeamsMessage(
  result: Exclude<DeleteTeamsResult, { ok: true }>,
): string {
  if ('blocked' in result) {
    return `No teams were deleted or created. ${result.blocked.join(' ')}`;
  }
  const cause =
    teamInUseMessage(result.error) ?? 'Failed to delete the existing teams.';
  const n = result.deleted.length;
  if (n === 0) return `${cause} No teams were deleted or created.`;
  const already =
    n === 1 ? '1 team was already deleted' : `${n} teams were already deleted`;
  return `${cause} ${already}; no teams were created.`;
}
