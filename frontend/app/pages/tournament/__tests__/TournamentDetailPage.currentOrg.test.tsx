// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchOrganization } from '~/components/api/api';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import type { OrganizationType } from '~/components/organization/schemas';
import LeaguePage from '~/routes/league';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import TournamentDetailPage from '../TournamentDetailPage';

const ORG_PK = 7;

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchOrganization: vi.fn(),
}));
vi.mock('~/hooks/useTournament', () => ({
  useTournament: () => ({
    data: { pk: 1, name: 'Cup', organization_pk: ORG_PK },
    isLoading: false,
    error: null,
  }),
}));
vi.mock('~/hooks/useTournamentSocket', () => ({
  useTournamentSocket: () => undefined,
}));
vi.mock('../tabs/TournamentTabs', () => ({ default: () => null }));
vi.mock('~/components/league', () => ({
  useLeague: () => ({
    league: { pk: 3, name: 'League', organization: { pk: ORG_PK } },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  LeagueTabs: () => null,
  EditLeagueModal: () => null,
}));
vi.mock('~/hooks/useMemberAccess', () => ({
  useMemberAccess: () => ({ canView: false, settled: false }),
}));
vi.mock('~/hooks/usePageNav', () => ({ usePageNav: () => undefined }));
vi.mock('~/hooks/usePermissions', () => ({
  useIsLeagueAdmin: () => false,
  useIsLeagueStaff: () => false,
}));

const org = (discord_server_id: string | null) =>
  ({ pk: ORG_PK, name: 'Org', discord_server_id }) as OrganizationType;

const storeDiscordId = () =>
  useOrgStore.getState().currentOrg?.discord_server_id;

function renderPage(page: 'tournament' | 'league', queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[
          page === 'tournament' ? '/tournament/1' : '/leagues/3',
        ]}
      >
        <Routes>
          <Route path="tournament/:pk/*" element={<TournamentDetailPage />} />
          <Route path="leagues/:leagueId/:tab?" element={<LeaguePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUserStore.setState({
    tournaments: [],
    getTournaments: vi.fn(async () => {}),
  } as never);
});

afterEach(() => {
  cleanup();
  vi.mocked(fetchOrganization).mockReset();
  useOrgStore.getState().reset();
});

describe.each(['tournament', 'league'] as const)(
  '%s page current org',
  (page) => {
    it('refreshes orgStore.currentOrg when the org query is invalidated', async () => {
      vi.mocked(fetchOrganization).mockResolvedValue(org(null));
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const { unmount } = renderPage(page, queryClient);
      await waitFor(() => expect(storeDiscordId()).toBeNull());

      vi.mocked(fetchOrganization).mockResolvedValue(org('123'));
      await act(() =>
        queryClient.invalidateQueries({
          queryKey: organizationQueryKey(ORG_PK),
        }),
      );
      await waitFor(() => expect(storeDiscordId()).toBe('123'));

      unmount();
      expect(useOrgStore.getState().currentOrg).toBeNull();
    });

    it('refetches instead of reusing a same-pk org left in the store', async () => {
      useOrgStore.getState().setCurrentOrg(org(null));
      vi.mocked(fetchOrganization).mockResolvedValue(org('123'));
      renderPage(page, new QueryClient());
      await waitFor(() => expect(storeDiscordId()).toBe('123'));
    });
  },
);
