// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getEvents: vi.fn(async () => []),
  getEventRepeaters: vi.fn(async () => []),
}));

vi.mock('~/root', () => ({ queryClient: {} }));
vi.mock('~/components/league', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/league')>()),
  useLeagues: () => ({ leagues: [], isLoading: false }),
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import OrganizationDetailPage from '../organization';

afterEach(cleanup);

describe('OrganizationDetailPage events queries', () => {
  it('does not list events or series without an organization id', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/organizations/not-a-number']}>
          <Routes>
            <Route
              path="organizations/:organizationId"
              element={<OrganizationDetailPage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(api.getEvents).not.toHaveBeenCalled();
    expect(api.getEventRepeaters).not.toHaveBeenCalled();
  });
});
