// @vitest-environment jsdom
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useLeagueStore } from '~/store/leagueStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

import {
  currentDisplayOrgId,
  notifyDisplayOrgRoute,
  setDisplayOrgQueryClient,
} from './displayOrg';

let qc: QueryClient;
const goTo = (path: string) => window.history.pushState({}, '', path);

beforeEach(() => {
  qc = new QueryClient();
  setDisplayOrgQueryClient(qc);
  useUserStore.setState({ tournament: null as never });
  useHeroDraftStore.setState({ draft: null });
  useLeagueStore.setState({ currentLeague: null });
  useUserCacheStore.getState().reset();
});
afterEach(() => {
  setDisplayOrgQueryClient(null);
  goTo('/');
});

describe('currentDisplayOrgId', () => {
  it('is null outside org pages', () => {
    goTo('/users');
    expect(currentDisplayOrgId()).toBeNull();
    goTo('/');
    expect(currentDisplayOrgId()).toBeNull();
  });

  it('reads the organization page id from the URL', () => {
    goTo('/organizations/4');
    expect(currentDisplayOrgId()).toBe(4);
  });

  it('tournament: null until loaded, then its organization_pk', () => {
    goTo('/tournament/5/bracket');
    expect(currentDisplayOrgId()).toBeNull();
    qc.setQueryData(['tournament', 5], { pk: 5, organization_pk: 7 });
    expect(currentDisplayOrgId()).toBe(7);
  });

  it('tournament falls back to the loaded userStore tournament with the same pk', () => {
    goTo('/tournament/5');
    useUserStore.setState({
      tournament: { pk: 6, organization_pk: 9 } as never,
    });
    expect(currentDisplayOrgId()).toBeNull();
    useUserStore.setState({
      tournament: { pk: 5, organization_pk: 9 } as never,
    });
    expect(currentDisplayOrgId()).toBe(9);
  });

  it('league: the current league when it is the routed one', () => {
    goTo('/leagues/3/users');
    useLeagueStore.setState({
      currentLeague: { pk: 2, organization: { pk: 8 } } as never,
    });
    expect(currentDisplayOrgId()).toBeNull();
    useLeagueStore.setState({
      currentLeague: { pk: 3, organization: { pk: 8 } } as never,
    });
    expect(currentDisplayOrgId()).toBe(8);
    useLeagueStore.setState({
      currentLeague: { pk: 3, organization: null, organization_id: 6 } as never,
    });
    expect(currentDisplayOrgId()).toBe(6);
  });

  it('event and roll call: the queried event organization', () => {
    qc.setQueryData(['event', 11], { id: 11, organization: 12 });
    goTo('/events/11/signups');
    expect(currentDisplayOrgId()).toBe(12);
    goTo('/rollcall/11');
    expect(currentDisplayOrgId()).toBe(12);
    goTo('/events/99');
    expect(currentDisplayOrgId()).toBeNull();
  });

  it('hero draft: the loaded draft organization_pk for the routed id', () => {
    goTo('/herodraft/2');
    useHeroDraftStore.setState({
      draft: { id: 3, organization_pk: 5 } as never,
    });
    expect(currentDisplayOrgId()).toBeNull();
    useHeroDraftStore.setState({
      draft: { id: 2, organization_pk: 5 } as never,
    });
    expect(currentDisplayOrgId()).toBe(5);
  });

  it('activity: the activity tournament, else the hero draft', () => {
    goTo('/activity');
    useHeroDraftStore.setState({
      draft: { id: 2, organization_pk: 5 } as never,
    });
    expect(currentDisplayOrgId()).toBe(5);
    useUserStore.setState({
      tournament: { pk: 1, organization_pk: 4 } as never,
    });
    expect(currentDisplayOrgId()).toBe(4);
  });
});

describe('names follow the page org', () => {
  let mounts = 0;

  function TournamentPage() {
    const { data } = useQuery({
      queryKey: ['tournament', 5],
      queryFn: () => new Promise<never>(() => {}),
      enabled: false,
    });
    useEffect(() => {
      mounts += 1;
    }, []);
    return (
      <div>
        <span data-testid="name">{data ? DisplayName({ pk: 1 }) : '…'}</span>
        <UserAvatar user={{ pk: 1 }} />
      </div>
    );
  }

  beforeEach(() => {
    mounts = 0;
    useUserCacheStore.getState().upsert(
      {
        pk: 1,
        username: 'u',
        discordNickname: 'Glob',
        guildNickname: 'Srv',
      } as never,
      { orgId: 7 },
    );
  });

  it('uses the org on the first render with data, without remounting', async () => {
    goTo('/tournament/5');
    render(
      <QueryClientProvider client={qc}>
        <TournamentPage />
      </QueryClientProvider>,
    );
    expect(screen.getByText('G')).toBeInTheDocument();
    await act(async () => {
      qc.setQueryData(['tournament', 5], { pk: 5, organization_pk: 7 });
    });
    expect(await screen.findByText('Srv')).toBeInTheDocument();
    expect(screen.getByText('S')).toBeInTheDocument();
    expect(mounts).toBe(1);
  });

  it('a navigation to a non-org route clears the org for subscribers', () => {
    qc.setQueryData(['tournament', 5], { pk: 5, organization_pk: 7 });
    goTo('/tournament/5');
    render(
      <QueryClientProvider client={qc}>
        <UserAvatar user={{ pk: 1 }} />
      </QueryClientProvider>,
    );
    expect(screen.getByText('S')).toBeInTheDocument();
    act(() => {
      goTo('/users');
      notifyDisplayOrgRoute();
    });
    expect(screen.getByText('G')).toBeInTheDocument();
  });
});
