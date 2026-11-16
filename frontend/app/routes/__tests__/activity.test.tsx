// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render as rtlRender,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  getActivityCredential,
  refreshActivityCredential,
  setActivityRefresher,
} from '~/lib/activity-session';
import type {
  ActivityDraftList,
  ActivityHeroDraftEntry,
} from '~/lib/activity-types';
import { ACTIVITY_OUT_OF_SCOPE } from '~/lib/websocket/WebSocketManager';
import { useActivityViewStore } from '~/store/activityViewStore';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useTournamentStore } from '~/store/tournamentStore';

const mocks = vi.hoisted(() => {
  class ActivityDisabledError extends Error {
    constructor() {
      super('disabled');
      this.name = 'ActivityDisabledError';
    }
  }
  return {
    ActivityDisabledError,
    initializeDiscord: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    setActivityErrorHandlers: vi.fn(),
    fetchActivityDrafts: vi.fn(),
    postActivityView: vi.fn(),
  };
});

vi.mock('~/lib/discord', () => ({
  initializeDiscord: mocks.initializeDiscord,
  releaseDiscordSession: vi.fn(),
  openExternal: vi.fn(),
  ActivityDisabledError: mocks.ActivityDisabledError,
}));
vi.mock('~/components/api/axios', () => ({
  default: { get: mocks.get, post: mocks.post },
  setActivityErrorHandlers: mocks.setActivityErrorHandlers,
}));
vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: mocks.fetchActivityDrafts,
  postActivityView: mocks.postActivityView,
}));
vi.mock('~/lib/hydrateTournament', () => ({
  hydrateTournament: (data: unknown) => data,
}));
vi.mock('~/components/teamdraft/draftModal', () => ({
  DraftModal: ({ activityHeader }: { activityHeader?: ReactNode }) => (
    <div data-testid="team-draft">{activityHeader}</div>
  ),
}));
vi.mock('~/components/herodraft/HeroDraftModal', () => ({
  HeroDraftModal: ({
    draftId,
    activityHeader,
  }: {
    draftId: number;
    activityHeader?: ReactNode;
  }) => (
    <div data-testid="hero-draft" data-draft-id={draftId}>
      {activityHeader}
    </div>
  ),
}));
vi.mock('~/components/bracket/BracketView', () => ({
  BracketView: ({
    tournamentId,
    header,
    openableDraftIds,
    onOpenHeroDraft,
  }: {
    tournamentId: number;
    header?: ReactNode;
    openableDraftIds?: ReadonlySet<number>;
    onOpenHeroDraft?: (id: number) => void;
  }) => (
    <div
      data-testid="bracket"
      data-tournament-id={tournamentId}
      data-openable={[...(openableDraftIds ?? [])].sort().join(',')}
    >
      {header}
      <span role="link" onClick={() => onOpenHeroDraft?.(156)}>
        open 156
      </span>
    </div>
  ),
}));
vi.mock('~/components/ui/dropdown-menu', () => {
  const Pass = ({ children }: { children?: ReactNode }) => (
    <div>{children}</div>
  );
  return {
    DropdownMenu: Pass,
    DropdownMenuContent: Pass,
    DropdownMenuLabel: Pass,
    DropdownMenuTrigger: Pass,
    DropdownMenuSeparator: () => null,
    DropdownMenuItem: ({
      children,
      onSelect,
      ...rest
    }: {
      children?: ReactNode;
      onSelect?: (event: Event) => void;
    }) => (
      <div
        role="menuitem"
        onClick={() => onSelect?.(new Event('select'))}
        {...rest}
      >
        {children}
      </div>
    ),
  };
});

import DraftActivity from '../activity';

const USER = { pk: 1 };

function heroSession(overrides: Record<string, unknown> = {}) {
  return {
    token: 't1',
    kind: 'hero',
    draft_id: 156,
    tournament_id: 12,
    user: USER,
    scope: 'tournament',
    initial_view: { kind: 'hero', id: 156 },
    launch_intent: null,
    site_url: 'https://site.test',
    notice: null,
    ...overrides,
  };
}

function legacySession(overrides: Record<string, unknown> = {}) {
  return {
    token: 'legacy',
    kind: 'hero',
    draft_id: 156,
    tournament_id: 12,
    user: USER,
    ...overrides,
  };
}

