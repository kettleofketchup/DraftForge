import { useEffect, useMemo, useState } from 'react';
import { ActivityBanner } from '~/components/activity/ActivityBanner';
import {
  ActivityHeader,
  useActivityMenu,
} from '~/components/activity/ActivityHeader';
import { ActivityNotice } from '~/components/activity/ActivityNotice';
import { useLeaveGuard } from '~/components/activity/LeaveDraftConfirm';
import api, { setActivityErrorHandlers } from '~/components/api/axios';
import { BracketView } from '~/components/bracket/BracketView';
import { HeroDraftModal } from '~/components/herodraft/HeroDraftModal';
import { DraftModal } from '~/components/teamdraft/draftModal';
import { useActivityDraftsPolling } from '~/hooks/useActivityDraftsPolling';
import type { TournamentType } from '~/index';
import {
  setActivityCredential,
  setActivityRefreshExhausted,
  setActivityRefresher,
  toActivityCredential,
} from '~/lib/activity-session';
import type { ActivityView } from '~/lib/activity-types';
import {
  ActivityDisabledError,
  initializeDiscord,
  releaseDiscordSession,
} from '~/lib/discord';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { getLogger } from '~/lib/logger';
import { ACTIVITY_OUT_OF_SCOPE } from '~/lib/websocket/WebSocketManager';
import { useActivityViewStore } from '~/store/activityViewStore';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserStore } from '~/store/userStore';

const log = getLogger('activity');

const CONNECT_ERROR =
  'Could not connect. Check that your Discord account is linked and this voice channel has a draft configured, then reopen the Activity.';
const TERMINAL_COPY = {
  disabled: 'Activities are turned off.',
  exhausted: 'The Activity lost its connection. Reopen the Activity.',
} as const;
const SCOPE_LOST_COPY = 'This draft is no longer part of the tournament.';

type Scope = 'tournament' | 'draft';

async function loadTournament(id: number): Promise<TournamentType> {
  const { data } = await api.get(`/tournaments/${id}/`);
  const tournament = hydrateTournament(data) as TournamentType;
  useUserStore.getState().setTournament(tournament);
  return tournament;
}

async function loadInitialTournament(
  id: number | null,
  initial: ActivityView,
): Promise<void> {
  const unavailable = new Error('The configured team draft is unavailable.');
  if (id === null) {
    if (initial.kind === 'team') throw unavailable;
    return;
  }
  try {
    const tournament = await loadTournament(id);
    if (initial.kind === 'team' && tournament.draft?.pk !== initial.id)
      throw unavailable;
  } catch (err) {
    if (initial.kind === 'team') throw err;
    log.warn('activity_tournament_load_failed', { error: err });
  }
}

