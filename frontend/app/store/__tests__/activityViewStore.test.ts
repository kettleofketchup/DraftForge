import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DraftRoundType, DraftType } from '~/components/teamdraft/types';
import type { TournamentType } from '~/index';
import type { ActivityNotice } from '~/lib/activity-types';
import { useActivityViewStore } from '../activityViewStore';
import { useDraftWebSocketStore } from '../draftWebSocketStore';
import { useTournamentStore } from '../tournamentStore';
import { useUserStore } from '../userStore';

const mocks = vi.hoisted(() => ({ postActivityView: vi.fn(), get: vi.fn() }));
vi.mock('~/components/api/axios', () => ({
  default: { get: mocks.get },
}));
vi.mock('~/lib/hydrateTournament', () => ({
  hydrateTournament: (data: unknown) => data,
}));
vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: vi.fn(),
  postActivityView: mocks.postActivityView,
}));

const teamDraft = { pk: 40 } as DraftType;

const noticeA: ActivityNotice = {
  intent_id: 'n1',
  kind: 'hero',
  draft_id: 300,
  tournament_name: 'Other Cup',
  label: 'Game 1',
  url: 'https://site.test/herodraft/300',
};

const channelNotice: ActivityNotice = {
  kind: 'team',
  draft_id: 12,
  tournament_name: 'Other Cup',
  label: 'Team draft',
  url: 'https://site.test/tournament/9/teams/draft',
};

let wsReset: ReturnType<typeof vi.fn<() => void>>;

beforeEach(() => {
  vi.clearAllMocks();
  useActivityViewStore.getState().reset();
  useTournamentStore.setState({ live: false, autoAdvance: false });
  useUserStore.setState({
    tournament: { pk: 9, draft: teamDraft } as TournamentType,
    draft: {} as DraftType,
    curDraftRound: { pk: 5 } as DraftRoundType,
  });
  wsReset = vi.fn<() => void>();
  useDraftWebSocketStore.setState({ reset: wsReset });
});

