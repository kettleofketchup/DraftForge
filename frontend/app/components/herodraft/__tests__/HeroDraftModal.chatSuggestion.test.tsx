// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
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

vi.mock('~/components/herodraft/HeroGrid', () => ({ HeroGrid: () => null }));
vi.mock('~/components/herodraft/DraftPanel', () => ({
  DraftPanel: () => null,
}));

let suggestionClick: ((heroId: number) => void) | undefined;
vi.mock('~/components/herodraft/chat/HeroDraftChat', () => ({
  HeroDraftChat: (props: { onSuggestionClick?: (heroId: number) => void }) => {
    suggestionClick = props.onSuggestionClick;
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
  members: [{ pk: id * 10, username: `m${id}`, nickname: null, avatar: null }],
  is_first_pick: isFirst,
  is_radiant: null,
  reserve_time_remaining: 5_000,
  is_ready: true,
  is_connected: true,
});

const round = (n: number, heroId: number | null) => ({
  id: 100 + n,
  draft_team: 1,
  round_number: n,
  action_type: 'ban',
  hero_id: heroId,
  state: heroId === null ? 'active' : 'completed',
  started_at: null,
  completed_at: null,
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
    rounds: [round(1, 5), round(2, null)],
    current_round: 1,
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
  } as unknown as HeroDraft;
}

const originalDraft = useHeroDraftStore.getState();
const originalUser = useUserStore.getState();
afterEach(() => {
  useHeroDraftStore.setState(originalDraft, true);
  useUserStore.setState(originalUser, true);
  suggestionClick = undefined;
});

function renderAs(userPk: number, state: HeroDraft['state'] = 'drafting') {
  useUserStore.setState({
    currentUser: { pk: userPk, username: `u${userPk}` } as never,
  });
  useHeroDraftStore.setState({
    connect: vi.fn(),
    disconnect: vi.fn(),
    startHeartbeat: vi.fn(),
    status: 'connected',
    draft: draftIn(state),
    chat: { ...initialChatState },
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
  expect(suggestionClick).toBeDefined();
}

const click = (heroId: number) => act(() => suggestionClick?.(heroId));

describe('HeroDraftModal chat suggestion click', () => {
  it('opens the confirm dialog for the captain on turn', () => {
    renderAs(1);
    click(74);
    expect(screen.getByTestId('herodraft-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('herodraft-confirm-title')).toHaveTextContent(
      'Ban this hero?',
    );
  });

  it.each([
    ['the other captain', 2],
    ['a team member', 10],
  ])('does not open the confirm dialog for %s', (_label, pk) => {
    renderAs(pk);
    click(74);
    expect(screen.queryByTestId('herodraft-confirm-dialog')).toBeNull();
  });

  it('does not open the confirm dialog for a hero already drafted', () => {
    renderAs(1);
    click(5);
    expect(screen.queryByTestId('herodraft-confirm-dialog')).toBeNull();
  });

  it('does not open the confirm dialog while paused', () => {
    renderAs(1, 'paused');
    click(74);
    expect(screen.queryByTestId('herodraft-confirm-dialog')).toBeNull();
  });
});
