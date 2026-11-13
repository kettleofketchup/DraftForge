import type { Cookie } from 'react-router';
import { RemixI18Next } from 'remix-i18next/server';

import { FALLBACK_LOCALE, SUPPORTED_LOCALES, type SupportedLocale } from './config';
import { LOCALE_COOKIE_NAME, readLocaleCookie, serializeLocaleCookie } from './localeCookie';

// Not createCookie: it base64-encodes JSON, which the client and nginx would have to decode.
export const localeCookie: Cookie = {
  name: LOCALE_COOKIE_NAME,
  isSigned: false,
  expires: undefined,
  async parse(cookieHeader: string | null): Promise<SupportedLocale | null> {
    return readLocaleCookie(cookieHeader).locale ?? null;
  },
  async serialize(value: SupportedLocale): Promise<string> {
    return serializeLocaleCookie(value, process.env.NODE_ENV === 'production');
  },
};

export const i18nServer = new RemixI18Next({
  detection: {
    supportedLanguages: [...SUPPORTED_LOCALES],
    fallbackLanguage: FALLBACK_LOCALE,
    order: ['searchParams', 'cookie', 'header'],
    searchParamKey: 'lang',
    cookie: localeCookie,
  },
});

export async function resolveRequestLocale(
  request: Request,
): Promise<{ locale: SupportedLocale; setCookie: string | null }> {
  const locale = (await i18nServer.getLocale(request)) as SupportedLocale;
  const existing = readLocaleCookie(request.headers.get('Cookie'));
  if (existing.locale === locale && !existing.needsRewrite) return { locale, setCookie: null };
  return { locale, setCookie: await localeCookie.serialize(locale) };
}
