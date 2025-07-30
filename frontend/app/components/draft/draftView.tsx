// Holds the general draft view

import { useEffect } from 'react';
import type { TournamentType } from '~/index';
import { useUserStore } from '~/store/userStore';

const DraftView: React.FC = () => {
  const tournament: TournamentType = useUserStore((state) => state.tournament);

  useEffect(() => {}, [tournament.teams]);
  
  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-2">Draft View</h1>
      {tournament ? (
        <div>
          <p className="text-lg">Tournament: {tournament.name}</p>
          <p className="text-base text-neutral-content">
            Status: {tournament.state}
          </p>
        </div>
      ) : (
        <span className="loading loading-spinner loading-md"></span>
      )}
    </div>
  );
};

export default DraftView;
