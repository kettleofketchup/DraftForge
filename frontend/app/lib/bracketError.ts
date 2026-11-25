import { AxiosError } from 'axios';

/**
 * Pulls a user-facing message out of a bracket or Steam-link error
 * response. Backend returns { error, code, details? } on 4xx.
 */
export function parseBracketError(error: unknown): {
  message: string;
  code?: string;
  details?: unknown;
} {
  if (error instanceof AxiosError) {
    const data = error.response?.data as
      | { error?: string; detail?: string; code?: string; details?: unknown }
      | undefined;
    const message =
      data?.error || data?.detail || error.message || 'Bracket request failed';
    return { message, code: data?.code, details: data?.details };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  return { message: 'Bracket request failed' };
}
