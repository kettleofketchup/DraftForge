// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getPendingReviews, putReview } from '../api';
import { EventLeadershipBanner } from '../EventLeadershipBanner';
import {
  DEFAULT_TRAITS,
  leadershipFeatureAccess,
  pendingReview,
} from './fixtures';

vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../api', () => ({
  getPendingReviews: vi.fn(),
  putReview: vi.fn(),
  deleteReview: vi.fn(),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const UNLOCKED: OrgFeatureAccess = leadershipFeatureAccess({ viewerPk: 12 });

const LATER = () => new Date(Date.now() + 86_400_000).toISOString();

function renderBanner(
  pending: number | undefined,
  access: OrgFeatureAccess = UNLOCKED,
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <EventLeadershipBanner
      event={{ id: 5, organization: 3, pending_captain_reviews: pending }}
      access={access}
    />,
    { wrapper },
  );
}

afterEach(() => {
  vi.mocked(getPendingReviews).mockReset();
  vi.mocked(putReview).mockReset();
});

describe('EventLeadershipBanner', () => {
  it('shows the pending captains for this event', async () => {
    vi.mocked(getPendingReviews).mockResolvedValue([
      pendingReview({ window_closes_at: LATER() }),
    ]);
    renderBanner(1);
    expect(
      await screen.findByTestId('event-leadership-item-5-7'),
    ).toBeInTheDocument();
    expect(getPendingReviews).toHaveBeenCalledWith(3, 5);
  });

  it.each([0, undefined])('hides with %s pending reviews', (pending) => {
    const { container } = renderBanner(pending);
    expect(container).toBeEmptyDOMElement();
    expect(getPendingReviews).not.toHaveBeenCalled();
  });

  it('hides while leadership is locked', () => {
    const { container } = renderBanner(
      2,
      leadershipFeatureAccess({ viewerPk: 12, track: null }),
    );
    expect(container).toBeEmptyDOMElement();
    expect(getPendingReviews).not.toHaveBeenCalled();
  });

  it('stays mounted for the toast when the event refetches to 0 pending', async () => {
    vi.mocked(getPendingReviews)
      .mockResolvedValueOnce([pendingReview({ window_closes_at: LATER() })])
      .mockResolvedValue([]);
    type Saved = Awaited<ReturnType<typeof putReview>>;
    let resolvePut: (value: Saved) => void = () => {};
    vi.mocked(putReview).mockReturnValue(
      new Promise<Saved>((resolve) => {
        resolvePut = resolve;
      }),
    );
    const view = renderBanner(1);
    fireEvent.click(await screen.findByTestId('event-leadership-open-5-7'));
    for (const trait of DEFAULT_TRAITS) {
      const group = screen.getByRole('radiogroup', { name: trait.label });
      fireEvent.click(within(group).getByRole('radio', { name: '4' }));
    }
    fireEvent.click(screen.getByTestId('leadership-review-submit'));
    await waitFor(() => expect(putReview).toHaveBeenCalled());
    view.rerender(
      <EventLeadershipBanner
        event={{ id: 5, organization: 3, pending_captain_reviews: 0 }}
        access={UNLOCKED}
      />,
    );
    resolvePut({
      scores: { communication: 4 },
      submitted_at: '2026-11-03T10:00:00Z',
      updated_at: '2026-11-03T10:00:00Z',
    });
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Review saved'),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('leadership-review-dialog')).toBeNull(),
    );
    expect(view.container).toBeEmptyDOMElement();
  });
});
