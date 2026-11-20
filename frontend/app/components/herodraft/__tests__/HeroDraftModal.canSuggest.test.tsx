// @vitest-environment jsdom
import { render } from '@testing-library/react';
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
import type { ChatViewer, HeroDraft } from '~/components/herodraft/types';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { TooltipProvider } from '~/components/ui/tooltip';
import { useHeroDraftStore } from '~/store/heroDraftStore';

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

const viewer = (role: ChatViewer['role']): ChatViewer => ({
  role,
  team_id: role === 'member' ? 1 : null,
  can_post_team: role === 'member',
  can_post_all: role === 'member',
});

const original = useHeroDraftStore.getState();
afterEach(() => {
  useHeroDraftStore.setState(original, true);
  gridProps.mockClear();
});

function canSuggestFor(
  role: ChatViewer['role'] | null,
  state: HeroDraft['state'] = 'drafting',
): boolean | undefined {
  useHeroDraftStore.setState({
    connect: vi.fn(),
    disconnect: vi.fn(),
    startHeartbeat: vi.fn(),
    status: 'connected',
    draft: draftIn(state),
    chat: { ...initialChatState, viewer: role ? viewer(role) : null },
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
  expect(gridProps).toHaveBeenCalled();
  return gridProps.mock.calls.at(-1)?.[0];
}

describe('HeroDraftModal suggest menu gating', () => {
  it('lets a team member suggest while drafting', () => {
    expect(canSuggestFor('member')).toBe(true);
  });

  it.each(['spectator', 'ambiguous'] as const)(
    'gives a %s no suggest menu',
    (role) => {
      expect(canSuggestFor(role)).toBe(false);
    },
  );

  it('gives no suggest menu before the chat viewer is known', () => {
    expect(canSuggestFor(null)).toBe(false);
  });

  it('gives a member no suggest menu while paused', () => {
    expect(canSuggestFor('member', 'paused')).toBe(false);
  });
});
