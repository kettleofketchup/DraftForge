// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getPendingReviews } from '../api';
import { EventLeadershipBanner } from '../EventLeadershipBanner';
import { pendingReview } from './fixtures';

vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}));
vi.mock('../api', () => ({
  getPendingReviews: vi.fn(),
  putReview: vi.fn(),
  deleteReview: vi.fn(),
}));

const UNLOCKED: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 12,
  leadershipUnlocked: true,
  leadershipMember: true,
});

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
      makeOrgFeatureAccess({ viewerPk: 12, leadershipUnlocked: false }),
    );
    expect(container).toBeEmptyDOMElement();
    expect(getPendingReviews).not.toHaveBeenCalled();
  });
});
