// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { ZodError } from 'zod';

import fixture from '~/components/api/__tests__/fixtures/signup-history-page.json';
import {
  signupHistoryPageSchema,
  type HistorySubject,
  type SignupHistoryEntry,
  type SignupHistoryPage,
  type SignupSnapshot,
} from '~/components/events/schemas';
import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';

const { api, logger } = vi.hoisted(() => ({
  api: { getEventSignupHistory: vi.fn() },
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));

import {
  SignupHistorySection,
  type HistoryMemberOption,
} from '../SignupHistorySection';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const EVENT_ID = 7;
const FIXTURE = signupHistoryPageSchema.parse(fixture);

const SUBJECT: HistorySubject = {
  user_id: 21,
  username: 'hist_member',
  nickname: 'HistMember',
  discordNickname: null,
  guildNickname: null,
  avatarUrl: 'https://cdn.discordapp.com/avatars/21/member.png',
  discord_id: '900000000000000021',
};

const OTHER: HistorySubject = {
  ...SUBJECT,
  user_id: 22,
  username: 'hist_other',
  nickname: 'HistOther',
  avatarUrl: null,
  discord_id: null,
};

function snap(overrides: Partial<SignupSnapshot> = {}): SignupSnapshot {
  return {
    status: 'rsvp',
    commitment: 'main',
    rsvp_class: 'standard',
    signed_up_at: '2026-11-19T18:00:00Z',
    line_seq: 1,
    waitlist_position: null,
    event_team_id: null,
    extra: {},
    ...overrides,
  };
}

function entry(
  id: number,
  overrides: Partial<SignupHistoryEntry> = {},
): SignupHistoryEntry {
  return {
    id,
    occurred_at: '2026-11-20T18:00:00Z',
    action: 'signed_up',
    subject: SUBJECT,
    actor: {
      user_id: SUBJECT.user_id,
      username: SUBJECT.username,
      nickname: SUBJECT.nickname,
      discordNickname: null,
      guildNickname: null,
      avatarUrl: SUBJECT.avatarUrl,
      role: 'member',
    },
    means: 'web',
    on_behalf: false,
    reason: '',
    before: null,
    after: snap(),
    rules_overridden: [],
    caused_by: null,
    ...overrides,
  };
}

function page(
  results: SignupHistoryEntry[],
  next: string | null = null,
): SignupHistoryPage {
  return { count: results.length, next, previous: null, results };
}

const NEXT = 'http://testserver/api/events/7/signup-history/?cursor=abc%7C2';

function makeClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

type SectionProps = Parameters<typeof SignupHistorySection>[0];

const MEMBER_OPTIONS: HistoryMemberOption[] = [
  { user_id: SUBJECT.user_id!, user: SUBJECT },
  { user_id: OTHER.user_id!, user: OTHER },
];

function renderSection(
  props: Partial<SectionProps> = {},
  client: QueryClient = makeClient(),
) {
  const base = {
    eventId: EVENT_ID,
    isAdmin: true,
    memberOptions: MEMBER_OPTIONS,
    ...props,
  } as SectionProps;
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={client}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
  const view = render(wrap(<SignupHistorySection {...base} />));
  return {
    client,
    ...view,
    rerenderWith: (next: Partial<SectionProps>) =>
      view.rerender(
        wrap(
          <SignupHistorySection {...({ ...base, ...next } as SectionProps)} />,
        ),
      ),
  };
}

const lastCall = () => api.getEventSignupHistory.mock.calls.at(-1);
const row = (id: number) => screen.getByTestId(`signup-history-row-${id}`);
const activeKey = (client: QueryClient) =>
  client
    .getQueryCache()
    .findAll({ type: 'active' })
    .map((q) => q.queryKey);
const historyQueries = (client: QueryClient) =>
  client
    .getQueryCache()
    .findAll({ queryKey: ['event-signup-history', EVENT_ID] });

function choose(testId: string, label: string) {
  fireEvent.pointerDown(screen.getByTestId(testId), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('option', { name: label }));
}

let restoreViewport: (() => void) | null = null;

beforeEach(() => {
  vi.clearAllMocks();
  useUserStore.setState({
    currentUser: { pk: 1, username: 'staff' } as UserType,
  });
});

afterEach(() => {
  cleanup();
  restoreViewport?.();
  restoreViewport = null;
});

describe('SignupHistorySection', () => {
  it('renders rows with actor, means and reason', async () => {
    restoreViewport = setViewportWidth(1280);
    api.getEventSignupHistory.mockResolvedValue(FIXTURE);
    renderSection();

    const staffRow = await screen.findByTestId('signup-history-row-2');
    const systemRow = row(3);
    expect(
      within(staffRow).getByTestId('signup-history-reason').textContent,
    ).toContain('Vouched for by staff');
    expect(
      within(staffRow).getByTestId('signup-history-means').textContent,
    ).toBe('Staff');
    expect(
      within(systemRow).getByTestId('signup-history-means').textContent,
    ).toBe('System');
    expect(
      within(staffRow).getByTestId('signup-history-actor').textContent,
    ).toContain(DisplayName(FIXTURE.results[1].actor));
    expect(
      within(systemRow).getByTestId('signup-history-actor').textContent,
    ).toContain('System');
    expect(within(staffRow).getByText('Added by staff')).toBeTruthy();
    expect(
      within(staffRow).getByTestId('signup-history-actor').textContent,
    ).toContain('on behalf');
    expect(api.getEventSignupHistory).toHaveBeenCalledWith(EVENT_ID, {});
  });

  it('shows the rules chip only when rules were overridden', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([
        entry(2, { rules_overridden: ['max_players', 'min_mmr'] }),
        entry(1),
      ]),
    );
    renderSection();
    const chip = await within(
      await screen.findByTestId('signup-history-row-2'),
    ).findByTestId('signup-history-rules-chip');
    expect(chip.textContent).toBe('Overrode 2 rules');
    expect(
      within(row(1)).queryByTestId('signup-history-rules-chip'),
    ).toBeNull();
  });

  it('locks the member to fixedUser and hides the member select', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    renderSection({ fixedUser: SUBJECT, memberOptions: undefined });
    await screen.findByTestId('signup-history-row-1');
    expect(screen.queryByTestId('signup-history-member-filter')).toBeNull();
    expect(screen.getByTestId('signup-history-action-filter')).toBeTruthy();
    expect(lastCall()).toEqual([EVENT_ID, { user: SUBJECT.user_id }]);
  });

  it('filters by member and action, and "All" clears back to {}', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    const { client } = renderSection();
    await screen.findByTestId('signup-history-row-1');

    choose('signup-history-member-filter', DisplayName(OTHER));
    await waitFor(() =>
      expect(lastCall()).toEqual([EVENT_ID, { user: OTHER.user_id }]),
    );

    choose('signup-history-action-filter', 'Withdrew');
    await waitFor(() =>
      expect(lastCall()).toEqual([
        EVENT_ID,
        { user: OTHER.user_id, action: 'withdrew' },
      ]),
    );

    choose('signup-history-member-filter', 'All members');
    choose('signup-history-action-filter', 'All actions');
    await waitFor(() =>
      expect(activeKey(client)).toEqual([
        ['event-signup-history', EVENT_ID, {}],
      ]),
    );
  });

  it('clear filters resets both selects', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    const { client } = renderSection();
    await screen.findByTestId('signup-history-row-1');
    expect(screen.queryByTestId('signup-history-clear-filters')).toBeNull();
    choose('signup-history-action-filter', 'Withdrew');
    await waitFor(() =>
      expect(lastCall()).toEqual([EVENT_ID, { action: 'withdrew' }]),
    );
    fireEvent.click(screen.getByTestId('signup-history-clear-filters'));
    await waitFor(() =>
      expect(activeKey(client)).toEqual([
        ['event-signup-history', EVENT_ID, {}],
      ]),
    );
    expect(screen.queryByTestId('signup-history-clear-filters')).toBeNull();
  });

  it('Load more appends every row without client pagination', async () => {
    const first = Array.from({ length: 50 }, (_, i) => entry(100 - i));
    const second = Array.from({ length: 50 }, (_, i) => entry(50 - i));
    api.getEventSignupHistory
      .mockResolvedValueOnce(page(first, NEXT))
      .mockResolvedValueOnce(page(second));
    renderSection();
    await screen.findByTestId('signup-history-row-100');
    expect(screen.queryByTestId('signup-history-row-50')).toBeNull();

    fireEvent.click(screen.getByTestId('signup-history-load-more'));
    await screen.findByTestId('signup-history-row-1');
    expect(lastCall()).toEqual([EVENT_ID, { cursor: 'abc|2' }]);
    expect(
      document.querySelectorAll('[data-testid^="signup-history-row-"]'),
    ).toHaveLength(100);
    expect(screen.queryByTestId('data-table-next')).toBeNull();
    expect(screen.queryByTestId('signup-history-load-more')).toBeNull();
  });

  it('marks the table busy and disables Load more while placeholder data shows', async () => {
    let resolveFiltered: (p: SignupHistoryPage) => void = () => undefined;
    api.getEventSignupHistory
      .mockResolvedValueOnce(page([entry(2), entry(1)], NEXT))
      .mockImplementationOnce(
        () => new Promise((resolve) => (resolveFiltered = resolve)),
      );
    renderSection();
    await screen.findByTestId('signup-history-row-2');
    const table = screen.getByTestId('signup-history-table');
    expect(table.getAttribute('aria-busy')).toBe('false');

    choose('signup-history-action-filter', 'Withdrew');
    await waitFor(() => expect(table.getAttribute('aria-busy')).toBe('true'));
    expect(
      (screen.getByTestId('signup-history-load-more') as HTMLButtonElement)
        .disabled,
    ).toBe(true);

    await act(async () => resolveFiltered(page([entry(5)])));
    await waitFor(() => expect(table.getAttribute('aria-busy')).toBe('false'));
    expect(screen.getByTestId('signup-history-row-5')).toBeTruthy();
  });

  it('renders "Details unavailable" for an entry with a null side', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([entry(1, { before: snap(), after: null })]),
    );
    renderSection();
    const r = await screen.findByTestId('signup-history-row-1');
    expect(within(r).getByText('Details unavailable')).toBeTruthy();
  });

  it('shows secondary columns on wide screens and a md:hidden meta line', async () => {
    restoreViewport = setViewportWidth(1280);
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    renderSection();
    await screen.findByTestId('signup-history-row-1');
    for (const name of ['When', 'Actor', 'Means']) {
      expect(screen.getByRole('columnheader', { name })).toBeTruthy();
    }
    expect(screen.getByTestId('signup-history-meta').className).toContain(
      'md:hidden',
    );
  });

  it('compact hides when/actor/means and always shows the meta line', async () => {
    restoreViewport = setViewportWidth(1280);
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    renderSection({
      compact: true,
      fixedUser: SUBJECT,
      memberOptions: undefined,
    });
    const r = await screen.findByTestId('signup-history-row-1');
    for (const name of ['When', 'Actor', 'Means']) {
      expect(screen.queryByRole('columnheader', { name })).toBeNull();
    }
    expect(r.querySelectorAll('td')).toHaveLength(1);
    const meta = within(r).getByTestId('signup-history-meta');
    expect(meta.className).not.toContain('md:hidden');
    expect(
      within(meta).getByTestId('signup-history-meta-means').textContent,
    ).toBe('Web');
  });

  it('renders nothing and requests nothing when not staff', async () => {
    const { container } = renderSection({ isAdmin: false });
    await act(async () => undefined);
    expect(container.innerHTML).toBe('');
    expect(api.getEventSignupHistory).not.toHaveBeenCalled();
  });

  it('drops rows and cache when the viewer stops being staff', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    const view = renderSection();
    await screen.findByTestId('signup-history-row-1');
    expect(historyQueries(view.client)).toHaveLength(1);

    view.rerenderWith({ isAdmin: false });
    await waitFor(() => expect(historyQueries(view.client)).toHaveLength(0));
    expect(screen.queryByTestId('signup-history-row-1')).toBeNull();
  });

  it('drops rows and cache when the user signs out', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    const view = renderSection();
    await screen.findByTestId('signup-history-row-1');

    act(() => {
      useUserStore.setState({ currentUser: {} as UserType });
    });
    await waitFor(() => expect(historyQueries(view.client)).toHaveLength(0));
    expect(screen.queryByTestId('signup-history-section')).toBeNull();
  });

  it('renders the payload avatarUrl', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([entry(1)]));
    renderSection();
    const r = await screen.findByTestId('signup-history-row-1');
    const srcs = Array.from(r.querySelectorAll('img')).map((i) =>
      i.getAttribute('src'),
    );
    expect(srcs).toContain(SUBJECT.avatarUrl);
  });

  it('shows the empty message, with a member variant', async () => {
    api.getEventSignupHistory.mockResolvedValue(page([]));
    renderSection();
    expect(
      (await screen.findByTestId('signup-history-empty')).textContent,
    ).toBe('No changes recorded yet.');
    cleanup();
    renderSection({ fixedUser: SUBJECT, memberOptions: undefined });
    expect(
      (await screen.findByTestId('signup-history-empty')).textContent,
    ).toContain('No changes recorded for this member.');
  });

  it('logs and shows an inline error when the load fails', async () => {
    const error = Object.assign(new Error('boom'), {
      response: { status: 500, data: { detail: 'Server exploded' } },
    });
    api.getEventSignupHistory.mockRejectedValue(error);
    renderSection();
    expect(
      (await screen.findByTestId('signup-history-error')).textContent,
    ).toContain('Server exploded');
    expect(logger.error).toHaveBeenCalledWith(
      'signup_history_load_failed',
      expect.objectContaining({ eventId: EVENT_ID, error, contract: false }),
    );
  });

  it('flags a response that fails the schema as a contract bug', async () => {
    const error = new ZodError([]);
    api.getEventSignupHistory.mockRejectedValue(error);
    renderSection();
    await screen.findByTestId('signup-history-error');
    expect(logger.error).toHaveBeenCalledWith(
      'signup_history_load_failed',
      expect.objectContaining({ contract: true }),
    );
  });
});

