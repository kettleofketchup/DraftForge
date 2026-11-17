// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { Dialog, DialogContent, DialogTitle } from '~/components/ui/dialog';
import { TooltipProvider } from '~/components/ui/tooltip';
import { setActivityCredential } from '~/lib/activity-session';
import type {
  ActivityDraftList,
  ActivityHeroDraftEntry,
} from '~/lib/activity-types';
import { useActivityViewStore } from '~/store/activityViewStore';
import { ActivityHeader, useActivityMenu } from '../ActivityHeader';

vi.mock('~/lib/discord', () => ({ openExternal: vi.fn() }));
vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: vi.fn(),
  postActivityView: vi.fn(),
}));

const DIALOG = 'activity-leave-dialog';

function hero(id: number): ActivityHeroDraftEntry {
  return {
    id,
    game_id: id + 100,
    label: `Winners R1 · Game ${id}`,
    state: 'drafting',
    status: 'drafting',
    involves_me: true,
    role: 'captain',
    updated_at: '2026-11-16T00:20:00Z',
  };
}

const DRAFTS: ActivityDraftList = {
  tournament: { id: 12, name: 'Kettle Cup' },
  team_draft: null,
  hero_drafts: [hero(156)],
  launch_intent: null,
  notice: null,
  site_url: 'https://site.test',
};

function Host() {
  const view = useActivityViewStore((s) => s.view);
  if (view?.kind === 'hero')
    return (
      <Dialog open>
        <DialogContent
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
          aria-describedby={undefined}
        >
          <DialogTitle>Hero draft</DialogTitle>
          <ActivityHeader key={`hero-${view.id}`} />
        </DialogContent>
      </Dialog>
    );
  return (
    <div data-testid="bracket-view">
      <ActivityHeader key="bracket" />
    </div>
  );
}

function dialogState(node: Node): string | null {
  if (!(node instanceof Element)) return null;
  const el = node.matches(`[data-testid="${DIALOG}"]`)
    ? node
    : node.querySelector(`[data-testid="${DIALOG}"]`);
  return el ? (el.getAttribute('data-state') ?? 'unknown') : null;
}

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

beforeEach(() => {
  useActivityViewStore.getState().reset();
  useActivityMenu.setState({ open: false });
  setActivityCredential({
    token: 'tok',
    scope: 'tournament',
    tournament_id: 12,
    pin: null,
    site_url: 'https://site.test',
  });
  useActivityViewStore.setState({
    view: { kind: 'hero', id: 156 },
    drafts: DRAFTS,
  });
});

afterEach(() => {
  setActivityCredential(null);
  vi.clearAllMocks();
});

describe('LeaveDraftConfirm with real Radix menu and dialog', () => {
  it('does not open the leave dialog on the destination view after Leave', async () => {
    render(
      <TooltipProvider>
        <Host />
      </TooltipProvider>,
    );

    act(() => useActivityMenu.getState().setOpen(true));
    fireEvent.click(await screen.findByTestId('activity-menu-bracket'));

    const original = await screen.findByTestId(DIALOG);
    expect(original).toHaveAttribute('data-state', 'open');

    const mountedAfterLeave: string[] = [];
    const observer = new MutationObserver((records) => {
      for (const r of records)
        r.addedNodes.forEach((n) => {
          const state = dialogState(n);
          if (state) mountedAfterLeave.push(state);
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });

    await act(async () => {
      fireEvent.click(screen.getByTestId('activity-leave-confirm'));
    });
    observer.takeRecords().forEach((r) =>
      r.addedNodes.forEach((n) => {
        const state = dialogState(n);
        if (state) mountedAfterLeave.push(state);
      }),
    );
    observer.disconnect();

    expect(useActivityViewStore.getState().view).toEqual({ kind: 'bracket' });
    expect(screen.getByTestId('bracket-view')).toBeInTheDocument();
    expect(mountedAfterLeave).toEqual([]);
    expect(screen.queryByTestId(DIALOG)).toBeNull();
  });
});
