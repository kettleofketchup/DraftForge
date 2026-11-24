// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { useState } from 'react';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';

import type {
  EventSignupType,
  HistorySubject,
} from '~/components/events/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';

const { api } = vi.hoisted(() => ({
  api: { getEventSignupHistory: vi.fn() },
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import {
  SignupHistoryButton,
  SignupHistorySheet,
  historySubjectFor,
} from '../SignupHistorySheet';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const EVENT_ID = 7;

const SUBJECT: HistorySubject = {
  user_id: 21,
  username: 'hist_member',
  nickname: 'HistMember',
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
  discord_id: null,
};

function Harness({ isAdmin }: { isAdmin: boolean }) {
  const [user, setUser] = useState<HistorySubject | null>(null);
  return (
    <>
      <SignupHistoryButton user={SUBJECT} onClick={() => setUser(SUBJECT)} />
      <SignupHistorySheet
        eventId={EVENT_ID}
        eventTimezone="UTC"
        isAdmin={isAdmin}
        user={user}
        onOpenChange={(open) => !open && setUser(null)}
      />
    </>
  );
}

function renderHarness(isAdmin = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Harness isAdmin={isAdmin} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getEventSignupHistory.mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  useUserStore.setState({
    currentUser: { pk: 1, username: 'staff' } as UserType,
  } as never);
});

afterEach(() => cleanup());

describe('SignupHistoryButton', () => {
  it('is keyed by user pk and names the member', () => {
    renderHarness();
    const btn = screen.getByTestId('signup-history-btn-user-21');
    expect(btn).toHaveAccessibleName('View history for HistMember');
    expect(btn.className).toContain('min-h-11');
  });
});

describe('SignupHistorySheet', () => {
  it('opens a sheet filtered to the member', async () => {
    renderHarness();
    expect(screen.queryByTestId('signup-history-sheet')).toBeNull();
    fireEvent.click(screen.getByTestId('signup-history-btn-user-21'));

    const sheet = await screen.findByTestId('signup-history-sheet');
    expect(within(sheet).getByText('Sign-up history')).toBeTruthy();
    expect(within(sheet).getByText('HistMember')).toBeTruthy();
    expect(within(sheet).queryByTestId('signup-history-member-filter')).toBe(
      null,
    );
    await waitFor(() =>
      expect(api.getEventSignupHistory).toHaveBeenCalledWith(EVENT_ID, {
        user: 21,
      }),
    );
  });

  it('renders nothing and fetches nothing for non-staff', async () => {
    renderHarness(false);
    fireEvent.click(screen.getByTestId('signup-history-btn-user-21'));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('signup-history-sheet')).toBeNull();
    expect(api.getEventSignupHistory).not.toHaveBeenCalled();
  });
});

describe('historySubjectFor', () => {
  const signup = {
    id: 3,
    user: 21,
    username: 'hist_member',
    user_data: {
      pk: 21,
      username: 'hist_member',
      nickname: 'FromSignup',
      avatar: null,
      discordId: '900',
      discordNickname: 'disc',
      positions: null,
      steam_account_id: null,
      avatarUrl: 'https://cdn.example/a.png',
    },
  } as unknown as EventSignupType;

  it('builds the subject from the signup payload', () => {
    expect(historySubjectFor(signup)).toEqual({
      user_id: 21,
      username: 'hist_member',
      nickname: 'FromSignup',
      discordNickname: 'disc',
      guildNickname: null,
      avatarUrl: 'https://cdn.example/a.png',
      discord_id: '900',
    });
  });

  it('prefers the resolved user', () => {
    const user = {
      pk: 21,
      username: 'hist_member',
      nickname: 'Resolved',
      guildNickname: 'Guild',
    } as UserType;
    expect(historySubjectFor(signup, user)).toMatchObject({
      user_id: 21,
      nickname: 'Resolved',
      guildNickname: 'Guild',
    });
  });
});