export default function DraftActivity() {
  const [scope, setScope] = useState<Scope | null>(null);
  const [tournamentId, setTournamentId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const view = useActivityViewStore((s) => s.view);
  const epoch = useActivityViewStore((s) => s.viewEpoch);
  const drafts = useActivityViewStore((s) => s.drafts);
  const terminal = useActivityViewStore((s) => s.terminal);
  const scopeLost = useActivityViewStore((s) => s.scopeLost);
  const heroError = useHeroDraftStore((s) => s.error);
  const teamError = useDraftWebSocketStore((s) => s.error);
  const guard = useLeaveGuard();

  useEffect(() => {
    let cancelled = false;
    let first = true;
    let currentTournament: number | null = null;
    let currentScope: Scope | undefined;
    const store = useActivityViewStore.getState;

    async function start(force: boolean) {
      let result;
      try {
        result = await initializeDiscord({
          force,
          currentView: store().view ?? undefined,
          scope: currentScope,
        });
      } catch (err) {
        if (err instanceof ActivityDisabledError && !cancelled)
          store().setTerminal('disabled');
        throw err;
      }
      if (cancelled) return;
      const legacy = { kind: result.kind, id: result.draft_id } as ActivityView;
      const credential = toActivityCredential(result);
      setActivityCredential(credential);
      useUserStore.getState().setCurrentUser(result.user);

      if (credential.scope === 'draft') {
        if (first) {
          await loadInitialTournament(result.tournament_id, legacy);
          if (cancelled) return;
        } else {
          log.warn('activity_scope_downgraded', { pin: legacy });
        }
        first = false;
        currentTournament = result.tournament_id;
        setTournamentId(result.tournament_id);
        currentScope = 'draft';
        setScope('draft');
        store().setView(legacy, 'initial');
        return;
      }

      if (!first) {
        const next = result.tournament_id;
        if (next !== null && next !== currentTournament) {
          const from = currentTournament;
          currentTournament = next;
          setTournamentId(next);
          if (from !== null) {
            log.warn('activity_tournament_changed', { from, to: next });
            store().markScopeLost();
          }
        }
        currentScope = 'tournament';
        setScope('tournament');
        return;
      }

      const initial = result.initial_view ?? legacy;
      await loadInitialTournament(result.tournament_id, initial);
      if (cancelled) return;
      first = false;
      currentTournament = result.tournament_id;
      setTournamentId(result.tournament_id);
      currentScope = 'tournament';
      setScope('tournament');
      store().setView(initial, 'initial', {
        intentId: result.launch_intent?.intent_id,
      });
      if (result.notice) store().showNotice(result.notice);
    }

    setActivityRefresher(() => start(true));
    setActivityRefreshExhausted(() => {
      log.warn('activity_refresh_exhausted');
      store().setTerminal('exhausted');
    });
    setActivityErrorHandlers({
      onScopeLost: () => store().markScopeLost(),
      onDisabled: () => store().setTerminal('disabled'),
    });
    start(false).catch((err: unknown) => {
      if (cancelled || err instanceof ActivityDisabledError) return;
      log.warn('activity_start_failed', { error: err });
      setError(CONNECT_ERROR);
    });
    return () => {
      cancelled = true;
      setActivityRefresher(null);
      setActivityRefreshExhausted(null);
      setActivityErrorHandlers(null);
      setActivityCredential(null);
      useActivityViewStore.getState().reset();
      useActivityMenu.getState().setOpen(false);
      releaseDiscordSession();
    };
  }, []);

  const { refetch } = useActivityDraftsPolling(
    scope === 'tournament' && !terminal,
  );

  useEffect(() => {
    if (scope !== 'tournament') return;
    if (
      heroError === ACTIVITY_OUT_OF_SCOPE ||
      teamError === ACTIVITY_OUT_OF_SCOPE
    )
      useActivityViewStore.getState().markScopeLost();
  }, [scope, heroError, teamError]);

  const openableDraftIds = useMemo(
    () => new Set(drafts?.hero_drafts.map((d) => d.id) ?? []),
    [drafts],
  );

  if (terminal)
    return (
      <div role="alert" data-testid="activity-terminal" className="p-6">
        {TERMINAL_COPY[terminal]}
      </div>
    );
  if (error)
    return (
      <div role="alert" data-testid="activity-error" className="p-6">
        {error}
      </div>
    );
  if (!scope || !view)
    return (
      <div role="status" data-testid="activity-connecting" className="p-6">
        Connecting to Discord…
      </div>
    );

  const header =
    scope === 'tournament' ? (
      <>
        <ActivityHeader onMenuOpen={refetch} />
        <ActivityBanner />
        <ActivityNotice />
      </>
    ) : undefined;

  if (view.kind === 'team')
    return (
      <DraftModal key={`team-${epoch}`} embedded activityHeader={header} />
    );
  if (view.kind === 'hero')
    return (
      <HeroDraftModal
        key={`hero-${view.id}-${epoch}`}
        draftId={view.id}
        open
        embedded
        activityHeader={header}
        onClose={() => {}}
      />
    );
  if (tournamentId === null)
    return (
      <div role="alert" data-testid="activity-error" className="p-6">
        {CONNECT_ERROR}
      </div>
    );
  return (
    <BracketView
      key={`bracket-${epoch}`}
      embedded
      tournamentId={tournamentId}
      openableDraftIds={openableDraftIds}
      onMatchOpen={() => void refetch()}
      onOpenHeroDraft={(id) =>
        guard(() =>
          useActivityViewStore
            .getState()
            .setView({ kind: 'hero', id }, 'bracket_match'),
        )
      }
      header={
        <>
          {header}
          {scopeLost && (
            <div
              role="status"
              data-testid="activity-scope-lost"
              className="border-b border-warning/40 bg-warning/10 px-4 py-2 text-sm text-warning"
            >
              {SCOPE_LOST_COPY}
            </div>
          )}
        </>
      }
    />
  );
}
