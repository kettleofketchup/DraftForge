// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { deleteReview, putReview } from '../api';
import { CaptainReviewDialog } from '../CaptainReviewDialog';
import type { PendingReview } from '../schemas';
import { pendingReview } from './fixtures';

const { logger } = vi.hoisted(() => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../api', () => ({ putReview: vi.fn(), deleteReview: vi.fn() }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function openReview(overrides: Partial<PendingReview> = {}): PendingReview {
  return pendingReview({
    window_closes_at: new Date(Date.now() + 2 * 86_400_000).toISOString(),
    ...overrides,
  });
}

function renderDialog(review: PendingReview) {
  const onOpenChange = vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(
    <CaptainReviewDialog
      orgId={1}
      review={review}
      open
      onOpenChange={onOpenChange}
    />,
    { wrapper },
  );
  return onOpenChange;
}

function pick(trait: string, score: number) {
  const group = screen.getByRole('radiogroup', { name: trait });
  fireEvent.click(within(group).getByRole('radio', { name: String(score) }));
}

function submit() {
  fireEvent.click(screen.getByTestId('leadership-review-submit'));
}

afterEach(() => {
  vi.useRealTimers();
  vi.mocked(putReview).mockReset();
  vi.mocked(deleteReview).mockReset();
  vi.mocked(toast.success).mockReset();
  logger.warn.mockReset();
  logger.error.mockReset();
});

