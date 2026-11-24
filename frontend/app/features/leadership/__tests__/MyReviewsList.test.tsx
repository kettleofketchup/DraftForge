// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import type { TrackInfo } from '~/features/standing/schemas';
import { getMyReviews } from '../api';
import { MyReviewsList } from '../MyReviewsList';
import { myReview } from './fixtures';

vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}));
vi.mock('../api', () => ({ getMyReviews: vi.fn() }));

const LEADERSHIP: TrackInfo = {
  key: 'leadership',
  label: 'Leadership',
  metrics: [
    {
      key: 'rating.drafting',
      label: 'Drafting',
      format: 'score5',
      periodic: false,
      default: false,
    },
  ],
  can_view_rows: true,
  can_view_own: true,
  board_open: true,
  can_manage: false,
  can_moderate: false,
};

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 12,
  standingTracks: [LEADERSHIP],
});

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<MyReviewsList orgId={3} access={access} />, { wrapper });
}

afterEach(() => vi.mocked(getMyReviews).mockReset());

describe('MyReviewsList', () => {
  it('fetches only when expanded', async () => {
    vi.mocked(getMyReviews).mockResolvedValue([myReview()]);
    renderList();
    expect(getMyReviews).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('leadership-mine-toggle'));
    const row = await screen.findByTestId('leadership-mine-5-7');
    expect(getMyReviews).toHaveBeenCalledWith(3);
    expect(row).toHaveTextContent('Inhouse night');
    expect(row).toHaveTextContent('alice');
    expect(row).toHaveTextContent('Drafting');
    expect(row).toHaveTextContent('Sportsmanship');
  });

  it('notes a review that no longer counts', async () => {
    vi.mocked(getMyReviews).mockResolvedValue([
      myReview({ void_kind: 'moderated' }),
    ]);
    renderList();
    fireEvent.click(screen.getByTestId('leadership-mine-toggle'));
    expect(
      await screen.findByTestId('leadership-mine-5-7-void'),
    ).toHaveTextContent('Removed by an organizer');
  });

  it('says so when there are no reviews', async () => {
    vi.mocked(getMyReviews).mockResolvedValue([]);
    renderList();
    fireEvent.click(screen.getByTestId('leadership-mine-toggle'));
    expect(
      await screen.findByTestId('leadership-mine-empty'),
    ).toBeInTheDocument();
  });
});
