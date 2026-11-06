// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { UserType } from '~/components/user/types';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { PlayerPopoverTrigger } from '../PlayerPopoverTrigger';

const actions = vi.hoisted(() => ({
  showPlayerPopover: vi.fn(),
  hidePopover: vi.fn(),
  openPlayerModal: vi.fn(),
  openTeamModal: vi.fn(),
}));

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => actions,
}));

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;

function trigger() {
  return screen.getByRole('button', { name: 'View profile for Alice' });
}

beforeEach(() => {
  vi.clearAllMocks();
  useLeagueStore.setState({ currentLeague: { pk: 3 } as LeagueType });
  useOrgStore.setState({ currentOrg: { pk: 9 } as never });
});

afterEach(() => {
  useLeagueStore.setState({ currentLeague: null });
  useOrgStore.setState({ currentOrg: null });
});

describe('PlayerPopoverTrigger statsLeagueId', () => {
  it('click passes statsLeagueId to openPlayerModal', () => {
    render(
      <PlayerPopoverTrigger player={player} statsLeagueId={7}>
        x
      </PlayerPopoverTrigger>,
    );
    fireEvent.click(trigger());
    expect(actions.openPlayerModal).toHaveBeenCalledWith(
      player,
      expect.objectContaining({ statsLeagueId: 7, leagueId: 3, organizationId: 9 }),
    );
  });

  it('Enter key passes statsLeagueId to openPlayerModal', () => {
    render(
      <PlayerPopoverTrigger player={player} statsLeagueId={7}>
        x
      </PlayerPopoverTrigger>,
    );
    fireEvent.keyDown(trigger(), { key: 'Enter' });
    expect(actions.openPlayerModal).toHaveBeenCalledWith(
      player,
      expect.objectContaining({ statsLeagueId: 7 }),
    );
  });

  it('mouseenter passes statsLeagueId to showPlayerPopover', () => {
    render(
      <PlayerPopoverTrigger player={player} statsLeagueId={7}>
        x
      </PlayerPopoverTrigger>,
    );
    fireEvent.mouseEnter(trigger());
    expect(actions.showPlayerPopover).toHaveBeenCalledWith(player, trigger(), {
      statsLeagueId: 7,
    });
  });

  it('without the prop keeps leagueId/organizationId and no statsLeagueId', () => {
    render(<PlayerPopoverTrigger player={player}>x</PlayerPopoverTrigger>);
    fireEvent.click(trigger());
    const ctx = actions.openPlayerModal.mock.calls[0][1];
    expect(ctx).toMatchObject({ leagueId: 3, organizationId: 9 });
    expect(ctx.statsLeagueId).toBeUndefined();
  });
});
