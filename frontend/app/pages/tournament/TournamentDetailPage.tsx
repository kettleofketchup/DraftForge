import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import axios from '~/components/api/axios'; // Assuming axios is configured for your API
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import TournamentTabs from './tabs/TournamentTabs';

import { getLogger } from '~/lib/logger';
const log = getLogger('TournamentDetailPage');
export const TournamentDetailPage: React.FC = () => {
  const { pk, '*': slug } = useParams<{ pk: string; '*': string }>();
  const tournament = useUserStore(useShallow((state) => state.tournament));
  const setTournament = useUserStore((state) => state.setTournament);
  const setLive = useTournamentStore((state) => state.setLive);
  const setActiveTab = useTournamentStore((state) => state.setActiveTab);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const setAutoAdvance = useTournamentStore((state) => state.setAutoAdvance);
  const autoAdvance = useTournamentStore((state) => state.autoAdvance);
  const setPendingDraftId = useTournamentStore((state) => state.setPendingDraftId);
  const setPendingMatchId = useTournamentStore((state) => state.setPendingMatchId);

  useEffect(() => {
    const parts = slug?.split('/') || [];
    // Map legacy "games" URL to "bracket" tab
    let tab = parts[0] || 'players';
    if (tab === 'games') {
      tab = 'bracket';
    }
    const isLive = parts[1] === 'draft';
    // Parse draftId from URL: /tournament/:pk/bracket/draft/:draftId
    const draftId = parts[1] === 'draft' && parts[2] ? parseInt(parts[2], 10) : null;
    // Parse matchId from URL: /tournament/:pk/bracket/match/:matchId
    const matchId = parts[1] === 'match' && parts[2] ? parts[2] : null;

    // Batch state updates using unstable_batchedUpdates pattern via setTimeout
    // This prevents multiple rerenders from sequential state updates
    setActiveTab(tab);
    setPendingDraftId(Number.isNaN(draftId) ? null : draftId);
    setPendingMatchId(matchId);

    // Only update live/autoAdvance if they actually changed
    setLive(isLive);
    if (isLive) {
      setAutoAdvance(true);
    }
  }, [slug, setActiveTab, setLive, setAutoAdvance, setPendingDraftId, setPendingMatchId]);
  useEffect(() => {
    if (pk) {
      const fetchTournament = async () => {
        setLoading(true);
        setError(null);
        try {
          const response = await axios.get(`/tournaments/${pk}/`);
          setTournament(response.data);
        } catch (err) {
          log.error('Failed to fetch tournament:', err);
          setError(
            'Failed to load tournament details. Please try again later.',
          );
        } finally {
          setLoading(false);
        }
      };
      fetchTournament();
    }
  }, [pk]);

  if (loading) {
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
          <span>{error}</span>
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
        <div className="flex flex-row items-center mb-2">
          {tournamentName()}

          <span className="ml-4 text-base text-base-content/50 font-normal">
            played on {getDate()}
          </span>
        </div>
      </>
    );
  };
  return (
    <div
      className="container px-1 sm:mx-auto sm:p-4"
      data-testid="tournamentDetailPage"
    >
      {title()}
      <TournamentTabs />
    </div>
  );
};

export default TournamentDetailPage;
