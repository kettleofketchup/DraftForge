import type { UserConfig } from 'i18next-parser';

const config: UserConfig = {
  locales: ['en', 'es'],
  input: ['app/components/navbar/**/*.{ts,tsx}'],
  output: 'app/i18n/locales/$LOCALE/$NAMESPACE.json',
  defaultNamespace: 'navbar',
  keySeparator: '.',
  namespaceSeparator: false,
  createOldCatalogs: false,
  sort: true,
  keepRemoved: false,
};

export default config;
