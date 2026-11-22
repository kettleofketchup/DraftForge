// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReviewModerationTable } from '../ReviewModerationTable';
import type { EventCaptainReviews, ModerationReview } from '../schemas';
import {
  DEFAULT_TRAITS,
  eventAggregate,
  eventReviews,
  moderationReview,
} from './fixtures';

function captainWith(
  overrides: Partial<EventCaptainReviews> = {},
): EventCaptainReviews {
  return { ...eventReviews().captains[0], ...overrides };
}

function renderTable(
  captain: EventCaptainReviews,
  handlers: {
    onVoid?: (r: ModerationReview) => void;
    onUnvoid?: (r: ModerationReview) => void;
  } = {},
) {
  return render(
    <ReviewModerationTable
      captain={captain}
      traits={DEFAULT_TRAITS}
      onVoid={handlers.onVoid ?? vi.fn()}
      onUnvoid={handlers.onUnvoid ?? vi.fn()}
      pendingPk={null}
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
      'You captained this team. Another admin has to moderate its reviews.',
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
});
