import { memo, useEffect, useState } from 'react';
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

/** Memoized wrapper for individual tournament cards */
const TournamentCardWrapper = memo(({
  tournamentData,
  animationIndex,
}: {
  tournamentData: TournamentType;
  animationIndex: number;
}) => {
  const [isCardEditing, setIsCardEditing] = useState(false);

  const wrapperClassName = isCardEditing
    ? ' col-span-2'
    : ' col-span-1';

  const cssClassNames = wrapperClassName + 'flex gap-4 content-center h-full';

  return (
    <div className={cssClassNames} key={tournamentData.pk}>
      <TournamentCard
        tournament={tournamentData as TournamentClassType}
        saveFunc={'save'}
        onEditModeChange={setIsCardEditing}
        animationIndex={animationIndex}
      />
    </div>
  );
});
export default function Tournament() {
  const [searchParams] = useSearchParams();
  const orgId = searchParams.get('organization');
  const leagueId = searchParams.get('league');

  const setTournaments = useUserStore((state) => state.setTournaments);
  const tournaments: TournamentType[] = useUserStore(
    (state) => state.tournaments,
  );
  const [query, setQuery] = useState('');
  const filteredTournaments =
    query === ''
      ? tournaments
      : tournaments.filter((tourn) => {
          const q = query.toLowerCase();
          return tourn.date_played?.toLowerCase().includes(q);
        });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTournaments = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await getTournaments({
          organizationId: orgId ? parseInt(orgId, 10) : undefined,
          leagueId: leagueId ? parseInt(leagueId, 10) : undefined,
        });
        setTournaments(response as TournamentType[]);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load tournaments');
      } finally {
        setLoading(false);
      }
    };
    fetchTournaments();
  }, [orgId, leagueId, setTournaments]);

  if (loading) {
    return (
      <div className="flex justify-center align-middle content-center pt-10">
        Loading...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center align-middle content-center pt-10 text-red-500">
        Error: {error}
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col items-start p-4 h-full  ">
        <div
          className="grid grid-flow-row-dense grid-auto-rows
          align-middle content-center justify-center
         grid-cols-4
           w-full "
        >
          <div className="flex col-start-4 align-end content-end justify-end">
            <TournamentCreateModal />
          </div>
        </div>
        <TournamentFilterBar />
        <div
          className="grid grid-flow-row-dense grid-auto-rows
          align-middle content-center justify-center
           grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4
           mb-0 mt-0 p-0 bg-base-900  w-full"
        >
          {filteredTournaments?.map((u, index) => (
            <TournamentCardWrapper
              tournamentData={u}
              key={`wrapper-${u.pk}`}
              animationIndex={index}
            />
          ))}
        </div>
      </div>
    </>
  );
}
