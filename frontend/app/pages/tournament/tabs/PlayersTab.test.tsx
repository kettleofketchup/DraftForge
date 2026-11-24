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
const steamFlags = vi.hoisted(() => [] as Array<boolean | undefined>);

vi.mock('~/components/user', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  UserList: (props: {
    organizationId?: number;
    leagueId?: number;
    showSteamVerification?: boolean;
  }) => {
    steamFlags.push(props.showSteamVerification);
    captured.push({
      organizationId: props.organizationId,
      leagueId: props.leagueId,
    });
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
    steamFlags.length = 0;
    useOrgStore.setState({
      currentOrg: { pk: 9, name: 'Stale' } as OrganizationType,
    });
    useLeagueStore.setState({
      currentLeague: { pk: 9, name: 'Stale' } as LeagueType,
    });
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
    expect(captured.at(-1)).toEqual({
      organizationId: undefined,
      leagueId: undefined,
    });
  });

  it('badges Friend IDs only for staff viewers', () => {
    const tournament = {
      pk: 1,
      organization_pk: null,
      league_pk: null,
      users: [],
    };
    useUserStore.setState({
      tournament,
      currentUser: { pk: 1, username: 'member' },
    } as never);
    renderTab();
    expect(steamFlags.at(-1)).toBe(false);

    steamFlags.length = 0;
    useUserStore.setState({
      tournament,
      currentUser: { pk: 1, username: 'staff', is_staff: true },
    } as never);
    renderTab();
    expect(steamFlags.at(-1)).toBe(true);
  });
});

describe('PlayersTab add-player controls', () => {
  beforeEach(() => {
    useOrgStore.setState({ currentOrg: null });
    useLeagueStore.setState({
      currentLeague: {
        pk: 8,
        name: 'League',
        organization: { pk: 5, name: 'Org' },
      } as LeagueType,
    });
    useUserStore.setState({
      tournament: { pk: 1, organization_pk: 5, league_pk: 8, users: [] },
    } as never);
  });

  it('shows Add Player to staff of the league org', () => {
    useUserStore.setState({
      currentUser: { pk: 2, username: 'staff', staff_organization_ids: [5] },
    } as never);
    const { queryByTestId } = renderTab();
    expect(queryByTestId('tournamentAddPlayerBtn')).not.toBeNull();
  });

  it('hides Add Player from staff of another org', () => {
    useUserStore.setState({
      currentUser: { pk: 2, username: 'other', staff_organization_ids: [6] },
    } as never);
    const { queryByTestId } = renderTab();
    expect(queryByTestId('tournamentAddPlayerBtn')).toBeNull();
  });
});
