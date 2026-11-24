// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import { ReviewModerationTable } from '../ReviewModerationTable';
import type { EventCaptainReviews, ModerationReview } from '../schemas';
import {
  DEFAULT_TRAITS,
  eventAggregate,
  moderationCaptain,
  moderationReview,
} from './fixtures';

function captainWith(
  overrides: Partial<EventCaptainReviews> = {},
): EventCaptainReviews {
  return moderationCaptain(overrides);
}

const OWN_NOTE =
  'You captained this team. Another org moderator, or site staff, has to release it. Your results show here once released.';

function renderTable(
  captain: EventCaptainReviews,
  handlers: {
    onVoid?: (r: ModerationReview) => void;
    onUnvoid?: (r: ModerationReview) => void;
    onRelease?: (c: EventCaptainReviews) => void;
  } = {},
  viewerPk: number | null = 1,
) {
  return render(
    <ReviewModerationTable
      captain={captain}
      viewerPk={viewerPk}
      traits={DEFAULT_TRAITS}
      onVoid={handlers.onVoid ?? vi.fn()}
      onUnvoid={handlers.onUnvoid ?? vi.fn()}
      pendingPk={null}
      onRelease={handlers.onRelease ?? vi.fn()}
    />,
  );
}

describe('ReviewModerationTable', () => {
  it('lists reviews with rater and scores', () => {
    renderTable(captainWith());
    const block = screen.getByTestId('leadership-moderation-7');
    expect(within(block).getByText('alice')).toBeInTheDocument();
    const row = screen.getByTestId('leadership-review-row-31');
    expect(within(row).getAllByText('bob').length).toBeGreaterThan(0);
    expect(within(row).getAllByText('Drafting: 3').length).toBeGreaterThan(0);
    expect(within(row).getAllByText('Live').length).toBeGreaterThan(0);
    expect(screen.getByTestId('leadership-void-31')).toBeInTheDocument();
    expect(screen.queryByTestId('leadership-unvoid-31')).toBeNull();
  });

  it('calls onVoid and onUnvoid for the right rows', () => {
    const onVoid = vi.fn();
    const onUnvoid = vi.fn();
    const moderated = moderationReview({
      pk: 32,
      voided_at: '2026-11-03T10:00:00Z',
      void_kind: 'moderated',
      void_reason: 'spam',
    });
    renderTable(captainWith({ reviews: [moderationReview(), moderated] }), {
      onVoid,
      onUnvoid,
    });
    fireEvent.click(screen.getByTestId('leadership-void-31'));
    expect(onVoid).toHaveBeenCalledWith(expect.objectContaining({ pk: 31 }));
    expect(screen.queryByTestId('leadership-void-32')).toBeNull();
    fireEvent.click(screen.getByTestId('leadership-unvoid-32'));
    expect(onUnvoid).toHaveBeenCalledWith(expect.objectContaining({ pk: 32 }));
  });

  it('offers no void or restore on a review the viewer wrote', () => {
    const moderated = moderationReview({
      pk: 32,
      voided_at: '2026-11-03T10:00:00Z',
      void_kind: 'moderated',
    });
    renderTable(
      captainWith({ reviews: [moderationReview(), moderated] }),
      {},
      12,
    );
    expect(screen.queryByTestId('leadership-void-31')).toBeNull();
    expect(screen.queryByTestId('leadership-unvoid-32')).toBeNull();
    expect(screen.getByTestId('leadership-own-review-32')).toHaveTextContent(
      'Your review',
    );
  });

  it('offers no action on a withdrawn review', () => {
    renderTable(
      captainWith({
        reviews: [
          moderationReview({
            voided_at: '2026-11-03T10:00:00Z',
            void_kind: 'withdrawn',
          }),
        ],
      }),
    );
    expect(screen.queryByTestId('leadership-void-31')).toBeNull();
    expect(screen.queryByTestId('leadership-unvoid-31')).toBeNull();
    expect(screen.getAllByText('Withdrawn').length).toBeGreaterThan(0);
  });

  it('shows the own-snapshot note without rows or actions', () => {
    renderTable(
      captainWith({
        own_snapshot: true,
        reviews: null,
        aggregate: eventAggregate({ rating: 4.1 }),
      }),
    );
    expect(screen.getByTestId('leadership-moderation-own-7')).toHaveTextContent(
      OWN_NOTE,
    );
    expect(screen.getByTestId('leadership-moderation-7')).toHaveTextContent(
      '4.1',
    );
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByTestId(/^leadership-(void|unvoid)-/)).toBeNull();
  });

  it('shows a deleted rater', () => {
    renderTable(captainWith({ reviews: [moderationReview({ rater: null })] }));
    expect(
      within(screen.getByTestId('leadership-review-row-31')).getByText(
        'Deleted account',
      ),
    ).toBeInTheDocument();
  });

  it('shows the empty message without reviews', () => {
    renderTable(captainWith({ reviews: [] }));
    expect(screen.getByText('No reviews')).toBeInTheDocument();
  });

  it('keeps the status column badge-only and puts a long reason under the rater', () => {
    const reason = 'x'.repeat(500);
    renderTable(
      captainWith({
        reviews: [
          moderationReview({
            voided_at: '2026-11-03T10:00:00Z',
            void_kind: 'moderated',
            void_reason: reason,
          }),
        ],
      }),
    );
    const row = screen.getByTestId('leadership-review-row-31');
    const cells = row.querySelectorAll('td');
    const raterCell = cells[0];
    const reasonEl = screen.getByTestId('leadership-void-reason-31');
    expect(raterCell.contains(reasonEl)).toBe(true);
    expect(reasonEl).toHaveTextContent(reason);
    expect(reasonEl).toHaveClass('break-words', 'line-clamp-3');
    expect(reasonEl).toHaveAttribute('title', reason);
    const statusCell = screen.getByTestId('leadership-status-31').closest('td');
    expect(statusCell).not.toBeNull();
    expect(statusCell!.className).not.toMatch(/(^|\s)w-\d/);
    expect(statusCell!.textContent).toBe('Voided by staff');
  });

  it('stacks status below sm and scores below md', () => {
    renderTable(captainWith());
    expect(screen.getByTestId('leadership-stacked-status-31')).toHaveClass(
      'sm:hidden',
    );
    expect(screen.getByTestId('leadership-stacked-scores-31')).toHaveClass(
      'md:hidden',
    );
  });

  it('puts the action beside the rater and the date under it below sm', () => {
    renderTable(captainWith());
    const row = screen.getByTestId('leadership-review-row-31');
    const cells = row.querySelectorAll('td');
    const head = screen.getByTestId('leadership-stacked-head-31');
    expect(cells[0].contains(head)).toBe(true);
    expect(within(head).getByTestId('leadership-void-31')).toBeInTheDocument();
    expect(screen.getAllByTestId('leadership-void-31')).toHaveLength(1);
    expect(
      head.contains(screen.getByTestId('leadership-stacked-scores-31')),
    ).toBe(false);
    const stacked = screen.getByTestId('leadership-stacked-status-31');
    expect(stacked).toHaveClass('sm:hidden');
    expect(stacked).toHaveTextContent('Live');
    expect(
      within(stacked).getByTestId('leadership-stacked-submitted-31'),
    ).toHaveTextContent(/\d{4}/);
    const actionsCell = cells[cells.length - 1];
    expect(actionsCell).toHaveClass('hidden', 'sm:table-cell');
    expect(actionsCell.textContent).toBe('');
  });

  it('keeps the action in its own column from sm', () => {
    const restore = setViewportWidth(1024);
    try {
      renderTable(captainWith());
      const row = screen.getByTestId('leadership-review-row-31');
      const cells = row.querySelectorAll('td');
      const button = screen.getByTestId('leadership-void-31');
      expect(screen.getAllByTestId('leadership-void-31')).toHaveLength(1);
      expect(cells[cells.length - 1].contains(button)).toBe(true);
      expect(cells[0].contains(button)).toBe(false);
    } finally {
      restore();
    }
  });

  describe('release state', () => {
    it.each([
      ['released', 'Released'],
      ['pending', 'Pending release'],
      ['open', 'Window open'],
      ['short', 'Not enough reviews'],
      ['voided', 'Voided'],
      ['hidden', 'Hidden'],
    ] as const)('badges %s as %s', (state, label) => {
      renderTable(captainWith({ release_state: state, released: false }));
      expect(
        screen.getByTestId('leadership-release-state-7'),
      ).toHaveTextContent(new RegExp(`^${label}$`));
    });

    it('shows the live count against the floor', () => {
      renderTable(
        captainWith({
          release_state: 'short',
          live_reviews: 1,
          release_floor: 2,
        }),
      );
      expect(
        screen.getByTestId('leadership-release-count-7'),
      ).toHaveTextContent('1 / 2 reviews');
    });

    it('offers Release and the auto-release time only while pending', () => {
      const onRelease = vi.fn();
      const captain = captainWith({
        release_state: 'pending',
        released: false,
        can_release: true,
        auto_release_at: '2026-11-26T12:00:00Z',
      });
      renderTable(captain, { onRelease });
      expect(screen.getByTestId('leadership-auto-release-7')).toHaveTextContent(
        /^auto-releases .*2026/,
      );
      fireEvent.click(screen.getByTestId('leadership-release-7'));
      expect(onRelease).toHaveBeenCalledWith(captain);
    });

    it('hides Release without can_release', () => {
      renderTable(
        captainWith({ release_state: 'pending', can_release: false }),
      );
      expect(screen.queryByTestId('leadership-release-7')).toBeNull();
    });

    it('shows no auto-release text on a row that is not pending', () => {
      renderTable(
        captainWith({
          release_state: 'short',
          auto_release_at: '2026-11-26T12:00:00Z',
        }),
      );
      expect(screen.queryByTestId('leadership-auto-release-7')).toBeNull();
    });

    it('names who released it and when', () => {
      renderTable(
        captainWith({
          release_state: 'released',
          released_at: '2026-11-23T10:02:00Z',
          released_by: { pk: 4, username: 'dana' },
        }),
      );
      expect(screen.getByTestId('leadership-released-by-7')).toHaveTextContent(
        /^by dana · .*2026/,
      );
    });

    it('shows nothing extra for a release without a stamp', () => {
      renderTable(
        captainWith({ release_state: 'released', released_at: null }),
      );
      expect(screen.queryByTestId('leadership-released-by-7')).toBeNull();
    });

    it('hides counts, release and auto-release on the own row', () => {
      renderTable(
        captainWith({
          own_snapshot: true,
          reviews: null,
          release_state: 'hidden',
          released: false,
          live_reviews: null,
          release_floor: null,
          auto_release_at: null,
          can_release: false,
        }),
      );
      expect(
        screen.getByTestId('leadership-moderation-own-7'),
      ).toHaveTextContent(OWN_NOTE);
      expect(
        screen.getByTestId('leadership-release-state-7'),
      ).toHaveTextContent('Hidden');
      expect(screen.queryByTestId('leadership-release-count-7')).toBeNull();
      expect(screen.queryByTestId('leadership-auto-release-7')).toBeNull();
      expect(screen.queryByTestId('leadership-release-7')).toBeNull();
      expect(screen.queryByRole('table')).toBeNull();
    });
  });
});
