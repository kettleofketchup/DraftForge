// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { UserStrip } from '../UserStrip';

const actions = vi.hoisted(() => ({
  showPlayerPopover: vi.fn(),
  hidePopover: vi.fn(),
  openPlayerModal: vi.fn(),
  openTeamModal: vi.fn(),
}));

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => actions,
}));

vi.mock('~/features/league-stats/queries', () => ({
  usePlayerLeagueSummary: () => ({ data: undefined, isLoading: false, isError: false }),
}));

const user = { pk: 42, username: 'alice', nickname: 'Alice', mmr: 4200 } as UserType;

function wrap(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('UserStrip popover statsLeagueId', () => {
  it.each([0, 1])('trigger %i (avatar, name) opens the modal with statsLeagueId', (idx) => {
    render(wrap(<UserStrip user={user} statsLeagueId={7} />));
    const triggers = screen.getAllByRole('button', { name: 'View profile for Alice' });
    expect(triggers).toHaveLength(2);
    fireEvent.click(triggers[idx]);
    expect(actions.openPlayerModal).toHaveBeenCalledWith(
      user,
      expect.objectContaining({ statsLeagueId: 7 }),
    );
  });
});
