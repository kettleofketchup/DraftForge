// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getMemberLeadership } from '../api';
import { MemberLeadershipPanel } from '../MemberLeadershipPanel';
import {
  CAPTAIN,
  eventAggregate,
  memberLeadership,
  moderationReview,
} from './fixtures';

const { logger } = vi.hoisted(() => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));
vi.mock('../api', () => ({ getMemberLeadership: vi.fn() }));

const member: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 11,
  leadershipUnlocked: true,
  leadershipMember: true,
});

function renderPanel({
  access = member,
  own = true,
  onClose = () => {},
}: {
  access?: OrgFeatureAccess;
  own?: boolean;
  onClose?: () => void;
} = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(
    <MemberLeadershipPanel
      orgId={1}
      orgUserPk={7}
      own={own}
      timeZone="UTC"
      access={access}
      onClose={onClose}
    />,
    { wrapper },
  );
}

afterEach(() => {
  vi.mocked(getMemberLeadership).mockReset();
  logger.error.mockReset();
  logger.warn.mockReset();
});

describe('MemberLeadershipPanel', () => {
  it('shows released summary, traits and per-event averages for the captain', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(memberLeadership());
    const onClose = vi.fn();
    renderPanel({ onClose });

    expect(
      await screen.findByTestId('leadership-member-rating'),
    ).toHaveTextContent('4.1');
    expect(screen.getByTestId('leadership-member-reviews')).toHaveTextContent(
      '6 released reviews',
    );
    expect(
      screen.getByTestId('leadership-member-points-all'),
    ).toHaveTextContent('42');
    expect(
      screen.getByTestId('leadership-member-points-month'),
    ).toHaveTextContent('13');
    const trait = screen.getByTestId('leadership-member-trait-communication');
    expect(trait).toHaveTextContent('Communication');
    expect(trait).toHaveTextContent('4.0');
    expect(screen.getByTestId('leadership-member-own-note')).toHaveTextContent(
      'Who rated you is never shown.',
    );

    const row = screen.getByTestId('leadership-member-event-5');
    expect(row).toHaveTextContent('Inhouse night');
    expect(row).toHaveTextContent('Team alice');
    expect(row).toHaveTextContent('1st');
    expect(row).toHaveTextContent('+8 rating points');
    expect(row).toHaveTextContent('3 reviews');
    expect(row).toHaveTextContent('Communication');
    expect(screen.getByRole('link', { name: 'Inhouse night' })).toHaveAttribute(
      'href',
      '/events/5',
    );
    expect(
      screen.queryByTestId('leadership-member-new'),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('leadership-member-close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('hides per-trait detail for a released event with fewer than 3 reviews', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(
      memberLeadership({
        events: [eventAggregate({ reviews: null, traits: null })],
      }),
    );
    renderPanel();
    const row = await screen.findByTestId('leadership-member-event-5');
    expect(row).toHaveTextContent(
      'Fewer than 3 reviews: per-trait detail hidden.',
    );
    expect(row).not.toHaveTextContent('Communication');
  });

  it('marks unreleased events for admins', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(
      memberLeadership({
        events: [
          eventAggregate({
            released: false,
            reviews: 1,
            rating: null,
            traits: null,
            captain_rating_points: null,
          }),
        ],
      }),
    );
    renderPanel({
      own: false,
      access: makeOrgFeatureAccess({
        viewerPk: 2,
        leadershipUnlocked: true,
        canManageLeadership: true,
        leadershipCanOpenOthers: true,
      }),
    });
    expect(
      await screen.findByTestId('leadership-member-event-5-unreleased'),
    ).toHaveTextContent('Not released');
    expect(screen.getByTestId('leadership-member-event-5')).toHaveTextContent(
      'Only admins see this until the window closes with enough reviews.',
    );
    expect(
      screen.queryByTestId('leadership-member-own-note'),
    ).not.toBeInTheDocument();
  });

  it('shows the new badge and the unreleased empty state', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(
      memberLeadership({
        status: 'new',
        reviews: 0,
        rating: null,
        traits: memberLeadership().traits.map((t) => ({ ...t, rating: null })),
        events: [],
      }),
    );
    renderPanel();
    expect(
      await screen.findByTestId('leadership-member-new'),
    ).toHaveTextContent('New');
    expect(screen.getByText(/Not enough released reviews/)).toBeInTheDocument();
    expect(
      screen.getByTestId('leadership-member-unreleased'),
    ).toHaveTextContent('No released ratings yet.');
    expect(screen.getByTestId('leadership-member-rating')).toHaveTextContent(
      '—',
    );
    expect(
      screen.getByTestId('leadership-member-trait-drafting'),
    ).toHaveTextContent('—');
  });

  it('renders no events block for another member', async () => {
    const { events: _events, ...rest } = memberLeadership();
    vi.mocked(getMemberLeadership).mockResolvedValue(rest);
    renderPanel({ own: false });
    await screen.findByTestId('leadership-member-rating');
    expect(screen.queryByText('Rated events')).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('leadership-member-event-5'),
    ).not.toBeInTheDocument();
  });

  it('never renders a rater name', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(memberLeadership());
    const { container } = renderPanel();
    await screen.findByTestId('leadership-member-event-5');
    const rater = moderationReview().rater!;
    expect(container).not.toHaveTextContent(rater.username);
    for (const name of [
      rater.nickname,
      rater.discordNickname,
      rater.guildNickname,
    ]) {
      if (name) expect(container).not.toHaveTextContent(name);
    }
  });

  it('labels the event list Rated events and notes what the totals include', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(memberLeadership());
    renderPanel();
    expect(await screen.findByText('Rated events')).toBeInTheDocument();
    expect(screen.queryByText(/Points history/i)).not.toBeInTheDocument();
    expect(
      screen.getByTestId('leadership-member-points-note'),
    ).toHaveTextContent(
      'Totals include events still in their review window or without enough reviews.',
    );
  });

  it('shows the admins-only message on a 403 not_permitted', async () => {
    vi.mocked(getMemberLeadership).mockRejectedValue({
      response: { status: 403, data: { code: 'not_permitted' } },
    });
    renderPanel({ own: false });
    expect(
      await screen.findByTestId('leadership-member-forbidden'),
    ).toHaveTextContent("Only org admins can see other captains' details.");
    await waitFor(() => expect(logger.warn).toHaveBeenCalled());
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('logs and shows an error for other failures', async () => {
    vi.mocked(getMemberLeadership).mockRejectedValue({
      response: { status: 500, data: {} },
    });
    renderPanel();
    expect(
      await screen.findByTestId('leadership-member-error'),
    ).toBeInTheDocument();
    await waitFor(() => expect(logger.error).toHaveBeenCalled());
  });

  it('wraps long names', async () => {
    const long = 'x'.repeat(64);
    vi.mocked(getMemberLeadership).mockResolvedValue(
      memberLeadership({ member: { ...CAPTAIN, username: long } }),
    );
    renderPanel();
    const name = await screen.findByRole('heading', { name: long });
    expect(name).toHaveClass('break-words');
    expect(name).not.toHaveClass('wrap-anywhere');
  });
});
