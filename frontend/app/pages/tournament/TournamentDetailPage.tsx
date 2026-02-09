import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { useTournament } from '~/hooks/useTournament';
import { useTournamentSocket } from '~/hooks/useTournamentSocket';
import type { TournamentType } from '~/components/tournament/types';
import TournamentTabs from './tabs/TournamentTabs';

import { getLogger } from '~/lib/logger';
const log = getLogger('TournamentDetailPage');

export const TournamentDetailPage: React.FC = () => {
  const { pk, '*': slug } = useParams<{ pk: string; '*': string }>();
  const navigate = useNavigate();
  const pkNum = pk ? parseInt(pk, 10) : null;

  // TanStack Query for tournament data
  const { data: tournament, isLoading, error } = useTournament(
    pkNum && !Number.isNaN(pkNum) ? pkNum : null,
  );

  // WebSocket for real-time cache invalidation
  useTournamentSocket(pkNum && !Number.isNaN(pkNum) ? pkNum : null);

  // Compatibility shim: sync query data to userStore for ~35 existing consumers
  // NOTE: This is one-way (query -> userStore). Files that call fetchTournament()
  // directly and write to userStore will be overwritten on next refetch (~10s).
  useEffect(() => {
    if (tournament) {
      useUserStore.getState().setTournament(tournament);
    }
    return () => {
      // Clear stale tournament when navigating away so children don't see old data
      useUserStore.getState().setTournament(null as unknown as TournamentType);
    };
  }, [tournament]);

  // UI state from tournamentStore
  const setLive = useTournamentStore((state) => state.setLive);
  const setActiveTab = useTournamentStore((state) => state.setActiveTab);
  const setAutoAdvance = useTournamentStore((state) => state.setAutoAdvance);
  const setPendingDraftId = useTournamentStore((state) => state.setPendingDraftId);
  const setPendingMatchId = useTournamentStore((state) => state.setPendingMatchId);

  // Parse URL slug for tabs and deep-linking
  useEffect(() => {
    const parts = slug?.split('/') || [];
    let tab = parts[0] || 'players';
    if (tab === 'games') {
      tab = 'bracket';
    }
    const isLive = parts[1] === 'draft';
    const draftId = parts[1] === 'draft' && parts[2] ? parseInt(parts[2], 10) : null;
    const matchId = parts[1] === 'match' && parts[2] ? parts[2] : null;

    // Redirect /tournament/:pk/bracket/draft/:draftId to /herodraft/:draftId
    if (draftId && !Number.isNaN(draftId)) {
      navigate(`/herodraft/${draftId}`, { replace: true });
      return;
    }

    setActiveTab(tab);
    setPendingDraftId(Number.isNaN(draftId) ? null : draftId);
    setPendingMatchId(matchId);
    setLive(isLive);
    if (isLive) {
      setAutoAdvance(true);
    }
  }, [slug, setActiveTab, setLive, setAutoAdvance, setPendingDraftId, setPendingMatchId, navigate]);

  // Set org context from tournament
  useEffect(() => {
    if (tournament?.organization_pk) {
      useOrgStore.getState().getOrganization(tournament.organization_pk);
    } else {
      useOrgStore.getState().setCurrentOrg(null);
    }
    return () => {
      useOrgStore.getState().reset();
    };
  }, [tournament?.organization_pk]);

  // Set league context from tournament
  useEffect(() => {
    if (tournament?.league_pk) {
      useLeagueStore.getState().getLeague(tournament.league_pk);
    } else {
      useLeagueStore.getState().setCurrentLeague(null);
    }
    return () => {
      useLeagueStore.getState().reset();
    };
  }, [tournament?.league_pk]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div role="alert" className="alert alert-error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Failed to load tournament details. Please try again later.</span>
        </div>
      </div>
    );
  }

  if (!tournament) {
    return (
      <div className="flex justify-center items-center h-screen">
        Tournament not found.
      </div>
    );
  }

  const getDate = () => {
    let date = tournament.date_played
      ? (() => {
          const [year, month, day] = tournament.date_played.split('-');
          return `${month}-${day}`;
        })()
      : '';
    return `${date || ''}`;
  };

  const tournamentName = () => {
    if (!tournament.name) {
      return <></>;
    }
    return (
      <h1 className="text-3xl font-bold mb-4" data-testid="tournamentTitle">
        {tournament.name}
      </h1>
    );
  };

  const title = () => {
    return (
      <>
        <div className="flex flex-col sm:flex-row sm:items-center mb-2 gap-1">
          {tournamentName()}
          <span className="sm:ml-4 text-base text-base-content/50 font-normal">
            played on {getDate()}
          </span>
        </div>
      </>
    );
  };

  return (
    <div
      className="max-w-full overflow-x-hidden px-2 sm:container sm:mx-auto sm:p-4"
      data-testid="tournamentDetailPage"
    >
      {title()}
      <TournamentTabs />
    </div>
  );
};

export default TournamentDetailPage;
