// @vitest-environment jsdom
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import type { LeagueType } from '~/components/league/schemas';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';

const captured = vi.hoisted(
  () => [] as Array<{ organizationId?: number; leagueId?: number }>,
);
const { getLeagueUsers } = vi.hoisted(() => ({ getLeagueUsers: vi.fn() }));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  getLeagueUsers,
  fetchLeague: vi.fn(),
}));

vi.mock('~/components/user', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  UserList: (props: { organizationId?: number; leagueId?: number }) => {
    captured.push({
      organizationId: props.organizationId,
      leagueId: props.leagueId,
    });
    return null;
  },
}));

const { UsersTab } = await import('./UsersTab');

const LEAGUE_PK = 3;
const ORG_PK = 8;

function renderTab() {
  window.history.pushState({}, '', `/leagues/${LEAGUE_PK}/users`);
  return render(
    <MemoryRouter initialEntries={[`/leagues/${LEAGUE_PK}/users`]}>
      <UsersTab leaguePk={LEAGUE_PK} />
    </MemoryRouter>,
  );
}

describe('UsersTab org/league context', () => {
  beforeEach(() => {
    captured.length = 0;
    useLeagueStore.getState().reset();
    useOrgStore.setState({ currentOrg: null });
    useUserCacheStore.getState().reset();
    useLeagueStore.setState({
      currentLeague: {
        pk: LEAGUE_PK,
        name: 'League',
        organization: { pk: ORG_PK, name: 'Org' },
      } as LeagueType,
    });
    getLeagueUsers.mockResolvedValue([
      {
        id: 50,
        pk: 1,
        username: 'event_player_1',
        mmr: 4800,
        orgUserPk: 11,
        game_mmrs: { '1': 5100, '2': 0 },
        league_mmr: 4800,
      },
    ]);
  });

  it('passes the league org and league ids to the user cards', async () => {
    renderTab();
    await waitFor(() => expect(captured.length).toBeGreaterThan(0));
    expect(captured.at(-1)).toEqual({
      organizationId: ORG_PK,
      leagueId: LEAGUE_PK,
    });
  });

  it('caches the org and league MMR from a fresh league users load', async () => {
    renderTab();
    await waitFor(() => expect(getLeagueUsers).toHaveBeenCalledWith(LEAGUE_PK));
    await waitFor(() => {
      const entry = useUserCacheStore.getState().getById(1);
      expect(entry?.orgData[ORG_PK]?.mmrs[GAME_TYPE.DOTA2]).toBe(5100);
      expect(entry?.leagueData[LEAGUE_PK]?.mmr).toBe(4800);
    });
  });
});
