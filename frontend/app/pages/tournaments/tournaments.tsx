import { useState, useEffect } from 'react';
import { TournamentCreateModal } from '~/components/tournament/create/createModal';
import { TournamentCard } from '~/components/tournament/TournamentCard';

import type {
  TournamentType,
  TeamType,
  GameType,
  TournamentClassType,
} from '~/components/tournament/types';
import { useUserStore } from '~/store/userStore';
export default function Tournament() {
  const [count, setCount] = useState(0);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);
  const tournament: TournamentType = useUserStore((state) => state.tournament); // Zustand setter
  const getGames = useUserStore((state) => state.getGames); // Zustand setter
  const getTeams = useUserStore((state) => state.getTeams); // Zustand setter
  const getTournaments = useUserStore((state) => state.getTournaments); // Zustand setter
  const setTournaments = useUserStore((state) => state.setTournaments); // Zustand setter
  const setGames = useUserStore((state) => state.setGames); // Zustand setter
  const setTeams = useUserStore((state) => state.setTeams); // Zustand setter
  const setTournament = useUserStore((state) => state.setTournament); // Zustand setter
  const setTeam = useUserStore((state) => state.setTeam); // Zustand setter
  const tournaments: TournamentType[] = useUserStore(
    (state) => state.tournaments,
  ); // Zustand setter
  const [query, setQuery] = useState('');
  const filteredTournaments =
    query === ''
      ? tournaments
      : tournaments.filter((tourn) => {
          const q = query.toLowerCase();
          return tourn.date_played?.toLowerCase().includes(q);
        });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTournaments();
    setLoading(false);
  }, []);

  if (loading) {
    return <div className="flex justify-center">Loading...</div>;
  }

  // Helper component to manage individual card state
  const TournamentCardWrapper = ({
    tournamentData,
  }: {
    tournamentData: TournamentType;
  }) => {
    const [isCardEditing, setIsCardEditing] = useState(false);

    const wrapperClassName = isCardEditing
      ? 'grid col-span-2' // Spanning classes
      : 'grid col-span-1'; // Default class for the wrapper, assuming "grid" was intentional for item styling

    const cssClassNames = wrapperClassName + ' px-6 py-4 gap-6 content-center';

    return (
      <div className={cssClassNames} key={tournamentData.pk}>
        <TournamentCard
          tournament={tournamentData as TournamentClassType}
          saveFunc={'save'}
          onEditModeChange={setIsCardEditing} // Pass the setter
        />
      </div>
    );
  };

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
        <div
          className="grid grid-flow-row-dense grid-auto-rows
          align-middle content-center justify-center
           grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4
           mb-0 mt-0 p-0 bg-base-900  w-full"
        >
          {filteredTournaments?.map((u) => (
            <TournamentCardWrapper tournamentData={u} key={`wrapper-${u.pk}`} />
          ))}
        </div>
      </div>
    </>
  );
}
