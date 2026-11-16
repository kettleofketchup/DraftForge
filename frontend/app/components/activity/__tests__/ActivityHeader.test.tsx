// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render as rtlRender,
  screen,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KickedOverlay } from '~/components/herodraft/HeroDraftModal';
import { TooltipProvider } from '~/components/ui/tooltip';
import { setActivityCredential } from '~/lib/activity-session';
import type {
  ActivityDraftList,
  ActivityHeroDraftEntry,
} from '~/lib/activity-types';
import { useActivityViewStore } from '~/store/activityViewStore';
import { ActivityHeader } from '../ActivityHeader';
import { useLeaveGuard } from '../LeaveDraftConfirm';

const mocks = vi.hoisted(() => ({
  openExternal: vi.fn<(url: string) => Promise<boolean>>(),
  postActivityView: vi.fn(),
}));

vi.mock('~/lib/discord', () => ({
  openExternal: mocks.openExternal,
}));
vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: vi.fn(),
  postActivityView: mocks.postActivityView,
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

function hero(
  id: number,
  overrides: Partial<ActivityHeroDraftEntry> = {},
): ActivityHeroDraftEntry {
  return {
    id,
    game_id: id + 100,
    label: `Winners R1 · Game ${id}`,
    state: 'drafting',
    status: 'drafting',
    involves_me: false,
    role: 'spectator',
    updated_at: '2026-11-16T00:20:00Z',
    ...overrides,
  };
}

function drafts(heroes: ActivityHeroDraftEntry[]): ActivityDraftList {
  return {
    tournament: { id: 12, name: 'Kettle Cup' },
    team_draft: {
      id: 40,
      state: 'completed',
      status: 'finished',
      involves_me: true,
      role: 'player',
    },
    hero_drafts: heroes,
    launch_intent: null,
    notice: null,
    site_url: 'https://site.test',
  };
}

const setView = vi.fn();

function render(ui: ReactNode) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>);
}

beforeEach(() => {
  useActivityViewStore.getState().reset();
  useActivityViewStore.setState({ setView });
  setActivityCredential({
    token: 'tok',
    scope: 'tournament',
    tournament_id: 12,
    pin: null,
    site_url: 'https://site.test',
  });
  mocks.openExternal.mockResolvedValue(true);
});

afterEach(() => {
  vi.clearAllMocks();
  setActivityCredential(null);
  vi.restoreAllMocks();
});

