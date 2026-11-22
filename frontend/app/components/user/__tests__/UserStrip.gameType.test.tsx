// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import type { UserEntry } from '~/store/userCacheTypes';
import { resetGameType, withGameType } from '~/test-utils/gameType';
import { UserStrip, userStripPropsAreEqual } from '../UserStrip';

afterEach(resetGameType);

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

vi.mock('~/features/league-stats/queries', () => ({
  usePlayerLeagueSummary: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
}));

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const entry: UserEntry = {
  pk: 43,
  username: 'bob',
  discordNickname: 'Bob',
  orgData: { 5: { id: 1, mmrs: { 1: 3000, 2: 2500 }, _fetchedAt: 0 } },
  leagueData: {},
  _fetchedAt: 0,
};

function wrap(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
}

function orgBadge(): HTMLElement {
  const badge = screen.getByTestId('user-strip-org-mmr');
  return badge;
}

describe('UserStrip page game', () => {
  it('Deadlock shows the DL prefix and the Deadlock value', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    render(wrap(<UserStrip user={entry} organizationId={5} />));
    const text = orgBadge().textContent ?? '';
    expect(text).toContain('DL:');
    expect(text).toContain('2,500');
    expect(text).not.toContain('3,000');
  });

  it('Dota keeps the B: prefix and shows the Dota value', () => {
    withGameType(GAME_TYPE.DOTA2);
    render(wrap(<UserStrip user={entry} organizationId={5} />));
    const text = orgBadge().textContent ?? '';
    expect(text).toContain('B:');
    expect(text).toContain('3,000');
  });

  it('server-resolved UserType mmr is labelled with the page game', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    const user = { pk: 1, username: 'a', mmr: 1800 } as UserType;
    render(wrap(<UserStrip user={user} />));
    expect(orgBadge().textContent).toContain('DL:');
  });

  it('tooltip names the game org MMR', async () => {
    withGameType(GAME_TYPE.DEADLOCK);
    render(wrap(<UserStrip user={entry} organizationId={5} />));
    await act(async () => {
      fireEvent.focus(orgBadge());
    });
    expect(
      (await screen.findAllByText('Deadlock org MMR')).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText('Dota 2 ranked MMR')).toBeNull();
  });

  it('Deadlock hides the Dota-seeded league MMR badge', () => {
    const user: UserEntry = {
      ...entry,
      leagueData: { 9: { id: 1, mmr: 2000, _fetchedAt: 0 } },
    };
    withGameType(GAME_TYPE.DEADLOCK);
    render(wrap(<UserStrip user={user} organizationId={5} leagueId={9} />));
    expect(screen.queryByText('L:')).toBeNull();
    expect(orgBadge().textContent).toContain('DL:');
  });

  it('Dota still shows the league MMR badge', () => {
    const user: UserEntry = {
      ...entry,
      leagueData: { 9: { id: 1, mmr: 2000, _fetchedAt: 0 } },
    };
    withGameType(GAME_TYPE.DOTA2);
    render(wrap(<UserStrip user={user} organizationId={5} leagueId={9} />));
    expect(screen.getByText('L:').parentElement?.textContent).toContain(
      '2,000',
    );
  });

  it('Deadlock hides a raw-payload league_mmr too', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    const user = { pk: 1, username: 'a', league_mmr: 2000 } as UserType;
    render(wrap(<UserStrip user={user} />));
    expect(screen.queryByText('L:')).toBeNull();
  });

  it('falls back to Dota outside any game context', () => {
    render(wrap(<UserStrip user={entry} organizationId={5} />));
    const text = orgBadge().textContent ?? '';
    expect(text).toContain('B:');
    expect(text).toContain('3,000');
  });

  it('an explicit gameType overrides the page game', () => {
    withGameType(GAME_TYPE.DOTA2);
    render(
      wrap(
        <UserStrip
          user={entry}
          organizationId={5}
          gameType={GAME_TYPE.DEADLOCK}
        />,
      ),
    );
    expect(orgBadge().textContent).toContain('DL:');
  });

  it('follows the page game when it changes', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    render(wrap(<UserStrip user={entry} organizationId={5} />));
    expect(orgBadge().textContent).toContain('DL:');
    act(() => withGameType(GAME_TYPE.DOTA2));
    expect(orgBadge().textContent).toContain('B:');
  });

  it('comparator returns false when the gameType override changes', () => {
    expect(
      userStripPropsAreEqual(
        { user: entry, gameType: GAME_TYPE.DOTA2 },
        { user: entry, gameType: GAME_TYPE.DEADLOCK },
      ),
    ).toBe(false);
  });
});
