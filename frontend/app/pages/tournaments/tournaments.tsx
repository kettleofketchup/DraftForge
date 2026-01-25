import { Loader2, Trophy } from 'lucide-react';
import { memo, useEffect, useTransition, useState } from 'react';
import { useSearchParams } from 'react-router';
import { getTournaments } from '~/components/api/api';
import { TournamentCard } from '~/components/tournament/card/TournamentCard';
import { TournamentCreateModal } from '~/components/tournament/create/createModal';
import { TournamentFilterBar } from '~/components/tournament';

import type {
  TournamentClassType,
  TournamentType,
} from '~/components/tournament/types';
import { useUserStore } from '~/store/userStore';

/** Skeleton loader for tournament cards */
const TournamentCardSkeleton = () => (
  <div className="flex items-center justify-center p-4 gap-6 content-center w-full h-full">
    <div className="w-full h-full card bg-base-200 shadow-md max-w-sm animate-pulse">
      <div className="p-4">
        {/* Header skeleton */}
        <div className="flex flex-row items-center justify-between gap-2 mb-4">
          <div className="flex flex-col gap-2">
            <div className="h-4 w-24 bg-base-300 rounded" />
            <div className="h-5 w-32 bg-base-300 rounded" />
          </div>
          <div className="flex gap-2">
            <div className="h-8 w-16 bg-base-300 rounded" />
            <div className="h-8 w-16 bg-base-300 rounded" />
          </div>
        </div>
        {/* Content skeleton */}
        <div className="space-y-3">
          <div className="h-4 w-3/4 bg-base-300 rounded" />
          <div className="h-4 w-1/2 bg-base-300 rounded" />
          <div className="h-4 w-2/3 bg-base-300 rounded" />
        </div>
        {/* Loading indicator */}
        <div className="flex items-center justify-center mt-6 text-base-content/50">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    </div>
  </div>
);

/** Memoized wrapper for individual tournament cards */
const TournamentCardWrapper = memo(({
  tournamentData,
  animationIndex,
}: {
  tournamentData: TournamentType;
  animationIndex: number;
}) => {
  return (
    <div className="col-span-1 flex gap-4 content-center h-full" key={tournamentData.pk}>
      <TournamentCard
        tournament={tournamentData as TournamentClassType}
        animationIndex={animationIndex}
      />
    </div>
  );
});
/** Grid of skeleton cards for initial loading */
const TournamentGridSkeleton = ({ count = 8 }: { count?: number }) => (
  <div
    className="grid grid-flow-row-dense grid-auto-rows
    align-middle content-center justify-center
    grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5
    mb-0 mt-0 p-0 bg-background w-full"
  >
    {Array.from({ length: count }).map((_, index) => (
      <TournamentCardSkeleton key={`skeleton-${index}`} />
    ))}
  </div>
);

/** Empty state when no tournaments found */
const EmptyTournaments = () => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <Trophy className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">No Tournaments Found</h3>
    <p className="text-sm">Create a new tournament to get started!</p>
  </div>
);

export default function Tournament() {
  const [searchParams] = useSearchParams();
  const orgId = searchParams.get('organization');
  const leagueId = searchParams.get('league');

  const setTournaments = useUserStore((state) => state.setTournaments);
  const tournaments: TournamentType[] = useUserStore(
    (state) => state.tournaments,
  );
  const getCurrentUser = useUserStore((state) => state.getCurrentUser);
  const currentUser = useUserStore((state) => state.currentUser);

  // Ensure current user is loaded
  useEffect(() => {
    if (!currentUser?.pk) {
      getCurrentUser();
    }
  }, [currentUser?.pk, getCurrentUser]);
  const [query, setQuery] = useState('');
  const [isPending, startTransition] = useTransition();

  const [loading, setLoading] = useState(true);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter tournaments - only use transition for user-initiated filtering
  const filteredTournaments = query === ''
    ? tournaments
    : tournaments.filter((tourn) => {
        const q = query.toLowerCase();
        return tourn.date_played?.toLowerCase().includes(q);
      });

  useEffect(() => {
    const fetchTournaments = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await getTournaments({
          organizationId: orgId ? parseInt(orgId, 10) : undefined,
          leagueId: leagueId ? parseInt(leagueId, 10) : undefined,
        });
        // Immediate update - no transition needed for initial load
        setTournaments(response as TournamentType[]);
        setHasInitialized(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load tournaments');
        setHasInitialized(true);
      } finally {
        setLoading(false);
      }
    };
    fetchTournaments();
  }, [orgId, leagueId, setTournaments]);

  if (error) {
    return (
      <div className="flex justify-center align-middle content-center pt-10 text-red-500">
        Error: {error}
      </div>
    );
  }

  // Render the tournament grid content based on state
  const renderTournamentGrid = () => {
    if (loading || !hasInitialized || (isPending && filteredTournaments.length === 0)) {
      return <TournamentGridSkeleton count={8} />;
    }

    if (filteredTournaments.length === 0) {
      return <EmptyTournaments />;
    }

    return (
      <div
        className={`grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
        grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5
        mb-0 mt-0 p-0 bg-background w-full
        ${isPending ? 'opacity-70 transition-opacity' : ''}`}
      >
        {filteredTournaments.map((u, index) => (
          <TournamentCardWrapper
            tournamentData={u}
            key={`wrapper-${u.pk}`}
            animationIndex={index}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col items-start p-4">
      {/* Header with Create button - NOT affected by transitions */}
      <div className="flex w-full justify-end mb-4">
        <TournamentCreateModal />
      </div>

      <TournamentFilterBar />

      {/* Tournament grid - affected by transitions */}
      {renderTournamentGrid()}
    </div>
  );
}
