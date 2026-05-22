import { createInstance, type i18n as I18nInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

import enNavbar from './locales/en/navbar.json';
import esNavbar from './locales/es/navbar.json';

export const SUPPORTED_LOCALES = ['en', 'es'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
export const FALLBACK_LOCALE: SupportedLocale = 'en';

export function createI18nInstance(locale: string): I18nInstance {
  const instance = createInstance();
  instance.use(initReactI18next).init({
    lng: locale,
    fallbackLng: FALLBACK_LOCALE,
    supportedLngs: [...SUPPORTED_LOCALES],
    ns: ['navbar'],
    defaultNS: 'navbar',
    resources: {
      en: { navbar: enNavbar },
      es: { navbar: esNavbar },
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });
  return instance;
}
