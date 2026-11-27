// @vitest-environment jsdom
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { MmrRequestCard } from '../MmrRequestCard';
import { mmrRequest } from './fixtures';
import { installDomStubs, renderWithClient } from './harness';

vi.mock('~/components/api/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

beforeEach(() => {
  installDomStubs();
  useUserStore.setState({ currentUser: { pk: 9 } as UserType });
});

function renderCard(overrides: Parameters<typeof mmrRequest>[0] = {}) {
  const request = mmrRequest(overrides);
  renderWithClient(<MmrRequestCard request={request} scope={{ org: 3 }} />);
  return request;
}

describe('MmrRequestCard', () => {
  it('shows the member, target and current to requested value', () => {
    renderCard();
    expect(screen.getByText('member')).toBeInTheDocument();
    expect(screen.getByTestId('mmr-card-target-77')).toHaveTextContent(
      'Org MMR · Dota 2',
    );
    expect(screen.getByTestId('mmr-card-mmrs-77')).toHaveTextContent(
      '4200 → 4800',
    );
    expect(screen.getByTestId('mmr-card-note-77')).toHaveTextContent(
      'New season',
    );
    expect(screen.getByTestId('mmr-approve-btn-77')).toBeInTheDocument();
    expect(screen.getByTestId('mmr-reject-btn-77')).toBeInTheDocument();
  });

  it('labels league targets with the league name', () => {
    renderCard({ target: 'league', league: { pk: 5, name: 'Season 4' } });
    expect(screen.getByTestId('mmr-card-target-77')).toHaveTextContent(
      'League · Season 4',
    );
  });

  it('uses the warning style for a change of 20% or more', () => {
    renderCard({ current_mmr: 4000, requested_mmr: 4800 });
    const delta = screen.getByTestId('mmr-card-delta-77');
    expect(delta).toHaveTextContent('+800, 20%');
    expect(delta.className).toContain('text-warning');
  });

  it('keeps the neutral style below 20%', () => {
    renderCard({ current_mmr: 4200, requested_mmr: 4800 });
    expect(screen.getByTestId('mmr-card-delta-77').className).not.toContain(
      'text-warning',
    );
  });

  it('hides actions when the viewer cannot review', () => {
    renderCard({ can_review: false });
    expect(screen.getByTestId('mmr-needs-admin-77')).toHaveTextContent(
      'Needs another admin to review',
    );
    expect(screen.queryByTestId('mmr-approve-btn-77')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mmr-reject-btn-77')).not.toBeInTheDocument();
  });

  it('shows the screenshot and falls back when it fails to load', () => {
    renderCard();
    const thumb = screen.getByTestId('mmr-card-screenshot-77');
    const img = thumb.querySelector('img')!;
    expect(img).toHaveAttribute('src', '/api/mmr-requests/77/screenshot/');
    fireEvent.error(img);
    expect(screen.getByText('Screenshot unavailable')).toBeInTheDocument();
    expect(
      screen.queryByTestId('mmr-card-screenshot-77'),
    ).not.toBeInTheDocument();
  });

  it('shows "Screenshot unavailable" when the file is gone', () => {
    renderCard({
      status: 'cancelled',
      has_screenshot: false,
      screenshot_url: null,
    });
    expect(screen.getByText('Screenshot unavailable')).toBeInTheDocument();
  });

  it('says the screenshot was removed after the retention window', () => {
    renderCard({
      status: 'approved',
      source: 'staff',
      reviewed_at: '2026-11-01T12:00:00Z',
      has_screenshot: false,
      screenshot_url: null,
      screenshot_purged_at: '2026-11-09T03:30:00Z',
    });
    expect(screen.getByTestId('mmr-card-no-screenshot-77')).toHaveTextContent(
      'Screenshot removed after 7 days',
    );
    expect(screen.queryByText('No screenshot')).not.toBeInTheDocument();
  });

  it('says the screenshot was removed when the decision date is unknown', () => {
    renderCard({
      status: 'rejected',
      has_screenshot: false,
      screenshot_url: null,
      screenshot_purged_at: '2026-11-08T03:30:00Z',
    });
    expect(screen.getByTestId('mmr-card-no-screenshot-77')).toHaveTextContent(
      'Screenshot removed',
    );
  });

  it('opens the enlarged screenshot', async () => {
    renderCard();
    fireEvent.click(screen.getByTestId('mmr-card-screenshot-77'));
    expect(
      await screen.findByTestId('mmr-card-screenshot-large-77'),
    ).toBeInTheDocument();
  });

  it('shows the replacing value for a superseded request', () => {
    renderCard({
      status: 'superseded',
      approved_mmr: 5000,
      reviewed_by_username: 'staffy',
      reviewed_at: '2026-11-22T10:00:00Z',
    });
    expect(screen.getByTestId('mmr-card-outcome-77')).toHaveTextContent(
      'Replaced by an official value of 5000 by staffy on 22 Nov 2026',
    );
    expect(screen.queryByTestId('mmr-approve-btn-77')).not.toBeInTheDocument();
  });

  it('shows an adjusted approval and a rejection reason', () => {
    renderCard({ status: 'approved', approved_mmr: 4750 });
    expect(screen.getByTestId('mmr-card-outcome-77')).toHaveTextContent(
      'Approved as 4750',
    );
  });

  it('shows the rejection reason', () => {
    renderCard({ status: 'rejected', rejection_reason: 'Blurry' });
    expect(screen.getByTestId('mmr-card-outcome-77')).toHaveTextContent(
      'Rejected: Blurry',
    );
  });
});
