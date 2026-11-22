// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventType } from '~/components/events/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getEventReviews, getTraits, unvoidReview, voidReview } from '../api';
import { EventLeadershipSection } from '../EventLeadershipSection';
import { eventReviews, moderationReview, traits } from './fixtures';

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
  getEventReviews: vi.fn(),
  getTraits: vi.fn(),
  voidReview: vi.fn(),
  unvoidReview: vi.fn(),
}));

const ADMIN: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 1,
  leadershipUnlocked: true,
  canManageLeadership: true,
});

function renderSection(
  state: EventType['state'] = 'completed',
  access: OrgFeatureAccess = ADMIN,
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <EventLeadershipSection
      event={{ id: 5, organization: 3, state }}
      access={access}
    />,
    { wrapper },
  );
}

function refusal(status: number, code?: string) {
  return { response: { status, data: code ? { code } : {} } };
}

beforeEach(() => {
  vi.mocked(getEventReviews).mockResolvedValue(eventReviews());
  vi.mocked(getTraits).mockResolvedValue(traits().traits);
});

afterEach(() => {
  vi.mocked(getEventReviews).mockReset();
  vi.mocked(getTraits).mockReset();
  vi.mocked(voidReview).mockReset();
  vi.mocked(unvoidReview).mockReset();
  vi.mocked(toast.error).mockReset();
});

describe('EventLeadershipSection', () => {
  it('lists the captains with trait labels', async () => {
    renderSection();
    expect(
      await screen.findByTestId('leadership-moderation'),
    ).toHaveTextContent('Admins only. Raters are never shown to captains.');
    expect(screen.getByTestId('leadership-moderation-7')).toBeInTheDocument();
    expect((await screen.findAllByText('Composure: 5')).length).toBeGreaterThan(
      0,
    );
    expect(getEventReviews).toHaveBeenCalledWith(3, 5);
  });

  it('voids with a reason', async () => {
    vi.mocked(voidReview).mockResolvedValue(
      moderationReview({ void_kind: 'moderated' }),
    );
    renderSection();
    fireEvent.click(await screen.findByTestId('leadership-void-31'));
    const confirm = screen.getByTestId('leadership-void-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId('leadership-void-reason'), {
      target: { value: 'spam' },
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(voidReview).toHaveBeenCalledWith(3, 31, 'spam'));
    await waitFor(() =>
      expect(screen.queryByTestId('leadership-void-confirm')).toBeNull(),
    );
  });

  it('keeps the dialog open with the refusal on a failed void', async () => {
    vi.mocked(voidReview).mockRejectedValue(
      refusal(409, 'cannot_moderate_own_reviews'),
    );
    renderSection();
    fireEvent.click(await screen.findByTestId('leadership-void-31'));
    fireEvent.change(screen.getByTestId('leadership-void-reason'), {
      target: { value: 'spam' },
    });
    fireEvent.click(screen.getByTestId('leadership-void-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You captained this team. Another admin has to moderate its reviews.',
    );
  });

  it('restores a staff-voided review', async () => {
    vi.mocked(getEventReviews).mockResolvedValue(
      eventReviews({
        captains: [
          {
            ...eventReviews().captains[0],
            reviews: [
              moderationReview({
                voided_at: '2026-11-03T10:00:00Z',
                void_kind: 'moderated',
                void_reason: 'spam',
              }),
            ],
          },
        ],
      }),
    );
    vi.mocked(unvoidReview).mockResolvedValue(moderationReview());
    renderSection();
    fireEvent.click(await screen.findByTestId('leadership-unvoid-31'));
    await waitFor(() => expect(unvoidReview).toHaveBeenCalledWith(3, 31));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('maps not_in_pool on restore', async () => {
    vi.mocked(getEventReviews).mockResolvedValue(
      eventReviews({
        captains: [
          {
            ...eventReviews().captains[0],
            reviews: [
              moderationReview({
                voided_at: '2026-11-03T10:00:00Z',
                void_kind: 'moderated',
                void_reason: 'spam',
              }),
            ],
          },
        ],
      }),
    );
    vi.mocked(unvoidReview).mockRejectedValue(refusal(409, 'not_in_pool'));
    renderSection();
    fireEvent.click(await screen.findByTestId('leadership-unvoid-31'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "The rater is no longer on this captain's team.",
      ),
    );
  });

  it('is hidden for non-admins', () => {
    const { container } = renderSection(
      'completed',
      makeOrgFeatureAccess({ viewerPk: 1, leadershipUnlocked: true }),
    );
    expect(container).toBeEmptyDOMElement();
    expect(getEventReviews).not.toHaveBeenCalled();
  });

  it('is hidden before the event runs', () => {
    const { container } = renderSection('signups_open');
    expect(container).toBeEmptyDOMElement();
    expect(getEventReviews).not.toHaveBeenCalled();
  });

  it('renders nothing when the event has no captains', async () => {
    vi.mocked(getEventReviews).mockResolvedValue(
      eventReviews({ captains: [] }),
    );
    const { container } = renderSection();
    await waitFor(() => expect(getEventReviews).toHaveBeenCalled());
    await waitFor(() => expect(getTraits).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