function hero(
  id: number,
  overrides: Partial<ActivityHeroDraftEntry> = {},
): ActivityHeroDraftEntry {
  return {
    id,
    game_id: id + 100,
    label: `Game ${id}`,
    state: 'completed',
    status: 'finished',
    involves_me: false,
    role: 'spectator',
    updated_at: '2026-11-16T00:20:00Z',
    ...overrides,
  };
}

function draftList(heroes: ActivityHeroDraftEntry[]): ActivityDraftList {
  return {
    tournament: { id: 12, name: 'Kettle Cup' },
    team_draft: {
      id: 9,
      state: 'completed',
      status: 'finished',
      involves_me: false,
      role: 'spectator',
    },
    hero_drafts: heroes,
    launch_intent: null,
    notice: null,
    site_url: 'https://site.test',
  };
}

function render(ui: ReactNode) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>);
}

function errorHandlers() {
  const calls = mocks.setActivityErrorHandlers.mock.calls;
  const last = calls.filter((c) => c[0] !== null).at(-1);
  return last![0] as { onScopeLost(): void; onDisabled(): void };
}

function postedTriggers(): string[] {
  return mocks.postActivityView.mock.calls
    .map((c) => c[0])
    .filter((b) => b.action === 'view')
    .map((b) => b.trigger);
}

async function heroOnScreen(id: number) {
  await waitFor(() =>
    expect(screen.getByTestId('hero-draft')).toHaveAttribute(
      'data-draft-id',
      String(id),
    ),
  );
}

beforeEach(() => {
  useActivityViewStore.getState().reset();
  useTournamentStore.setState({ autoAdvance: false, live: false });
  useHeroDraftStore.setState({ error: null });
  mocks.get.mockResolvedValue({
    data: { pk: 12, draft: { pk: 9, draft_rounds: [] } },
  });
  mocks.fetchActivityDrafts.mockResolvedValue(
    draftList([hero(156), hero(157)]),
  );
});
afterEach(() => {
  vi.resetAllMocks();
  setActivityRefresher(null);
});

