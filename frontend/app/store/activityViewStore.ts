import { create } from 'zustand';
import type { DraftRoundType } from '~/components/teamdraft/types';
import { postActivityView } from '~/lib/activity-api';
import type {
  ActivityDraftList,
  ActivityNotice,
  ActivityTrigger,
  ActivityView,
} from '~/lib/activity-types';
import { getLogger } from '~/lib/logger';
import { useDraftWebSocketStore } from './draftWebSocketStore';
import { useTournamentStore } from './tournamentStore';
import { useUserStore } from './userStore';

const log = getLogger('activity');

export type ActivityTerminal = 'disabled' | 'exhausted';

export interface ActivityViewState {
  view: ActivityView | null;
  viewEpoch: number;
  drafts: ActivityDraftList | null;
  notice: ActivityNotice | null;
  appliedIntentIds: Set<string>;
  dismissedNoticeIds: Set<string>;
  seenNoticeIntentIds: Set<string>;
  terminal: ActivityTerminal | null;
  scopeLost: boolean;
  setView: (
    next: ActivityView,
    trigger: ActivityTrigger,
    extra?: { intentId?: string },
  ) => void;
  remount: (trigger: ActivityTrigger) => void;
  declineIntent: (intentId: string) => void;
  setDrafts: (drafts: ActivityDraftList) => void;
  showNotice: (notice: ActivityNotice) => void;
  dismissNotice: () => void;
  setTerminal: (terminal: ActivityTerminal) => void;
  markScopeLost: () => void;
  reset: () => void;
}

export function sameView(
  a: ActivityView | null,
  b: ActivityView | null,
): boolean {
  if (!a || !b) return a === b;
  if (a.kind !== b.kind) return false;
  return a.kind === 'bracket' || a.id === (b as { id: number }).id;
}

function noticeKey(notice: ActivityNotice): string {
  return notice.intent_id ?? notice.url;
}

function leaveTeam(): void {
  const tournament = useTournamentStore.getState();
  tournament.setLive(false);
  tournament.setAutoAdvance(false);
  const user = useUserStore.getState();
  user.setDraft(null);
  user.setCurDraftRound({} as DraftRoundType);
  useDraftWebSocketStore.getState().reset();
}

function enterTeam(): void {
  const user = useUserStore.getState();
  user.setDraft(user.tournament?.draft ?? null);
  const tournament = useTournamentStore.getState();
  tournament.setLive(true);
  tournament.setAutoAdvance(true);
}

const initialState = () => ({
  view: null,
  viewEpoch: 0,
  drafts: null,
  notice: null,
  appliedIntentIds: new Set<string>(),
  dismissedNoticeIds: new Set<string>(),
  seenNoticeIntentIds: new Set<string>(),
  terminal: null,
  scopeLost: false,
});

export const useActivityViewStore = create<ActivityViewState>((set, get) => ({
  ...initialState(),

  setView: (next, trigger, extra) => {
    const from = get().view;
    const intentId = extra?.intentId;
    if (trigger !== 'scope_lost' && get().scopeLost) set({ scopeLost: false });
    const unchanged = sameView(from, next);
    if (unchanged && !intentId) return;

    if (!unchanged) {
      if (from?.kind === 'team') leaveTeam();
      if (next.kind === 'team') enterTeam();
    }

    set((state) => ({
      view: unchanged ? state.view : next,
      appliedIntentIds: intentId
        ? new Set(state.appliedIntentIds).add(intentId)
        : state.appliedIntentIds,
    }));

    log.info('activity view changed', { from, to: next, trigger, intentId });
    postActivityView({
      action: 'view',
      ...(from ? { from } : {}),
      to: next,
      trigger,
      ...(intentId ? { intent_id: intentId } : {}),
    });
  },

  remount: (trigger) => {
    const view = get().view;
    if (!view) return;
    set((state) => ({ viewEpoch: state.viewEpoch + 1 }));
    log.info('activity view remounted', { view, trigger });
    postActivityView({ action: 'view', from: view, to: view, trigger });
  },

  declineIntent: (intentId) => {
    set((state) => ({
      appliedIntentIds: new Set(state.appliedIntentIds).add(intentId),
    }));
    postActivityView({ action: 'intent_declined', intent_id: intentId });
  },

  setDrafts: (drafts) => set({ drafts }),

  showNotice: (notice) => {
    const { dismissedNoticeIds, notice: current } = get();
    const key = noticeKey(notice);
    if (dismissedNoticeIds.has(key)) return;
    if (current && noticeKey(current) === key) return;
    set({ notice });
  },

  dismissNotice: () => {
    const current = get().notice;
    if (!current) return;
    set((state) => ({
      notice: null,
      dismissedNoticeIds: new Set(state.dismissedNoticeIds).add(
        noticeKey(current),
      ),
    }));
  },

  setTerminal: (terminal) => set({ terminal }),

  markScopeLost: () => {
    set({ scopeLost: true });
    get().setView({ kind: 'bracket' }, 'scope_lost');
  },

  reset: () => set(initialState()),
}));