describe('CaptainReviewDialog', () => {
  it('submits every active trait score', async () => {
    vi.mocked(putReview).mockResolvedValue({
      scores: {},
      submitted_at: '2026-11-22T10:00:00Z',
      updated_at: '2026-11-22T10:00:00Z',
    });
    const onOpenChange = renderDialog(openReview());

    expect(screen.getByTestId('leadership-review-dialog')).toHaveTextContent(
      'alice',
    );
    pick('Communication', 5);
    pick('Drafting', 4);
    pick('Composure', 3);
    pick('Sportsmanship', 2);
    expect(screen.getByTestId('leadership-review-submit')).toHaveTextContent(
      'Submit',
    );
    submit();

    await waitFor(() =>
      expect(putReview).toHaveBeenCalledWith(1, 5, 7, {
        communication: 5,
        drafting: 4,
        composure: 3,
        sportsmanship: 2,
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toast.success).toHaveBeenCalledWith('Review saved');
  });

  it('blocks submit until every trait has a score', async () => {
    renderDialog(openReview());
    pick('Communication', 5);
    pick('Drafting', 4);
    pick('Composure', 3);
    submit();

    expect(await screen.findByText('Pick a score')).toBeInTheDocument();
    expect(putReview).not.toHaveBeenCalled();
  });

  it('prefills only active traits and requires the new one', async () => {
    vi.mocked(putReview).mockResolvedValue({
      scores: {},
      submitted_at: '2026-11-22T10:00:00Z',
      updated_at: '2026-11-22T10:00:00Z',
    });
    renderDialog(
      openReview({
        traits: [
          { key: 'communication', label: 'Communication' },
          { key: 'leadership_new', label: 'Shotcalling' },
        ],
        scores: { communication: 4, retired: 2 },
      }),
    );

    expect(
      within(
        screen.getByRole('radiogroup', { name: 'Communication' }),
      ).getByRole('radio', { name: '4' }),
    ).toHaveAttribute('aria-checked', 'true');
    submit();
    expect(await screen.findByText('Pick a score')).toBeInTheDocument();
    expect(putReview).not.toHaveBeenCalled();

    pick('Shotcalling', 5);
    submit();
    await waitFor(() =>
      expect(putReview).toHaveBeenCalledWith(1, 5, 7, {
        communication: 4,
        leadership_new: 5,
      }),
    );
  });

  it('labels an existing review Update and withdraws it', async () => {
    vi.mocked(deleteReview).mockResolvedValue(undefined);
    const onOpenChange = renderDialog(
      openReview({
        scores: {
          communication: 4,
          drafting: 3,
          composure: 5,
          sportsmanship: 4,
        },
      }),
    );
    expect(screen.getByTestId('leadership-review-submit')).toHaveTextContent(
      'Update',
    );
    fireEvent.click(screen.getByTestId('leadership-review-withdraw'));

    await waitFor(() => expect(deleteReview).toHaveBeenCalledWith(1, 5, 7));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toast.success).toHaveBeenCalledWith('Review withdrawn');
  });

  it('moderated review is read-only', () => {
    renderDialog(
      openReview({
        scores: {
          communication: 4,
          drafting: 3,
          composure: 5,
          sportsmanship: 4,
        },
        void_kind: 'moderated',
      }),
    );
    expect(screen.getByTestId('leadership-review-moderated')).toHaveTextContent(
      "An organizer removed your review, so it can't be changed.",
    );
    expect(
      screen.queryByTestId('leadership-review-submit'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('leadership-review-withdraw'),
    ).not.toBeInTheDocument();
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled();
    }
  });

  it('shows Submit, not Update, for a withdrawn review', () => {
    renderDialog(
      openReview({
        scores: {
          communication: 4,
          drafting: 3,
          composure: 5,
          sportsmanship: 4,
        },
        void_kind: 'withdrawn',
      }),
    );
    expect(screen.getByTestId('leadership-review-submit')).toHaveTextContent(
      'Submit',
    );
    expect(
      screen.queryByTestId('leadership-review-withdraw'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('leadership-review-resubmit')).toHaveTextContent(
      'Your earlier review no longer counts. Submit again to restore it.',
    );
  });

  it('disables submit when the window closes while open', () => {
    vi.useFakeTimers();
    const now = new Date('2026-11-22T12:00:00Z');
    vi.setSystemTime(now);
    renderDialog(
      pendingReview({
        window_closes_at: new Date(now.getTime() + 45_000).toISOString(),
        scores: {
          communication: 4,
          drafting: 3,
          composure: 5,
          sportsmanship: 4,
        },
      }),
    );
    expect(screen.getByTestId('leadership-review-submit')).toBeEnabled();
    expect(screen.getByTestId('leadership-review-countdown')).toHaveTextContent(
      '<1m left',
    );

    act(() => {
      vi.advanceTimersByTime(45_000);
    });

    expect(screen.getByTestId('leadership-review-submit')).toBeDisabled();
    expect(screen.getByTestId('leadership-review-withdraw')).toBeDisabled();
    expect(screen.getByTestId('leadership-review-closed')).toHaveTextContent(
      'The review window has closed.',
    );
    expect(screen.getByTestId('leadership-review-countdown')).toHaveTextContent(
      'Closed',
    );
  });

  it('maps a 404 on submit to the can-no-longer-be-rated text', async () => {
    vi.mocked(putReview).mockRejectedValue({
      response: { status: 404, data: { detail: 'Not found.' } },
    });
    renderDialog(
      openReview({
        scores: {
          communication: 4,
          drafting: 3,
          composure: 5,
          sportsmanship: 4,
        },
      }),
    );
    submit();
    expect(
      await screen.findByTestId('leadership-review-error'),
    ).toHaveTextContent('This captain can no longer be rated.');
  });

  it('maps review_window_closed', async () => {
    vi.mocked(putReview).mockRejectedValue({
      response: { status: 409, data: { code: 'review_window_closed' } },
    });
    const onOpenChange = renderDialog(
      openReview({
        scores: {
          communication: 4,
          drafting: 3,
          composure: 5,
          sportsmanship: 4,
        },
      }),
    );
    submit();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The review window has closed.');
    expect(alert).toHaveAttribute('data-testid', 'leadership-review-error');
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByTestId('leadership-review-dialog')).toBeInTheDocument();
    expect(logger.warn).toHaveBeenCalledWith('captain review refused', {
      orgId: 1,
      eventId: 5,
      code: 'review_window_closed',
    });
  });

  it('keeps the title clear of the close button', () => {
    renderDialog(openReview());
    const title = screen.getByRole('heading', { name: 'Rate your captain' });
    expect(title.closest('[data-slot="dialog-header"]')).toHaveClass('pr-8');
  });
});
