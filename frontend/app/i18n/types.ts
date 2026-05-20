import type navbar from './locales/en/navbar.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'navbar';
    resources: {
      navbar: typeof navbar;
    };
  }
}
