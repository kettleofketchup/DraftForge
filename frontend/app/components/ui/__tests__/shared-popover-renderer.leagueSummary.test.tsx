// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { SharedPopoverRenderer } from '../shared-popover-renderer';

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;
const anchorEl = document.createElement('span');
document.body.appendChild(anchorEl);

const popover = vi.hoisted(() => ({ context: undefined as { statsLeagueId?: number | null } | undefined }));

vi.mock('../shared-popover-context', () => ({
  useSharedPopover: () => ({
    openPlayerModal: vi.fn(),
    scheduleHidePopover: vi.fn(),
    cancelHidePopover: vi.fn(),
    showPlayerPopover: vi.fn(),
    openTeamModal: vi.fn(),
    setPlayerModalOpen: vi.fn(),
    setTeamModalOpen: vi.fn(),
    state: {
      type: 'player',
      isOpen: true,
      player,
      team: null,
      anchorEl,
      context: popover.context,
    },
    playerModalState: { player: null, open: false },
    teamModalState: { team: null, open: false },
  }),
}));

vi.mock('~/components/player/PlayerLeagueSummary', () => ({
  PlayerLeagueSummary: (props: { leaguePk: number; userId: number; compact?: boolean }) => (
    <div data-testid="hover-league-summary" data-props={JSON.stringify(props)} />
  ),
}));
vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/components/player/PlayerModal', () => ({ PlayerModal: () => null }));
vi.mock('~/components/team/TeamModal', () => ({ TeamModal: () => null }));
vi.mock('~/components/team/TeamPopoverContent', () => ({ TeamPopoverContent: () => null }));

afterEach(() => {
  popover.context = undefined;
  vi.clearAllMocks();
});

describe('player hover card league summary', () => {
  it('shows the compact league summary when the card has a stats league', () => {
    popover.context = { statsLeagueId: 7 };
    render(<SharedPopoverRenderer />);
    const summary = screen.getByTestId('hover-league-summary');
    expect(JSON.parse(summary.getAttribute('data-props') ?? '{}')).toEqual({
      leaguePk: 7,
      userId: 42,
      compact: true,
    });
  });

  it('shows no league summary without a stats league', () => {
    popover.context = { statsLeagueId: null };
    render(<SharedPopoverRenderer />);
    expect(screen.queryByTestId('hover-league-summary')).toBeNull();
  });
});
