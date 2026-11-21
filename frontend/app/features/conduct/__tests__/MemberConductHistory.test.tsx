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
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getMemberConduct } from '../api';
import { MemberConductHistory } from '../MemberConductHistory';
import { HISTORY_PAGE_SIZE } from '../schemas';
import { historyItem, memberConduct } from './fixtures';

vi.mock('../api', () => ({ getMemberConduct: vi.fn() }));

const self: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 11,
  canViewOwnConduct: true,
});
const staff: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 2,
  canViewConduct: true,
  canViewConductDetails: true,
});

function renderHistory(
  access: OrgFeatureAccess = self,
  onClose: () => void = () => {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(
    <MemberConductHistory
      orgId={1}
      access={access}
      orgUserPk={7}
      timeZone="UTC"
      onClose={onClose}
    />,
    { wrapper },
  );
}

afterEach(() => {
  vi.mocked(getMemberConduct).mockReset();
});

describe('MemberConductHistory', () => {
  it('shows the counted and weighted basis under the score', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(memberConduct());
    renderHistory();
    expect(await screen.findByTestId('conduct-member-score')).toHaveTextContent(
      '91%',
    );
    expect(screen.getByTestId('conduct-member-basis')).toHaveTextContent(
      'Based on 6 counted events (4.4 after recency weighting)',
    );
    expect(screen.getByTestId('conduct-total-attended')).toHaveTextContent('5');
    expect(screen.queryByTestId('conduct-new-member')).not.toBeInTheDocument();
  });

  it('shows the new-member note and New for a new member', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(
      memberConduct({ status: 'new', counted_events: 1, weighted_events: 1 }),
    );
    renderHistory();
    expect(await screen.findByTestId('conduct-member-score')).toHaveTextContent(
      'New',
    );
    expect(screen.getByTestId('conduct-new-member')).toHaveTextContent(
      'New members are shown as New until they have enough counted events.',
    );
    expect(screen.getByTestId('conduct-member-basis')).toHaveTextContent(
      'Based on 1 counted event (1.0 after recency weighting)',
    );
  });

  it('shows row weights to the member themself', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(memberConduct());
    renderHistory(self);
    expect(
      await screen.findByTestId('conduct-history-row-5'),
    ).toHaveTextContent('Weight 0.62');
  });

  it('shows reasons only when the payload has them', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(
      memberConduct({
        history: [
          historyItem({ event_id: 5 }),
          historyItem({
            event_id: 6,
            outcome: 'no_show',
            source: 'staff',
            reason: 'Never joined voice',
            set_by: { user_pk: 2, username: 'admin' },
          }),
        ],
      }),
    );
    renderHistory(staff);
    expect(
      await screen.findByTestId('conduct-history-row-6'),
    ).toHaveTextContent('Never joined voice');
    expect(screen.getByTestId('conduct-history-row-5')).not.toHaveTextContent(
      'Never joined voice',
    );
    expect(
      screen.queryByTestId('conduct-history-row-5-reason'),
    ).not.toBeInTheDocument();
  });

  it('pages older history', async () => {
    const full = Array.from({ length: HISTORY_PAGE_SIZE }, (_, i) =>
      historyItem({ event_id: 100 + i }),
    );
    vi.mocked(getMemberConduct).mockImplementation(async (_o, _m, page) =>
      memberConduct({
        history: page.offset === 0 ? full : [historyItem({ event_id: 999 })],
      }),
    );
    renderHistory();
    await screen.findByTestId('conduct-history-row-100');
    fireEvent.click(screen.getByTestId('conduct-history-next'));
    expect(
      await screen.findByTestId('conduct-history-row-999'),
    ).toBeInTheDocument();
    expect(getMemberConduct).toHaveBeenLastCalledWith(1, 7, {
      limit: HISTORY_PAGE_SIZE,
      offset: HISTORY_PAGE_SIZE,
    });
    await waitFor(() =>
      expect(screen.getByTestId('conduct-history-prev')).toBeEnabled(),
    );
  });

  it('shows each outcome source to the member themself', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(memberConduct());
    renderHistory(self);
    const row = await screen.findByTestId('conduct-history-row-5');
    expect(row).toHaveTextContent('Ready check');
    expect(
      within(row).queryByTestId('conduct-history-set-by'),
    ).not.toBeInTheDocument();
  });

  it('shows who set an outcome when the payload carries it', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(
      memberConduct({
        history: [
          historyItem({
            event_id: 6,
            outcome: 'no_show',
            source: 'staff',
            set_by: { user_pk: 2, username: 'admin' },
          }),
        ],
      }),
    );
    renderHistory(staff);
    const row = await screen.findByTestId('conduct-history-row-6');
    expect(row).toHaveTextContent('Staff');
    expect(within(row).getByTestId('conduct-history-set-by')).toHaveTextContent(
      'Set by admin',
    );
  });

  it('calls onClose from the close button', async () => {
    vi.mocked(getMemberConduct).mockResolvedValue(memberConduct());
    const onClose = vi.fn();
    renderHistory(self, onClose);
    await screen.findByTestId('conduct-member-score');
    fireEvent.click(screen.getByTestId('conduct-history-close'));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