describe('activityViewStore', () => {
  it('enters the team view with live and auto-advance on', () => {
    useActivityViewStore
      .getState()
      .setView({ kind: 'team', id: 40 }, 'initial');
    expect(useActivityViewStore.getState().view).toEqual({
      kind: 'team',
      id: 40,
    });
    expect(useTournamentStore.getState().live).toBe(true);
    expect(useTournamentStore.getState().autoAdvance).toBe(true);
    expect(useUserStore.getState().draft).toBe(teamDraft);
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'view',
      to: { kind: 'team', id: 40 },
      trigger: 'initial',
    });
  });

  it('tears down the team stores when switching to a hero draft', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'team', id: 40 }, 'initial');
    mocks.postActivityView.mockClear();
    store.setView({ kind: 'hero', id: 156 }, 'menu');
    expect(useTournamentStore.getState().live).toBe(false);
    expect(useTournamentStore.getState().autoAdvance).toBe(false);
    expect(useUserStore.getState().draft).toBeNull();
    expect(useUserStore.getState().curDraftRound).toEqual({});
    expect(wsReset).toHaveBeenCalledTimes(1);
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'view',
      from: { kind: 'team', id: 40 },
      to: { kind: 'hero', id: 156 },
      trigger: 'menu',
    });
  });

  it('restores live and auto-advance when returning to the team draft', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'team', id: 40 }, 'initial');
    store.setView({ kind: 'hero', id: 156 }, 'menu');
    store.setView({ kind: 'team', id: 40 }, 'menu');
    expect(useTournamentStore.getState().live).toBe(true);
    expect(useTournamentStore.getState().autoAdvance).toBe(true);
    expect(useUserStore.getState().draft).toBe(teamDraft);
  });

  it('fetches the team draft when it started after the Activity loaded', async () => {
    useUserStore.setState({
      tournament: { pk: 9, draft: null } as unknown as TournamentType,
      tournamentPK: 9,
      draft: null,
    });
    mocks.get.mockResolvedValue({ data: { pk: 9, draft: teamDraft } });
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    store.setView({ kind: 'team', id: 40 }, 'menu');
    await vi.waitFor(() => expect(useUserStore.getState().draft?.pk).toBe(40));
  });

  it('does not tear down team stores when moving between hero drafts', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    store.setView({ kind: 'hero', id: 157 }, 'menu');
    expect(wsReset).not.toHaveBeenCalled();
  });

  it('ignores a switch to the current view without an intent', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    mocks.postActivityView.mockClear();
    store.setView({ kind: 'hero', id: 156 }, 'menu');
    expect(mocks.postActivityView).not.toHaveBeenCalled();
    expect(useActivityViewStore.getState().viewEpoch).toBe(0);
  });

  it('records and posts the intent id that caused a switch', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    store.setView({ kind: 'hero', id: 157 }, 'launch_intent', {
      intentId: 'q1w2e3',
    });
    expect(useActivityViewStore.getState().appliedIntentIds.has('q1w2e3')).toBe(
      true,
    );
    expect(mocks.postActivityView).toHaveBeenLastCalledWith({
      action: 'view',
      from: { kind: 'hero', id: 156 },
      to: { kind: 'hero', id: 157 },
      trigger: 'launch_intent',
      intent_id: 'q1w2e3',
    });
  });

  it('posts an intent that targets the current view so the server consumes it', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    mocks.postActivityView.mockClear();
    store.setView({ kind: 'hero', id: 156 }, 'launch_intent', {
      intentId: 'same',
    });
    expect(useActivityViewStore.getState().appliedIntentIds.has('same')).toBe(
      true,
    );
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'view',
      from: { kind: 'hero', id: 156 },
      to: { kind: 'hero', id: 156 },
      trigger: 'launch_intent',
      intent_id: 'same',
    });
  });

  it('remount bumps the epoch and posts the same view', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    mocks.postActivityView.mockClear();
    store.remount('kicked_recover');
    expect(useActivityViewStore.getState().viewEpoch).toBe(1);
    expect(useActivityViewStore.getState().view).toEqual({
      kind: 'hero',
      id: 156,
    });
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'view',
      from: { kind: 'hero', id: 156 },
      to: { kind: 'hero', id: 156 },
      trigger: 'kicked_recover',
    });
  });

  it('markScopeLost switches to the bracket', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    store.markScopeLost();
    const state = useActivityViewStore.getState();
    expect(state.scopeLost).toBe(true);
    expect(state.view).toEqual({ kind: 'bracket' });
    expect(mocks.postActivityView).toHaveBeenLastCalledWith({
      action: 'view',
      from: { kind: 'hero', id: 156 },
      to: { kind: 'bracket' },
      trigger: 'scope_lost',
    });
  });

  it('clears scopeLost when the user picks another view', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    store.markScopeLost();
    store.setView({ kind: 'hero', id: 157 }, 'menu');
    expect(useActivityViewStore.getState().scopeLost).toBe(false);
  });

  it('clears scopeLost when the user picks the bracket it is already on', () => {
    const store = useActivityViewStore.getState();
    store.setView({ kind: 'hero', id: 156 }, 'initial');
    store.markScopeLost();
    store.setView({ kind: 'bracket' }, 'menu');
    expect(useActivityViewStore.getState().scopeLost).toBe(false);
  });

  it('declineIntent records the intent and posts intent_declined', () => {
    useActivityViewStore.getState().declineIntent('q1');
    expect(useActivityViewStore.getState().appliedIntentIds.has('q1')).toBe(
      true,
    );
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'intent_declined',
      intent_id: 'q1',
    });
  });

  it('keeps a shown notice when a later poll carries none', () => {
    const store = useActivityViewStore.getState();
    store.showNotice(channelNotice);
    store.setDrafts({
      tournament: { id: 9, name: 'Cup' },
      team_draft: null,
      hero_drafts: [],
      launch_intent: null,
      notice: null,
      site_url: 'https://site.test',
    });
    expect(useActivityViewStore.getState().notice).toEqual(channelNotice);
  });

  it('does not show a dismissed notice again', () => {
    const store = useActivityViewStore.getState();
    store.showNotice(noticeA);
    store.dismissNotice();
    expect(useActivityViewStore.getState().notice).toBeNull();
    store.showNotice(noticeA);
    expect(useActivityViewStore.getState().notice).toBeNull();
    store.showNotice(channelNotice);
    store.dismissNotice();
    store.showNotice(channelNotice);
    expect(useActivityViewStore.getState().notice).toBeNull();
  });

  it('keeps the same notice object when it is shown again', () => {
    const store = useActivityViewStore.getState();
    store.showNotice(noticeA);
    const shown = useActivityViewStore.getState().notice;
    store.showNotice({ ...noticeA });
    expect(useActivityViewStore.getState().notice).toBe(shown);
  });

  it('records terminal states', () => {
    useActivityViewStore.getState().setTerminal('exhausted');
    expect(useActivityViewStore.getState().terminal).toBe('exhausted');
  });
});
