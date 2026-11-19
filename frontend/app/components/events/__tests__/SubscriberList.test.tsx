// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getRepeaterSubscribers } from '~/components/api/api';
import { useUserCacheStore } from '~/store/userCacheStore';
import { SubscriberList } from '../SubscriberList';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getRepeaterSubscribers: vi.fn(),
}));

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SubscriberList repeaterId={4} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('SubscriberList', () => {
  it('names subscribers from their own payload, not the user whose pk matches the subscription id', async () => {
    useUserCacheStore
      .getState()
      .upsert({ pk: 12, username: 'other', nickname: 'Someone Else' } as never);
    vi.mocked(getRepeaterSubscribers).mockResolvedValue([
      {
        id: 12,
        username: 'sub_user',
        nickname: null,
        discordNickname: 'Subby',
        discordId: null,
        avatar: null,
        created_at: '2026-11-01T00:00:00Z',
      },
    ]);
    renderList();
    fireEvent.click(await screen.findByText('Notification Subscribers'));
    expect(screen.getByText('Subby')).toBeInTheDocument();
    expect(screen.queryByText('Someone Else')).toBeNull();
  });
});
