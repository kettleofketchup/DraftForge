// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getMemberBreakdown } from '../api';
import { MemberBreakdown } from '../MemberBreakdown';
import type { ContributionEntry } from '../schemas';

vi.mock('../api', () => ({
  getMemberBreakdown: vi.fn(),
}));

afterEach(() => {
  vi.mocked(getMemberBreakdown).mockReset();
});

const access = makeOrgFeatureAccess({
  viewerPk: 5,
  canViewContributions: true,
  canViewContributors: true,
});

function entry(
  pk: number,
  kind: ContributionEntry['kind'],
  points: number,
): ContributionEntry {
  return {
    pk,
    kind,
    points,
    event: { id: 4, name: 'Weekly Cup' },
    event_name: 'Weekly Cup',
    occurred_at: '2026-11-01T12:00:00Z',
  };
}

function renderBreakdown() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  return render(
    <MemberBreakdown
      orgId={7}
      orgUserPk={11}
      period="all"
      timeZone="America/New_York"
      access={access}
      onClose={() => {}}
    />,
    { wrapper },
  );
}

describe('MemberBreakdown', () => {
  it('shows a voided promotion point and its restore with signed points', async () => {
    vi.mocked(getMemberBreakdown).mockResolvedValue({
      member: {
        org_user_pk: 11,
        user_pk: 9,
        username: 'alice',
        nickname: null,
        avatarUrl: null,
      },
      totals: { all_time: 1, this_month: 1 },
      monthly: [],
      entries: [
        entry(1, 'promo_message', 1),
        entry(2, 'promo_void', -1),
        entry(3, 'promo_restore', 1),
      ],
    });
    renderBreakdown();
    const voided = await screen.findByTestId('contributions-entry-2');
    expect(voided).toHaveTextContent('Promotion point voided');
    expect(voided).toHaveTextContent('-1');
    expect(voided).not.toHaveTextContent('+');
    const restored = screen.getByTestId('contributions-entry-3');
    expect(restored).toHaveTextContent('Promotion point restored');
    expect(restored).toHaveTextContent('+1');
    expect(screen.getByTestId('contributions-entry-1')).toHaveTextContent(
      'Promotion message',
    );
  });
});
