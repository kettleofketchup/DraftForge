// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
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

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;

afterEach(cleanup);

describe('PlayerModal avatar ring', () => {
  // ring-2 paints 2px outside the avatar; the scroll viewport clips it unless
  // the content is inset by at least that much.
  it('insets the content from the scroll viewport by the ring width', () => {
    const client = new QueryClient();
    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <TooltipProvider>
            <PlayerModal player={player} open onOpenChange={vi.fn()} />
          </TooltipProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const avatar = document.querySelector('.ring-2');
    expect(avatar).not.toBeNull();
    const viewport = avatar!.closest('[data-slot="scroll-area-viewport"]');
    expect(viewport).not.toBeNull();

    const insets: string[] = [];
    for (
      let el = avatar!.parentElement;
      el && el !== viewport;
      el = el.parentElement
    ) {
      insets.push(
        ...Array.from(el.classList).filter((c) =>
          /^p-(0\.5|1|1\.5|2)$/.test(c),
        ),
      );
    }
    expect(insets).not.toHaveLength(0);
  });
});
