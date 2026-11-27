import {
  formatDiscordTimestamps,
  type DiscordPreviewOptions,
} from '~/components/discord/timestamps';
import { extractApiError } from '~/lib/apiError';
import type { getLogger } from '~/lib/logger';
import type {
  ExternalWriteback,
  ExternalWritebackState,
  PromoUndoResult,
} from './schemas';

export function reportPromoError(
  log: ReturnType<typeof getLogger>,
  event: string,
  err: unknown,
  context: Record<string, unknown>,
): string | undefined {
  const status = (err as { response?: { status?: number } })?.response?.status;
  const message = extractApiError(err);
  const payload = { ...context, status, error: message };
  if (status != null && status >= 400 && status < 500) log.warn(event, payload);
  else log.error(event, payload);
  return message;
}

const EXTERNAL_WRITEBACK_TEXT: Record<ExternalWritebackState, string> = {
  pending: 'Waiting to be recorded externally.',
  in_flight: 'Being recorded externally now.',
  retry:
    'The adaptor could not take it yet; DraftForge will try recording it externally again.',
  paused:
    'External recording is paused. The send is saved in DraftForge and will be recorded once it resumes.',
  reconciliation_required:
    'This send needs review before it can be recorded externally.',
  applied: 'Recorded externally.',
  canceled: 'This send will not be recorded externally.',
};

/**
 * What happened to writing one local send to the external contact log. Only
 * `applied` says the log has it; recording the send in DraftForge never
 * implies that.
 */
export function describeExternalWriteback(
  writeback: ExternalWriteback | null | undefined,
): string | null {
  return writeback?.state ? EXTERNAL_WRITEBACK_TEXT[writeback.state] : null;
}

/** The toast after an undo: it removes the local send, never the receipt. */
export function undoToastDescription(
  result: PromoUndoResult,
  syncConfigured: boolean,
): string | undefined {
  const state = describeExternalWriteback(result.writeback);
  if (!syncConfigured || state == null) return undefined;
  return `Undo removes it from DraftForge only. ${state}`;
}

export function relativeFromIso(
  iso: string,
  opts: DiscordPreviewOptions,
): string {
  const ms = new Date(iso).getTime();
  if (Number.isNaN(ms)) return '';
  return formatDiscordTimestamps(`<t:${Math.floor(ms / 1000)}:R>`, opts);
}
