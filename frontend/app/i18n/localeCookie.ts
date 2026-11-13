import { readCookie } from '~/lib/cookies';

import { SUPPORTED_LOCALES, type SupportedLocale } from './config';

export const LOCALE_COOKIE_NAME = 'df-locale';
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

// Before the plain format, React Router's createCookie wrote base64 JSON ("es" -> ImVzIg==).
function decodeLegacy(value: string): string | undefined {
  try {
    const decoded: unknown = JSON.parse(atob(value));
    return typeof decoded === 'string' ? decoded : undefined;
  } catch {
    return undefined;
  }
}

export function decodeLocaleCookieValue(value: string | undefined): SupportedLocale | undefined {
  if (!value) return undefined;
  if (isSupportedLocale(value)) return value;
  const legacy = decodeLegacy(value);
  return isSupportedLocale(legacy) ? legacy : undefined;
}

export function readLocaleCookie(cookieHeader: string | null | undefined): {
  locale: SupportedLocale | undefined;
  needsRewrite: boolean;
} {
  const raw = readCookie(cookieHeader ?? '', LOCALE_COOKIE_NAME);
  const locale = decodeLocaleCookieValue(raw);
  return { locale, needsRewrite: locale !== undefined && raw !== locale };
}

export function serializeLocaleCookie(locale: SupportedLocale, secure: boolean): string {
  const secureAttr = secure ? '; Secure' : '';
  return `${LOCALE_COOKIE_NAME}=${locale}; Path=/; Max-Age=${LOCALE_COOKIE_MAX_AGE}; SameSite=Lax${secureAttr}`;
}