describe('SignupHistorySection diff rendering', () => {
  it('renders a status change as two badges with sr-only "changed to"', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([
        entry(1, {
          action: 'approved',
          before: snap({ status: 'waitlisted', waitlist_position: 1 }),
          after: snap({ status: 'approved' }),
        }),
      ]),
    );
    renderSection();
    const diff = within(
      await screen.findByTestId('signup-history-row-1'),
    ).getByTestId('signup-history-diff');
    const badges = diff.querySelectorAll('[data-slot="badge"]');
    expect(Array.from(badges).map((b) => b.textContent)).toEqual([
      'Waitlisted',
      'Approved',
    ]);
    const sr = within(diff).getByText('changed to');
    expect(sr.className).toContain('sr-only');
    expect(diff.textContent).toContain('Left the waitlist');
  });

  it('renders commitment and waitlist text', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([
        entry(2, {
          action: 'switched_commitment',
          before: snap({ commitment: 'main' }),
          after: snap({ commitment: 'maybe' }),
        }),
        entry(1, {
          action: 'waitlisted',
          after: snap({ status: 'waitlisted', waitlist_position: 2 }),
        }),
      ]),
    );
    renderSection();
    const changed = within(
      await screen.findByTestId('signup-history-row-2'),
    ).getByTestId('signup-history-diff');
    expect(changed.textContent).toContain('Main → Maybe');
    expect(
      within(row(1)).getByTestId('signup-history-diff').textContent,
    ).toContain('#2 on the waitlist');
  });

  it('phrases a promotion by its loaded cause, else "automatic"', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([
        entry(3, {
          action: 'promoted',
          caused_by: 2,
          before: snap({ status: 'waitlisted', waitlist_position: 1 }),
          after: snap({ status: 'rsvp' }),
        }),
        entry(2, {
          action: 'withdrew',
          subject: OTHER,
          before: snap(),
          after: snap({ status: 'dropped' }),
        }),
        entry(1, {
          action: 'promoted',
          caused_by: 999,
          before: snap({ status: 'waitlisted', waitlist_position: 1 }),
          after: snap({ status: 'rsvp' }),
        }),
      ]),
    );
    renderSection();
    const linked = await within(
      await screen.findByTestId('signup-history-row-3'),
    ).findByTestId('signup-history-cause');
    expect(linked.textContent).toBe(`after ${DisplayName(OTHER)} withdrew`);
    expect(within(row(1)).getByTestId('signup-history-cause').textContent).toBe(
      'automatic',
    );
    expect(within(row(2)).queryByTestId('signup-history-cause')).toBeNull();
  });

  it('marks the original sign-up only once the last page is loaded', async () => {
    api.getEventSignupHistory
      .mockResolvedValueOnce(
        page(
          [
            entry(4, {
              action: 'resigned_up',
              before: snap({ status: 'dropped' }),
              after: snap({ line_seq: 9 }),
            }),
            entry(3, {
              action: 'withdrew',
              before: snap(),
              after: snap({ status: 'dropped' }),
            }),
          ],
          NEXT,
        ),
      )
      .mockResolvedValueOnce(
        page([
          entry(2, { action: 'signed_up' }),
          entry(1, {
            action: 'backfilled',
            after: snap({ status: 'cancelled' }),
          }),
        ]),
      );
    renderSection({ fixedUser: SUBJECT, memberOptions: undefined });
    await screen.findByTestId('signup-history-row-4');
    expect(screen.queryByTestId('signup-history-original')).toBeNull();

    fireEvent.click(screen.getByTestId('signup-history-load-more'));
    await screen.findByTestId('signup-history-row-2');
    const markers = screen.getAllByTestId('signup-history-original');
    expect(markers).toHaveLength(1);
    expect(within(row(2)).getByTestId('signup-history-original')).toBe(
      markers[0],
    );
  });

  it('does not mark an original sign-up in the unfiltered view', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([entry(1, { action: 'signed_up' })]),
    );
    renderSection();
    await screen.findByTestId('signup-history-row-1');
    expect(screen.queryByTestId('signup-history-original')).toBeNull();
  });

  it('shows the merge note instead of a diff for a discarded duplicate', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([
        entry(1, {
          action: 'account_merged',
          before: snap({
            status: 'waitlisted',
            extra: { discarded_duplicate: true, from_user_id: 4 },
          }),
          after: snap({ status: 'approved' }),
        }),
      ]),
    );
    renderSection();
    const r = await screen.findByTestId('signup-history-row-1');
    const diff = within(r).getByTestId('signup-history-diff');
    expect(diff.textContent).toBe(
      'Duplicate sign-up from merged account discarded; kept current sign-up',
    );
    expect(diff.querySelectorAll('[data-slot="badge"]')).toHaveLength(0);
    expect(within(r).getByText('Merged from another account')).toBeTruthy();
  });

  it('renders the reason box and extra notes', async () => {
    api.getEventSignupHistory.mockResolvedValue(
      page([
        entry(1, {
          action: 'staff_added',
          reason: 'Covering for a late player',
          actor: { ...FIXTURE.results[1].actor },
          on_behalf: true,
          after: snap({ extra: { staff_power: true, mmr_override: 4200 } }),
        }),
      ]),
    );
    renderSection();
    const r = await screen.findByTestId('signup-history-row-1');
    expect(
      within(r).getByTestId('signup-history-reason').textContent,
    ).toContain('Covering for a late player');
    const notes = within(r)
      .getAllByTestId('signup-history-note')
      .map((n) => n.textContent);
    expect(notes).toEqual(['Staff override on own sign-up', 'MMR set to 4200']);
  });
});
