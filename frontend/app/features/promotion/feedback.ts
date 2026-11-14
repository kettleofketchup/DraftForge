import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { extractApiError } from '~/lib/apiError';
import type { getLogger } from '~/lib/logger';
import {
  formatDiscordTimestamps,
  type DiscordPreviewOptions,
} from './discordPreview';

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
