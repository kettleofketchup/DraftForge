import { useEffect, useState } from 'react';
import api from '~/components/api/axios';
import { HeroDraftModal } from '~/components/herodraft/HeroDraftModal';
import { DraftModal } from '~/components/teamdraft/draftModal';
import type { TournamentType } from '~/index';
import {
  setActivityCredential,
  setActivityRefresher,
} from '~/lib/activity-session';
import {
  initializeDiscord,
  releaseDiscordSession,
  type DraftActivitySession,
} from '~/lib/discord';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';

export default function DraftActivity() {
  const [session, setSession] = useState<DraftActivitySession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function start(force = false) {
      const result = await initializeDiscord({ force });
      if (cancelled) return;
      setActivityCredential(result);
      useUserStore.getState().setCurrentUser(result.user);
      if (result.kind === 'team') {
        const { data } = await api.get(`/tournaments/${result.tournament_id}/`);
        if (cancelled) return;
        const tournament = hydrateTournament(data) as TournamentType;
        if (!tournament.draft || tournament.draft.pk !== result.draft_id) {
          throw new Error('The configured team draft is unavailable.');
        }
        useUserStore.getState().setTournament(tournament);
        useUserStore.getState().setDraft(tournament.draft);
        useTournamentStore.getState().setLive(true);
      }
      setSession(result);
    }
    // Sockets call this on 4401 (expiry, revocation, or the channel moving on
    // to the next game's draft) so the Activity recovers without a relaunch.
    setActivityRefresher(() => start(true));
    start().catch(() => {
      if (!cancelled)
        setError(
          'Could not connect. Check that your Discord account is linked and this voice channel has a draft configured, then reopen the Activity.',
        );
    });
    return () => {
      cancelled = true;
      setActivityRefresher(null);
      setActivityCredential(null);
      releaseDiscordSession();
    };
  }, []);

  if (error)
    return (
      <div role="alert" data-testid="activity-error" className="p-6">
        {error}
      </div>
    );
  if (!session)
    return (
      <div role="status" data-testid="activity-connecting" className="p-6">
        Connecting to Discord…
      </div>
    );
  if (session.kind === 'team') return <DraftModal embedded />;
  return (
    <HeroDraftModal
      key={session.draft_id}
      draftId={session.draft_id}
      open
      embedded
      onClose={() => {}}
    />
  );
}
