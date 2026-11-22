// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getPendingReviews } from '../api';
import { PendingReviewsCard, pendingCount } from '../PendingReviewsCard';
import { CAPTAIN, pendingReview } from './fixtures';

const { logger } = vi.hoisted(() => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));
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

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 12,
  leadershipUnlocked: true,
  leadershipMember: true,
});

const LATER = () => new Date(Date.now() + 86_400_000).toISOString();
const SCORES = { communication: 4, drafting: 3, composure: 5 };

function captain(pk: number) {
  return { ...CAPTAIN, org_user_pk: pk, username: `captain${pk}` };
}

function item(pk: number, overrides: Parameters<typeof pendingReview>[0]) {
  return pendingReview({
    captain_org_user_id: pk,
    captain: captain(pk),
    window_closes_at: LATER(),
    ...overrides,
  });
}

const FIVE = [
  item(1, { scores: null }),
  item(2, { scores: SCORES, void_kind: '' }),
  item(3, { scores: SCORES, void_kind: 'moderated' }),
  item(4, { scores: SCORES, void_kind: 'withdrawn' }),
  item(5, { scores: SCORES, void_kind: 'lifecycle' }),
];

function renderCard(props: { eventId?: number | null } = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<PendingReviewsCard orgId={3} access={access} {...props} />, {
    wrapper,
  });
}

afterEach(() => {
  vi.mocked(getPendingReviews).mockReset();
  logger.warn.mockReset();
});

describe('PendingReviewsCard', () => {
  it('lists pending captains and opens the dialog', async () => {
    vi.mocked(getPendingReviews).mockResolvedValue([item(7, {})]);
    renderCard();
    const row = await screen.findByTestId('leadership-pending-item-5-7');
    expect(row).toHaveTextContent('captain7');
    expect(row).toHaveTextContent('Team alice');
    expect(row).toHaveTextContent('Inhouse night');
    expect(
      screen.getByRole('heading', { name: 'Rate your captain' }),
    ).toBeInTheDocument();
    const open = screen.getByTestId('leadership-pending-open-5-7');
    expect(open).toHaveTextContent('Rate');
    expect(open.className).toContain('min-h-11');
    fireEvent.click(open);
    expect(
      await screen.findByTestId('leadership-review-dialog'),
    ).toBeInTheDocument();
    expect(getPendingReviews).toHaveBeenCalledWith(3, null);
  });

  it('counts only reviews still to submit', async () => {
    vi.mocked(getPendingReviews).mockResolvedValue(FIVE);
    renderCard();
    expect(
      await screen.findByTestId('leadership-pending-count'),
    ).toHaveTextContent('3');
    expect(pendingCount(FIVE)).toBe(3);
    const badges = [1, 2, 3, 4, 5].map(
      (pk) =>
        screen.queryByTestId(`leadership-pending-badge-5-${pk}`)?.textContent ??
        null,
    );
    expect(badges).toEqual([
      null,
      'Submitted',
      'Removed by an organizer',
      'Withdrawn',
      'No longer counted',
    ]);
    const labels = [1, 2, 3, 4, 5].map(
      (pk) => screen.getByTestId(`leadership-pending-open-5-${pk}`).textContent,
    );
    expect(labels).toEqual(['Rate', 'Edit', 'View', 'Rate', 'Rate']);
  });

  it('renders nothing without pending items', async () => {
    vi.mocked(getPendingReviews).mockResolvedValue([]);
    const { container } = renderCard();
    await waitFor(() => expect(getPendingReviews).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the pending request fails', async () => {
    vi.mocked(getPendingReviews).mockRejectedValue(new Error('boom'));
    const { container } = renderCard();
    await waitFor(() => expect(logger.warn).toHaveBeenCalledTimes(1));
    expect(container).toBeEmptyDOMElement();
  });

  it('passes event_id when scoped to an event', async () => {
    vi.mocked(getPendingReviews).mockResolvedValue([item(7, {})]);
    renderCard({ eventId: 5 });
    await screen.findByTestId('leadership-pending-item-5-7');
    expect(getPendingReviews).toHaveBeenCalledWith(3, 5);
  });
});
