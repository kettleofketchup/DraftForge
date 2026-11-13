import { createI18nInstance, FALLBACK_LOCALE, type SupportedLocale } from './config';
import { isSupportedLocale, readLocaleCookie, serializeLocaleCookie } from './localeCookie';

function writeLocaleCookie(locale: SupportedLocale): void {
  document.cookie = serializeLocaleCookie(locale, location.protocol === 'https:');
}

export function resolveLocale(): SupportedLocale {
  if (typeof document === 'undefined') return FALLBACK_LOCALE;
  const stored = readLocaleCookie(document.cookie);
  const queryLocale = new URLSearchParams(location.search).get('lang');
  if (isSupportedLocale(queryLocale)) {
    if (stored.locale !== queryLocale || stored.needsRewrite) writeLocaleCookie(queryLocale);
  } else if (stored.locale && stored.needsRewrite) {
    writeLocaleCookie(stored.locale);
  }
  const htmlLang = document.documentElement.lang;
  if (isSupportedLocale(htmlLang)) return htmlLang;
  if (isSupportedLocale(queryLocale)) return queryLocale;
  return stored.locale ?? FALLBACK_LOCALE;
}

export const i18n = createI18nInstance(resolveLocale());
