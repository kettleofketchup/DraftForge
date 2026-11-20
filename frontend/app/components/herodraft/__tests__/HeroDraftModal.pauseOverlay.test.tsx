// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => vi.fn(),
}));

const gridProps = vi.fn();
vi.mock('~/components/herodraft/HeroGrid', () => ({
  HeroGrid: (props: { canSuggest?: boolean }) => {
    gridProps(props.canSuggest);
    return null;
  },
}));

import { initialChatState } from '~/components/herodraft/chat/chatState';
import { HeroDraftModal } from '~/components/herodraft/HeroDraftModal';
import type { HeroDraft } from '~/components/herodraft/types';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { TooltipProvider } from '~/components/ui/tooltip';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserStore } from '~/store/userStore';

const team = (id: number, isFirst: boolean) => ({
  id,
  tournament_team: 30 + id,
  captain: { pk: id, username: `c${id}`, nickname: null, avatar: null },
  team_name: `Team ${id}`,
  members: [],
  is_first_pick: isFirst,
  is_radiant: null,
  reserve_time_remaining: 5_000,
  is_ready: true,
  is_connected: true,
});

function draftIn(state: HeroDraft['state']): HeroDraft {
  return {
    id: 7,
    game: 99,
    tournament_id: 8,
    state,
    roll_winner: null,
    timer_enabled: true,
    draft_teams: [team(1, true), team(2, false)],
    rounds: [],
    current_round: 0,
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
  } as unknown as HeroDraft;
}

const original = useHeroDraftStore.getState();
const originalUser = useUserStore.getState().currentUser;
afterEach(() => {
  useHeroDraftStore.setState(original, true);
  useUserStore.setState({ currentUser: originalUser });
});

function renderAsCaptain(lastEvent: unknown = null): void {
  useUserStore.setState({
    currentUser: { ...originalUser, pk: 1 } as typeof originalUser,
  });
  useHeroDraftStore.setState({
    connect: vi.fn(),
    disconnect: vi.fn(),
    startHeartbeat: vi.fn(),
    status: 'connected',
    draft: draftIn('drafting'),
    chat: initialChatState,
    lastEvent: lastEvent as never,
  });
  render(
    <MemoryRouter>
      <TooltipProvider>
        <SharedPopoverProvider>
          <HeroDraftModal draftId={7} open onClose={() => {}} />
        </SharedPopoverProvider>
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe('HeroDraftModal pause button', () => {
  it('shows Pause to a captain while drafting', () => {
    renderAsCaptain();
    expect(screen.queryByTestId('herodraft-paused-overlay')).toBeNull();
    expect(screen.getByTestId('herodraft-pause-btn')).toBeTruthy();
  });

  it('hides Pause while the resume countdown overlay shows', () => {
    renderAsCaptain({
      event_type: 'resume_countdown',
      metadata: { countdown_seconds: 3 },
    });
    expect(screen.getByTestId('herodraft-paused-overlay')).toBeTruthy();
    expect(screen.queryByTestId('herodraft-pause-btn')).toBeNull();
  });
});
