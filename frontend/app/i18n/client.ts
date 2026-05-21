import { createI18nInstance, FALLBACK_LOCALE, SUPPORTED_LOCALES, type SupportedLocale } from './config';

function isSupported(value: string): value is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

function readCookie(name: string): string | undefined {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

function writeCookie(name: string, value: string): void {
  const oneYear = 60 * 60 * 24 * 365;
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${oneYear}; SameSite=Lax${secure}`;
}

function resolveLocale(): SupportedLocale {
  if (typeof document === 'undefined') return FALLBACK_LOCALE;
  const htmlLang = document.documentElement.lang;
  if (htmlLang && isSupported(htmlLang)) return htmlLang;
  const params = new URLSearchParams(location.search);
  const queryLocale = params.get('lang');
  if (queryLocale && isSupported(queryLocale)) {
    if (readCookie('df-locale') !== queryLocale) {
      writeCookie('df-locale', queryLocale);
    }
    return queryLocale;
  }
  const cookieLocale = readCookie('df-locale');
  if (cookieLocale && isSupported(cookieLocale)) return cookieLocale;
  return FALLBACK_LOCALE;
}

export const i18n = createI18nInstance(resolveLocale());
