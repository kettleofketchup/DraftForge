// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import type { PlayerPopoverContext } from '../shared-popover-context';
import { SharedPopoverRenderer } from '../shared-popover-renderer';

const anchorEl = document.createElement('span');
document.body.appendChild(anchorEl);

const popover = vi.hoisted(() => ({
  player: null as unknown as UserType,
  context: undefined as PlayerPopoverContext | undefined,
  openPlayerModal: vi.fn(),
}));

vi.mock('../shared-popover-context', () => ({
  useSharedPopover: () => ({
    openPlayerModal: popover.openPlayerModal,
    scheduleHidePopover: vi.fn(),
    cancelHidePopover: vi.fn(),
    showPlayerPopover: vi.fn(),
    openTeamModal: vi.fn(),
    setPlayerModalOpen: vi.fn(),
    setTeamModalOpen: vi.fn(),
    state: {
      type: 'player',
      isOpen: true,
      player: popover.player,
      team: null,
      anchorEl,
      context: popover.context,
    },
    playerModalState: { player: null, open: false },
    teamModalState: { team: null, open: false },
  }),
}));

vi.mock('~/components/player/PlayerLeagueSummary', () => ({
  PlayerLeagueSummary: () => null,
}));
vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/components/player/PlayerModal', () => ({ PlayerModal: () => null }));
vi.mock('~/components/team/TeamModal', () => ({ TeamModal: () => null }));
vi.mock('~/components/team/TeamPopoverContent', () => ({
  TeamPopoverContent: () => null,
}));

afterEach(() => {
  popover.context = undefined;
  vi.clearAllMocks();
});

describe('player hover card org MMR line', () => {
  it('labels the MMR with the context game', () => {
    popover.player = { pk: 42, username: 'a', mmr: 2500 } as UserType;
    popover.context = { gameType: 2 };
    render(<SharedPopoverRenderer />);
    expect(screen.getByTestId('player-popover-mmr').textContent).toBe(
      'DL 2,500',
    );
  });

  it('falls back to the payload game when the context has none', () => {
    popover.player = {
      pk: 42,
      username: 'a',
      mmr: 4200,
      mmr_game_type: 1,
    } as UserType;
    render(<SharedPopoverRenderer />);
    expect(screen.getByTestId('player-popover-mmr').textContent).toBe(
      'D2 4,200',
    );
  });

  it('forwards the context game to the player modal', () => {
    popover.player = { pk: 42, username: 'a', mmr: 2500 } as UserType;
    popover.context = { gameType: 2 };
    render(<SharedPopoverRenderer />);
    fireEvent.click(screen.getByRole('tooltip'));
    expect(popover.openPlayerModal).toHaveBeenCalledWith(
      popover.player,
      expect.objectContaining({ gameType: 2 }),
    );
  });
});
