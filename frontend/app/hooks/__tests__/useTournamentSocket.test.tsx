// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Handler = (msg: unknown) => void;
const { manager, captured } = vi.hoisted(() => {
  const captured: { handler: Handler | null } = { handler: null };
  return {
    captured,
    manager: {
      connect: vi.fn(() => 'conn-t'),
      subscribe: vi.fn((_id: string, cb: Handler) => {
        captured.handler = cb;
        return () => {};
      }),
    },
  };
});
vi.mock('~/lib/websocket', () => ({ getWebSocketManager: () => manager }));

const { useTournamentSocket, TOURNAMENT_REFETCH_WINDOW_MS } = await import('../useTournamentSocket');
const { useDraftWebSocketStore } = await import('~/store/draftWebSocketStore');

const emit = (msg: unknown) => captured.handler!(msg);
const draftEvent = (draftPk: number, event_type = 'player_picked') => ({
  type: 'draft_event',
  event: { pk: 1, event_type },
  draft_state: { pk: draftPk },
});

describe('useTournamentSocket', () => {
  let client: QueryClient;
  let invalidate: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    client = new QueryClient();
    invalidate = vi.spyOn(client, 'invalidateQueries');
    useDraftWebSocketStore.setState({ _currentDraftId: null, status: 'disconnected' });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    renderHook(() => useTournamentSocket(5), { wrapper });
  });
  afterEach(() => vi.useRealTimers());

  it('refetches the tournament once for a burst of events', () => {
    for (let i = 0; i < 5; i++) emit(draftEvent(9));
    expect(invalidate).not.toHaveBeenCalled();
    vi.advanceTimersByTime(TOURNAMENT_REFETCH_WINDOW_MS);
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['tournament', 5] });
  });

  it('skips the refetch when the open draft socket already applies the event state', () => {
    useDraftWebSocketStore.setState({ _currentDraftId: 9, status: 'connected' });
    emit(draftEvent(9));
    vi.advanceTimersByTime(TOURNAMENT_REFETCH_WINDOW_MS);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('still refetches for an event without draft state', () => {
    useDraftWebSocketStore.setState({ _currentDraftId: 9, status: 'connected' });
    emit({ type: 'draft_event', event: { pk: 2 } });
    vi.advanceTimersByTime(TOURNAMENT_REFETCH_WINDOW_MS);
    expect(invalidate).toHaveBeenCalledTimes(1);
  });

  it('refetches when the draft completes even though the draft socket carries the state', () => {
    useDraftWebSocketStore.setState({ _currentDraftId: 9, status: 'connected' });
    emit(draftEvent(9, 'draft_completed'));
    vi.advanceTimersByTime(TOURNAMENT_REFETCH_WINDOW_MS);
    expect(invalidate).toHaveBeenCalledTimes(1);
  });
});
