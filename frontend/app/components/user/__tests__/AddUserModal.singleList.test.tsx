// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { AddUserModal } from '~/components/user/AddUserModal';
import type { UserType } from '~/components/user/types';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  searchUsers: vi.fn(async () => [
    {
      pk: 5001,
      username: 'event_player_1',
      membership: 'org',
      membership_label: 'Events Test Org',
    },
  ]),
  searchDiscordMembers: vi.fn(async () => []),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => undefined;

let restoreViewport: (() => void) | undefined;

afterEach(() => {
  restoreViewport?.();
  restoreViewport = undefined;
});

function renderModal() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SharedPopoverProvider>
        <AddUserModal
          open
          onOpenChange={() => undefined}
          title="Add Member"
          entityContext={{ orgId: 7 }}
          onAdd={async () => ({}) as UserType}
          isAdded={(user) => user.pk === 5001}
          hasDiscordServer={false}
        />
      </SharedPopoverProvider>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByTestId('add-user-search'), {
    target: { value: 'event_player_1' },
  });
}

describe('AddUserModal site results', () => {
  it.each([
    ['desktop', 1400],
    ['mobile', 500],
  ])('lists each user once on %s', async (_label, width) => {
    restoreViewport = setViewportWidth(width);
    renderModal();

    const rows = await screen.findAllByTestId(
      'site-user-result-event_player_1',
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent(/already added/i);
  });
});