describe('Discord Activity route', () => {
  it('follows the latest team draft pick like the live website view', async () => {
    mocks.initializeDiscord.mockResolvedValue({
      token: 't',
      kind: 'team',
      draft_id: 9,
      tournament_id: 5,
      user: USER,
    });
    render(<DraftActivity />);
    await screen.findByTestId('team-draft');
    expect(useTournamentStore.getState().live).toBe(true);
    expect(useTournamentStore.getState().autoAdvance).toBe(true);
  });

  it('keeps the refresh throttle across re-handshakes', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    await expect(refreshActivityCredential()).resolves.toBe(true);
    await waitFor(() =>
      expect(mocks.initializeDiscord).toHaveBeenCalledTimes(2),
    );
    await expect(refreshActivityCredential()).resolves.toBe(false);
    expect(mocks.initializeDiscord).toHaveBeenCalledTimes(2);
  });

  it('opens the initial hero view with the switcher header', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    expect(screen.getByTestId('activity-header')).toBeInTheDocument();
    expect(mocks.initializeDiscord).toHaveBeenCalledWith({
      force: false,
      currentView: undefined,
    });
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'view',
      to: { kind: 'hero', id: 156 },
      trigger: 'initial',
    });
    expect(getActivityCredential()?.scope).toBe('tournament');
  });

  it('posts the launch intent id with the initial view', async () => {
    mocks.initializeDiscord.mockResolvedValue(
      heroSession({
        launch_intent: { intent_id: 'q1', kind: 'hero', id: 156 },
      }),
    );
    render(<DraftActivity />);
    await heroOnScreen(156);
    expect(mocks.postActivityView).toHaveBeenCalledWith(
      expect.objectContaining({ trigger: 'initial', intent_id: 'q1' }),
    );
  });

  it('fetches the drafts list once right after the first handshake', async () => {
    let resolve!: (value: unknown) => void;
    mocks.initializeDiscord.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    render(<DraftActivity />);
    await Promise.resolve();
    expect(mocks.fetchActivityDrafts).not.toHaveBeenCalled();
    await act(async () => resolve(heroSession()));
    await heroOnScreen(156);
    await waitFor(() =>
      expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(1),
    );
    expect(useActivityViewStore.getState().drafts?.hero_drafts).toHaveLength(2);
  });

  it('switches team → hero → hero → bracket in place with team teardown', async () => {
    mocks.initializeDiscord.mockResolvedValue(
      heroSession({
        kind: 'team',
        draft_id: 9,
        initial_view: { kind: 'team', id: 9 },
      }),
    );
    render(<DraftActivity />);
    await screen.findByTestId('team-draft');
    expect(useTournamentStore.getState().live).toBe(true);

    act(() =>
      useActivityViewStore
        .getState()
        .setView({ kind: 'hero', id: 156 }, 'menu'),
    );
    await heroOnScreen(156);
    expect(screen.queryByTestId('team-draft')).not.toBeInTheDocument();
    expect(useTournamentStore.getState().live).toBe(false);
    expect(useTournamentStore.getState().autoAdvance).toBe(false);

    act(() =>
      useActivityViewStore
        .getState()
        .setView({ kind: 'hero', id: 157 }, 'menu'),
    );
    await heroOnScreen(157);

    act(() =>
      useActivityViewStore.getState().setView({ kind: 'bracket' }, 'menu'),
    );
    expect(await screen.findByTestId('bracket')).toHaveAttribute(
      'data-tournament-id',
      '12',
    );
    expect(screen.queryByTestId('hero-draft')).not.toBeInTheDocument();
    expect(mocks.initializeDiscord).toHaveBeenCalledTimes(1);
  });

  it('refreshes with mode refresh and keeps the current view', async () => {
    mocks.initializeDiscord
      .mockResolvedValueOnce(heroSession())
      .mockResolvedValueOnce(heroSession({ token: 't2', initial_view: null }));
    render(<DraftActivity />);
    await heroOnScreen(156);
    act(() =>
      useActivityViewStore
        .getState()
        .setView({ kind: 'hero', id: 157 }, 'menu'),
    );
    await heroOnScreen(157);

    await expect(refreshActivityCredential()).resolves.toBe(true);
    expect(mocks.initializeDiscord).toHaveBeenLastCalledWith({
      force: true,
      currentView: { kind: 'hero', id: 157 },
    });
    expect(getActivityCredential()?.token).toBe('t2');
    await heroOnScreen(157);
    expect(useActivityViewStore.getState().view).toEqual({
      kind: 'hero',
      id: 157,
    });
  });

  it('shows the turned-off state when a refresh finds Activities disabled', async () => {
    mocks.initializeDiscord
      .mockResolvedValueOnce(heroSession())
      .mockRejectedValueOnce(new mocks.ActivityDisabledError());
    render(<DraftActivity />);
    await heroOnScreen(156);

    await expect(refreshActivityCredential()).resolves.toBe(false);
    expect(
      await screen.findByText('Activities are turned off.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('hero-draft')).not.toBeInTheDocument();
    expect(postedTriggers()).not.toContain('scope_lost');
    expect(useActivityViewStore.getState().view).toEqual({
      kind: 'hero',
      id: 156,
    });
  });

  it('shows the turned-off state when the first handshake finds Activities disabled', async () => {
    mocks.initializeDiscord.mockRejectedValue(
      new mocks.ActivityDisabledError(),
    );
    render(<DraftActivity />);
    expect(
      await screen.findByText('Activities are turned off.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('activity-error')).not.toBeInTheDocument();
  });

  it('shows the turned-off state on an activity_disabled REST failure', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    act(() => errorHandlers().onDisabled());
    expect(
      await screen.findByText('Activities are turned off.'),
    ).toBeInTheDocument();
  });

  it('shows the reopen state when refreshes are exhausted', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    act(() => useActivityViewStore.getState().setTerminal('exhausted'));
    expect(
      await screen.findByText(
        'The Activity lost its connection. Reopen the Activity.',
      ),
    ).toBeInTheDocument();
  });

  it('moves to the bracket when the draft leaves the tournament', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    act(() => errorHandlers().onScopeLost());
    expect(await screen.findByTestId('bracket')).toBeInTheDocument();
    expect(
      screen.getByText('This draft is no longer part of the tournament.'),
    ).toBeInTheDocument();
    expect(postedTriggers()).toContain('scope_lost');
  });

  it('moves to the bracket when the hero socket closes out of scope', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    act(() => useHeroDraftStore.setState({ error: ACTIVITY_OUT_OF_SCOPE }));
    expect(await screen.findByTestId('bracket')).toBeInTheDocument();
    expect(postedTriggers()).toContain('scope_lost');
  });

  it('marks scope lost when a refresh comes back for another tournament', async () => {
    mocks.initializeDiscord
      .mockResolvedValueOnce(heroSession())
      .mockResolvedValueOnce(
        heroSession({ token: 't2', tournament_id: 99, initial_view: null }),
      );
    render(<DraftActivity />);
    await heroOnScreen(156);
    await expect(refreshActivityCredential()).resolves.toBe(true);
    expect(await screen.findByTestId('bracket')).toBeInTheDocument();
    expect(postedTriggers()).toContain('scope_lost');
  });

  it('downgrades to draft scope when a refresh has no scope', async () => {
    mocks.initializeDiscord
      .mockResolvedValueOnce(heroSession())
      .mockResolvedValueOnce(legacySession({ draft_id: 157 }));
    render(<DraftActivity />);
    await heroOnScreen(156);
    await waitFor(() =>
      expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(1),
    );

    await expect(refreshActivityCredential()).resolves.toBe(true);
    await heroOnScreen(157);
    const credential = getActivityCredential();
    expect(credential?.scope).toBe('draft');
    expect(credential?.pin).toEqual({ kind: 'hero', id: 157 });
    expect(screen.queryByTestId('activity-header')).not.toBeInTheDocument();
    expect(
      screen.queryByText('This draft is no longer part of the tournament.'),
    ).not.toBeInTheDocument();
    expect(postedTriggers()).not.toContain('scope_lost');

    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await Promise.resolve();
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(1);
  });

  it('asks a captain before leaving their live hero draft', async () => {
    mocks.initializeDiscord.mockResolvedValue(heroSession());
    mocks.fetchActivityDrafts.mockResolvedValue(
      draftList([
        hero(156, { role: 'captain', status: 'drafting', involves_me: true }),
      ]),
    );
    render(<DraftActivity />);
    await heroOnScreen(156);
    await waitFor(() =>
      expect(useActivityViewStore.getState().drafts).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId('activity-menu-bracket'));
    const dialog = await screen.findByTestId('activity-leave-dialog');
    expect(dialog).toHaveTextContent(
      'Leaving pauses your draft for both teams.',
    );
    fireEvent.click(screen.getByTestId('activity-leave-stay'));
    await waitFor(() =>
      expect(
        screen.queryByTestId('activity-leave-dialog'),
      ).not.toBeInTheDocument(),
    );
    await heroOnScreen(156);
    expect(screen.queryByTestId('bracket')).not.toBeInTheDocument();
  });

  it('opens a hero draft from the bracket in place', async () => {
    mocks.initializeDiscord.mockResolvedValue(
      heroSession({ initial_view: { kind: 'bracket' } }),
    );
    render(<DraftActivity />);
    const bracket = await screen.findByTestId('bracket');
    await waitFor(() =>
      expect(bracket).toHaveAttribute('data-openable', '156,157'),
    );
    expect(screen.getByTestId('activity-header')).toBeInTheDocument();

    fireEvent.click(screen.getByText('open 156'));
    await heroOnScreen(156);
    expect(mocks.postActivityView).toHaveBeenLastCalledWith({
      action: 'view',
      from: { kind: 'bracket' },
      to: { kind: 'hero', id: 156 },
      trigger: 'bracket_match',
    });
  });

  it('renders a draft-scope session without the header or drafts list', async () => {
    mocks.initializeDiscord.mockResolvedValue(legacySession());
    render(<DraftActivity />);
    await heroOnScreen(156);
    expect(screen.queryByTestId('activity-header')).not.toBeInTheDocument();
    expect(getActivityCredential()?.scope).toBe('draft');
    expect(mocks.fetchActivityDrafts).not.toHaveBeenCalled();
  });

  it('shows the connect error when the handshake fails', async () => {
    mocks.initializeDiscord.mockRejectedValue(new Error('nope'));
    render(<DraftActivity />);
    expect(await screen.findByTestId('activity-error')).toBeInTheDocument();
  });
});
