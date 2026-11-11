import type lobby from './locales/en/lobby.json';
import type navbar from './locales/en/navbar.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'navbar';
    resources: {
      navbar: typeof navbar;
      lobby: typeof lobby;
    };
  }
}