describe('ActivityHeader', () => {
  it('lists the team draft, hero drafts with status chips and the bracket', () => {
    useActivityViewStore.setState({
      view: { kind: 'bracket' },
      drafts: drafts([hero(156), hero(157, { status: 'finished' })]),
    });
    render(<ActivityHeader />);

    expect(screen.getByText('Kettle Cup')).toBeInTheDocument();
    expect(screen.getByTestId('activity-menu-team')).toHaveTextContent(
      'Team draft',
    );
    expect(screen.getByTestId('activity-menu-hero-156')).toHaveTextContent(
      'Winners R1 · Game 156',
    );
    expect(screen.getByTestId('activity-menu-hero-156')).toHaveTextContent(
      'Drafting',
    );
    expect(screen.getByTestId('activity-menu-hero-157')).toHaveTextContent(
      'Finished',
    );
    expect(screen.getByTestId('activity-menu-bracket')).toHaveTextContent(
      'Bracket',
    );
  });

  it('switches to a hero draft from the menu', () => {
    useActivityViewStore.setState({
      view: { kind: 'bracket' },
      drafts: drafts([hero(156)]),
    });
    render(<ActivityHeader />);

    fireEvent.click(screen.getByTestId('activity-menu-hero-156'));
    expect(setView).toHaveBeenCalledWith({ kind: 'hero', id: 156 }, 'menu');
  });

  it('captain leaving a live draft asks first', async () => {
    useActivityViewStore.setState({
      view: { kind: 'hero', id: 156 },
      drafts: drafts([hero(156, { role: 'captain' }), hero(157)]),
    });
    render(<ActivityHeader />);

    fireEvent.click(screen.getByTestId('activity-menu-hero-157'));
    expect(setView).not.toHaveBeenCalled();
    expect(
      screen.getByText('Leaving pauses your draft for both teams.'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('activity-leave-stay'));
    expect(setView).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('activity-menu-bracket'));
    await act(async () => {
      fireEvent.click(screen.getByTestId('activity-leave-confirm'));
    });
    expect(setView).toHaveBeenCalledWith({ kind: 'bracket' }, 'menu');
  });

  it('calls onCancel when a guarded switch is declined', () => {
    useActivityViewStore.setState({
      view: { kind: 'team', id: 40 },
      drafts: {
        ...drafts([]),
        team_draft: {
          id: 40,
          state: 'drafting',
          status: 'drafting',
          involves_me: true,
          role: 'captain',
        },
      },
    });
    const proceed = vi.fn();
    const onCancel = vi.fn();
    function Probe() {
      const guard = useLeaveGuard();
      return (
        <div data-testid="probe" onClick={() => guard(proceed, onCancel)} />
      );
    }
    render(
      <>
        <ActivityHeader />
        <Probe />
      </>,
    );

    fireEvent.click(screen.getByTestId('probe'));
    expect(
      screen.getByText('The other captain will see you as disconnected.'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('activity-leave-stay'));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(proceed).not.toHaveBeenCalled();
  });

  it('lets a spectator leave a live draft without a dialog', () => {
    useActivityViewStore.setState({
      view: { kind: 'hero', id: 156 },
      drafts: drafts([hero(156), hero(157)]),
    });
    render(<ActivityHeader />);

    fireEvent.click(screen.getByTestId('activity-menu-hero-157'));
    expect(setView).toHaveBeenCalledWith({ kind: 'hero', id: 157 }, 'menu');
    expect(screen.queryByTestId('activity-leave-confirm')).toBeNull();
  });

  it('asks before leaving a draft while the drafts list has not arrived', () => {
    useActivityViewStore.setState({
      view: { kind: 'hero', id: 156 },
      drafts: null,
    });
    render(<ActivityHeader />);

    fireEvent.click(screen.getByTestId('activity-menu-bracket'));
    expect(setView).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        'If you are a captain here, leaving may pause the draft.',
      ),
    ).toBeInTheDocument();
  });

  it('opens the viewed draft in the browser after the guard', async () => {
    useActivityViewStore.setState({
      view: { kind: 'hero', id: 156 },
      drafts: drafts([hero(156, { role: 'captain' })]),
    });
    render(<ActivityHeader />);

    fireEvent.click(screen.getByTestId('activity-open-browser'));
    expect(mocks.openExternal).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByTestId('activity-leave-confirm'));
    });
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'open_external',
      view: { kind: 'hero', id: 156 },
    });
    expect(mocks.openExternal).toHaveBeenCalledWith(
      'https://site.test/herodraft/156',
    );
  });
});

describe('embedded kicked overlay', () => {
  it('remounts the view instead of reloading the frame', () => {
    const remount = vi.fn();
    useActivityViewStore.setState({ remount });
    const reload = vi.fn();
    const location = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...location, reload },
    });

    try {
      render(<KickedOverlay embedded onClose={() => {}} />);
      expect(
        screen.getByText('This draft was opened in another window'),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByText('Take control back'));
      expect(remount).toHaveBeenCalledWith('kicked_recover');
      expect(reload).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: location,
      });
    }
  });

  it('keeps the refresh button on the website', () => {
    render(<KickedOverlay embedded={false} onClose={() => {}} />);
    expect(
      screen.getByTestId('herodraft-kicked-refresh-btn'),
    ).toHaveTextContent('Refresh Page');
    expect(screen.queryByText('Take control back')).toBeNull();
  });
});
