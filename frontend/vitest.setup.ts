import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import type { UserType } from '~/index';

// userStore fetches /current_user when it hydrates on import; answer as an anonymous visitor.
vi.mock('~/components/api/userAPI', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/userAPI')>()),
  fetchCurrentUser: vi.fn(async () => ({}) as UserType),
}));

afterEach(() => {
  cleanup();
});
