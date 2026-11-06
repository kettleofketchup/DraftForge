// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { SharedPopoverRenderer } from '../shared-popover-renderer';

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;
const anchorEl = document.createElement('span');
document.body.appendChild(anchorEl);

const hook = vi.hoisted(() => ({
  openPlayerModal: vi.fn(),
  hidePopover: vi.fn(),
  showPlayerPopover: vi.fn(),
  openTeamModal: vi.fn(),
  setPlayerModalOpen: vi.fn(),
  setTeamModalOpen: vi.fn(),
  showTeamPopover: vi.fn(),
}));

vi.mock('../shared-popover-context', () => ({
  useSharedPopover: () => ({
    ...hook,
    state: {
      type: 'player',
      isOpen: true,
      player,
      team: null,
      anchorEl,
      context: { statsLeagueId: 7 },
    },
    playerModalState: { player: null, open: false },
    teamModalState: { team: null, open: false },
  }),
}));

vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/components/player/PlayerModal', () => ({ PlayerModal: () => null }));
vi.mock('~/components/team/TeamModal', () => ({ TeamModal: () => null }));
vi.mock('~/components/team/TeamPopoverContent', () => ({ TeamPopoverContent: () => null }));

afterEach(() => vi.clearAllMocks());

describe('SharedPopoverRenderer statsLeagueId', () => {
  it('hover card click forwards state.context.statsLeagueId to openPlayerModal', () => {
    render(<SharedPopoverRenderer />);
    fireEvent.click(screen.getByRole('tooltip'));
    expect(hook.openPlayerModal).toHaveBeenCalledWith(
      player,
      expect.objectContaining({ statsLeagueId: 7 }),
    );
    const ctx = hook.openPlayerModal.mock.calls[0][1];
    expect(ctx).toHaveProperty('leagueId');
    expect(ctx).toHaveProperty('organizationId');
  });
});
