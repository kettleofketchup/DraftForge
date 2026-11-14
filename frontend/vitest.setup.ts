import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { setI18n } from 'react-i18next';
import { afterEach, vi } from 'vitest';

import { createI18nInstance, FALLBACK_LOCALE } from '~/i18n/config';
import type { UserType } from '~/index';

// Components rendered without an I18nextProvider fall back to this instance.
setI18n(createI18nInstance(FALLBACK_LOCALE));

// userStore fetches /current_user when it hydrates on import; answer as an anonymous visitor.
vi.mock('~/components/api/userAPI', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/userAPI')>()),
  fetchCurrentUser: vi.fn(async () => ({}) as UserType),
}));

afterEach(() => {
  cleanup();
});
