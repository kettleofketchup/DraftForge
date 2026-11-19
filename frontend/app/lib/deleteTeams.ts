import { isAxiosError } from 'axios';
import { z } from 'zod';

const TeamInUseSchema = z.object({
  code: z.literal('team_in_use'),
  detail: z.string(),
});

export type DeleteTeamsResult =
  | { ok: true }
  | { ok: false; error: unknown; deleted: number[] };

/** The backend's explanation when a DELETE was refused because the team is still referenced. */
export function teamInUseMessage(err: unknown): string | null {
  if (!isAxiosError(err) || err.response?.status !== 409) return null;
  const parsed = TeamInUseSchema.safeParse(err.response.data);
  return parsed.success ? parsed.data.detail : null;
}

export async function deleteTeamsInOrder(
  teams: { pk: number }[],
  remove: (pk: number) => Promise<void>,
): Promise<DeleteTeamsResult> {
  const deleted: number[] = [];
  for (const team of teams) {
    try {
      await remove(team.pk);
    } catch (error) {
      return { ok: false, error, deleted };
    }
    deleted.push(team.pk);
  }
  return { ok: true };
}
