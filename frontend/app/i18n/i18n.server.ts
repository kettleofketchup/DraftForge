import { createCookie } from 'react-router';
import { RemixI18Next } from 'remix-i18next/server';

import { FALLBACK_LOCALE, SUPPORTED_LOCALES } from './config';

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export const localeCookie = createCookie('df-locale', {
  sameSite: 'lax',
  path: '/',
  maxAge: ONE_YEAR_SECONDS,
  secure: process.env.NODE_ENV === 'production',
});

export const i18nServer = new RemixI18Next({
  detection: {
    supportedLanguages: [...SUPPORTED_LOCALES],
    fallbackLanguage: FALLBACK_LOCALE,
    order: ['searchParams', 'cookie', 'header'],
    searchParamKey: 'lang',
    cookie: localeCookie,
  },
});
