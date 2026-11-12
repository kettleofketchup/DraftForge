import { createInstance, type i18n as I18nInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

import enLobby from './locales/en/lobby.json';
import enNavbar from './locales/en/navbar.json';
import esLobby from './locales/es/lobby.json';
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
    ns: ['navbar', 'lobby'],
    defaultNS: 'navbar',
    resources: {
      en: { navbar: enNavbar, lobby: enLobby },
      es: { navbar: esNavbar, lobby: esLobby },
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });
  return instance;
}
