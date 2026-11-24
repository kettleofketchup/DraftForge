import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { extractApiError } from '~/lib/apiError';
import type { getLogger } from '~/lib/logger';
import {
  formatDiscordTimestamps,
  type DiscordPreviewOptions,
} from './discordPreview';
import type {
  PromoUndoResult,
  SfgWriteback,
  SfgWritebackState,
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

const SFG_WRITEBACK_TEXT: Record<SfgWritebackState, string> = {
  pending: 'Waiting to be recorded in SFG.',
  in_flight: 'Being recorded in SFG now.',
  retry:
    'SFG could not take it yet; DraftForge will try recording it in SFG again.',
  paused:
    'SFG recording is paused. The send is saved in DraftForge and will be recorded once it resumes.',
  reconciliation_required:
    'This send needs review before it can be recorded in SFG.',
  applied: 'Recorded in SFG.',
  canceled: 'This send will not be recorded in SFG.',
};

/**
 * What happened to writing one local send to SFG. Only `applied` says SFG has
 * it; recording the send in DraftForge never implies that.
 */
export function describeSfgWriteback(
  writeback: SfgWriteback | null | undefined,
): string | null {
  return writeback?.state ? SFG_WRITEBACK_TEXT[writeback.state] : null;
}

/** The toast after an undo: undo removes the local send, never the SFG receipt. */
export function undoToastDescription(
  result: PromoUndoResult,
  syncConfigured: boolean,
): string | undefined {
  const state = describeSfgWriteback(result.sfg_writeback);
  if (!syncConfigured || state == null) return undefined;
  return `Undo removes it from DraftForge only. ${state}`;
}

export function usePreviewOptions(): DiscordPreviewOptions {
  const { i18n } = useTranslation();
  const locale = i18n?.resolvedLanguage ?? 'en';
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return useMemo(() => ({ locale, timeZone }), [locale, timeZone]);
}

export function relativeFromIso(
  iso: string,
  opts: DiscordPreviewOptions,
): string {
  const ms = new Date(iso).getTime();
  if (Number.isNaN(ms)) return '';
  return formatDiscordTimestamps(`<t:${Math.floor(ms / 1000)}:R>`, opts);
}
