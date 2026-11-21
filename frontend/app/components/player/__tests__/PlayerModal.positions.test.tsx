// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { PlayerModal } from '../PlayerModal';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopover: () => ({
    playerModalState: { player: null, open: true, context: {} },
  }),
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function renderModal(player: UserType) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <PlayerModal player={player} open onOpenChange={vi.fn()} />
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function positionsRow(): Element | null {
  return document.querySelector('[data-testid="player-modal-positions"]');
}

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('{}', {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('PlayerModal positions row', () => {
  it('renders no positions row when the player has no positions', () => {
    renderModal({
      pk: 51,
      username: 'nopos',
      nickname: 'NoPos',
      steam_account_id: 12345,
    } as UserType);
    expect(screen.getByText('Friend ID:')).toBeTruthy();
    expect(positionsRow()).toBeNull();
    expect(document.querySelector('.pt-1.pl-1')).toBeNull();
  });

  it('renders no positions row when every position is unset', () => {
    renderModal({
      pk: 52,
      username: 'zeros',
      positions: {
        carry: 0,
        mid: 0,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
    } as UserType);
    expect(positionsRow()).toBeNull();
  });

  it('still renders the positions row when the player has positions', () => {
    renderModal({
      pk: 53,
      username: 'haspos',
      positions: {
        carry: 1,
        mid: 0,
        offlane: 2,
        soft_support: 0,
        hard_support: 0,
      },
    } as UserType);
    const row = positionsRow();
    expect(row).not.toBeNull();
    expect(row?.className).toBe('pt-1 pl-1');
    expect(screen.getByText('Carry')).toBeTruthy();
    expect(screen.getByText('Offlane')).toBeTruthy();
  });
});
