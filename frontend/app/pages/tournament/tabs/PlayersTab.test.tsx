// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { PlayersTab } from './PlayersTab';

const captured = vi.hoisted(
  () => [] as Array<{ organizationId?: number; leagueId?: number }>,
);

vi.mock('~/components/user', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  UserList: (props: { organizationId?: number; leagueId?: number }) => {
    captured.push({ organizationId: props.organizationId, leagueId: props.leagueId });
    return null;
  },
}));

window.matchMedia ??= (() => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
})) as unknown as typeof window.matchMedia;

function renderTab() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <PlayersTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PlayersTab org/league context', () => {
  beforeEach(() => {
    captured.length = 0;
    useOrgStore.setState({ currentOrg: { pk: 9, name: 'Stale' } as OrganizationType });
    useLeagueStore.setState({ currentLeague: { pk: 9, name: 'Stale' } as LeagueType });
  });

  it('passes the tournament org/league ids, not the store ones', () => {
    useUserStore.setState({
      tournament: { pk: 1, organization_pk: 8, league_pk: 8, users: [] },
    } as never);
    renderTab();
    expect(captured.length).toBeGreaterThan(0);
    expect(captured.at(-1)).toEqual({ organizationId: 8, leagueId: 8 });
  });

  it('org-less tournament never falls back to a stale store org', () => {
    useUserStore.setState({
      tournament: { pk: 1, organization_pk: null, league_pk: null, users: [] },
    } as never);
    renderTab();
    expect(captured.length).toBeGreaterThan(0);
    expect(captured.at(-1)).toEqual({ organizationId: undefined, leagueId: undefined });
  });
});
