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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import {
  getEventReviews,
  getTraits,
  releaseResults,
  unvoidReview,
  voidReview,
} from '../api';
import { EventLeadershipSection } from '../EventLeadershipSection';
import {
  CAPTAIN,
  eventReviews,
  leadershipFeatureAccess,
  moderationCaptain,
  moderationReview,
  traits,
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
  getEventReviews: vi.fn(),
  getTraits: vi.fn(),
  voidReview: vi.fn(),
  unvoidReview: vi.fn(),
  releaseResults: vi.fn(),
}));

const ADMIN: OrgFeatureAccess = leadershipFeatureAccess({
  viewerPk: 1,
  track: { can_manage: true, can_moderate: true },
});

function renderSection(access: OrgFeatureAccess = ADMIN) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <EventLeadershipSection
      event={{ id: 5, organization: 3 }}
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
  vi.mocked(releaseResults).mockReset();
  vi.mocked(toast.error).mockReset();
  vi.mocked(toast.success).mockReset();
});

describe('EventLeadershipSection', () => {
  it('lists the captains with trait labels', async () => {
    renderSection();
    expect(
      await screen.findByTestId('leadership-moderation-7'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('leadership-moderation')).toHaveTextContent(
      'Moderators only. Raters are never shown to captains.',
    );
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
    vi.mocked(voidReview).mockRejectedValue(refusal(409, 'snapshot_voided'));
    renderSection();
    fireEvent.click(await screen.findByTestId('leadership-void-31'));
    fireEvent.change(screen.getByTestId('leadership-void-reason'), {
      target: { value: 'spam' },
    });
    fireEvent.click(screen.getByTestId('leadership-void-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Reviews for this event were closed because the event was reopened or cancelled.',
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

  it('is hidden for plain members', () => {
    const { container } = renderSection(
      leadershipFeatureAccess({ viewerPk: 1 }),
    );
    expect(container).toBeEmptyDOMElement();
    expect(getEventReviews).not.toHaveBeenCalled();
  });

  it('shows a load failure instead of hiding the section', async () => {
    vi.mocked(getEventReviews).mockRejectedValue(refusal(500));
    renderSection();
    expect(
      await screen.findByTestId('leadership-moderation-error'),
    ).toBeInTheDocument();
  });

  it('offers no void or restore on the viewer’s own review', async () => {
    renderSection(
      leadershipFeatureAccess({
        viewerPk: 12,
        track: { can_manage: true, can_moderate: true },
      }),
    );
    expect(
      await screen.findByTestId('leadership-own-review-31'),
    ).toHaveTextContent('Your review');
    expect(screen.queryByTestId('leadership-void-31')).toBeNull();
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

  it('renders for org staff who cannot manage settings', async () => {
    renderSection(
      leadershipFeatureAccess({
        viewerPk: 1,
        track: { can_manage: false, can_moderate: true },
      }),
    );
    expect(
      await screen.findByTestId('leadership-moderation-7'),
    ).toBeInTheDocument();
  });

  it('hides Release all with the gate off', async () => {
    renderSection();
    await screen.findByTestId('leadership-moderation-7');
    expect(screen.queryByTestId('leadership-release-all')).toBeNull();
  });

  describe('release', () => {
    const BOB = { ...CAPTAIN, org_user_pk: 9, user_pk: 13, username: 'carol' };
    const gated = () =>
      eventReviews({
        require_staff_release: true,
        captains: [
          moderationCaptain({
            release_state: 'pending',
            released: false,
            can_release: true,
          }),
          moderationCaptain({
            org_user_id: 9,
            captain: BOB,
            team_name: 'Team carol',
            release_state: 'pending',
            released: false,
            can_release: true,
          }),
          moderationCaptain({
            org_user_id: 10,
            captain: { ...CAPTAIN, org_user_pk: 10, username: 'erin' },
            team_name: 'Team erin',
            release_state: 'open',
            released: false,
          }),
        ],
      });

    beforeEach(() => {
      vi.mocked(getEventReviews).mockResolvedValue(gated());
    });

    it('releases every pending captain event-wide', async () => {
      vi.mocked(releaseResults).mockResolvedValue({
        released: [7, 9],
        skipped: [],
      });
      renderSection();
      const button = await screen.findByTestId('leadership-release-all');
      expect(button).toHaveTextContent('Release all pending (2)');
      fireEvent.click(button);
      const dialog = screen.getByTestId('leadership-release-dialog');
      expect(dialog).toHaveTextContent('Team alice');
      expect(dialog).toHaveTextContent('Team carol');
      expect(dialog).not.toHaveTextContent('Team erin');
      fireEvent.click(within(dialog).getByTestId('leadership-release-confirm'));
      await waitFor(() =>
        expect(releaseResults).toHaveBeenCalledWith(3, 5, undefined),
      );
      await waitFor(() =>
        expect(screen.queryByTestId('leadership-release-dialog')).toBeNull(),
      );
      expect(toast.success).toHaveBeenCalled();
    });

    it('releases one captain', async () => {
      vi.mocked(releaseResults).mockResolvedValue({
        released: [9],
        skipped: [],
      });
      renderSection();
      fireEvent.click(await screen.findByTestId('leadership-release-9'));
      const dialog = screen.getByTestId('leadership-release-dialog');
      expect(dialog).toHaveTextContent('Team carol');
      expect(dialog).not.toHaveTextContent('Team alice');
      fireEvent.click(within(dialog).getByTestId('leadership-release-confirm'));
      await waitFor(() =>
        expect(releaseResults).toHaveBeenCalledWith(3, 5, [9]),
      );
    });

    it('shows the refusal on a double release', async () => {
      vi.mocked(releaseResults).mockRejectedValue(
        refusal(409, 'already_released'),
      );
      renderSection();
      fireEvent.click(await screen.findByTestId('leadership-release-7'));
      fireEvent.click(screen.getByTestId('leadership-release-confirm'));
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          'These results were already released.',
        ),
      );
    });
  });
});
