import { extractApiError } from '~/lib/apiError';

const FALLBACK = 'Failed to start tournament';

type StartErrorBody = { code?: unknown; error?: unknown };

export function startTournamentErrorMessage(err: unknown): string {
  const data = (err as { response?: { data?: unknown } } | undefined)?.response
    ?.data;
  if (!data || typeof data !== 'object') return FALLBACK;
  const body = data as StartErrorBody;
  if (body.code !== 'ready_check_held') return FALLBACK;
  return (
    extractApiError({ response: { data: { error: body.error } } }) ?? FALLBACK
  );
}
