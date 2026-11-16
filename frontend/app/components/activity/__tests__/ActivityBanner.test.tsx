// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ActivityDraftList,
  ActivityHeroDraftEntry,
  ActivityView,
} from '~/lib/activity-types';
import { useActivityViewStore } from '~/store/activityViewStore';
import { ActivityBanner } from '../ActivityBanner';
import { useActivityMenu } from '../ActivityHeader';

vi.mock('~/lib/discord', () => ({ openExternal: vi.fn() }));
vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: vi.fn(),
  postActivityView: vi.fn(),
}));

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

function list(heroes: ActivityHeroDraftEntry[]): ActivityDraftList {
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

const LIVE_MINE = { status: 'drafting', involves_me: true, role: 'player' };
const LIVE_OTHER = { status: 'drafting', involves_me: false } as const;

const setView = vi.fn();

function show(view: ActivityView, heroes: ActivityHeroDraftEntry[]) {
  useActivityViewStore.setState({ view, drafts: list(heroes), setView });
  render(<ActivityBanner />);
}

beforeEach(() => {
  useActivityViewStore.getState().reset();
  useActivityMenu.setState({ open: false });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ActivityBanner', () => {
  it('offers my live draft while I view a finished one', () => {
    show({ kind: 'team', id: 40 }, [
      hero(156, LIVE_MINE as Partial<ActivityHeroDraftEntry>),
    ]);
    expect(screen.getByTestId('activity-banner')).toHaveTextContent(
      'Game 156 is live',
    );
    fireEvent.click(screen.getByTestId('activity-banner-view'));
    expect(setView).toHaveBeenCalledWith({ kind: 'hero', id: 156 }, 'banner');
  });

  it('offers my live draft while I spectate a live draft that is not mine', () => {
    show({ kind: 'hero', id: 157 }, [
      hero(156, LIVE_MINE as Partial<ActivityHeroDraftEntry>),
      hero(157, LIVE_OTHER),
    ]);
    expect(screen.getByTestId('activity-banner')).toHaveTextContent(
      'Game 156 is live',
    );
  });

  it('treats a viewed draft missing from the list as finished', () => {
    show({ kind: 'hero', id: 90 }, [
      hero(156, LIVE_MINE as Partial<ActivityHeroDraftEntry>),
      hero(157, LIVE_OTHER),
    ]);
    expect(screen.getByTestId('activity-banner')).toHaveTextContent(
      'Game 156 is live',
    );
  });

  it('counts live drafts while viewing a draft missing from the list', () => {
    show({ kind: 'hero', id: 90 }, [hero(156, LIVE_OTHER)]);
    expect(screen.getByTestId('activity-banner')).toHaveTextContent(
      '1 draft live',
    );
  });

  it('stays hidden while I view my own live draft', () => {
    show({ kind: 'hero', id: 156 }, [
      hero(156, LIVE_MINE as Partial<ActivityHeroDraftEntry>),
      hero(157, LIVE_OTHER),
    ]);
    expect(screen.queryByTestId('activity-banner')).toBeNull();
  });

  it('counts live drafts when none involves me and opens the menu', () => {
    show({ kind: 'bracket' }, [
      hero(156, LIVE_OTHER),
      hero(157, LIVE_OTHER),
      hero(158),
    ]);
    expect(screen.getByTestId('activity-banner')).toHaveTextContent(
      '2 drafts live',
    );
    fireEvent.click(screen.getByTestId('activity-banner-choose'));
    expect(useActivityMenu.getState().open).toBe(true);
    expect(setView).not.toHaveBeenCalled();
  });

  it('stays hidden while spectating a live draft with nothing of mine live', () => {
    show({ kind: 'hero', id: 156 }, [
      hero(156, LIVE_OTHER),
      hero(157, LIVE_OTHER),
    ]);
    expect(screen.queryByTestId('activity-banner')).toBeNull();
  });

  it('stays hidden when nothing is live', () => {
    show({ kind: 'bracket' }, [hero(156)]);
    expect(screen.queryByTestId('activity-banner')).toBeNull();
  });
});
