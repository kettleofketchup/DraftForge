// Holds the general draft view

import { useEffect } from 'react';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { useUserStore } from '~/store/userStore';
import { DraftTable } from './draftTable';

interface DraftViewProps {
  curRound: DraftRoundType;
}

const DraftView: React.FC<DraftViewProps> = ({ curRound }) => {
  const tournament: TournamentType = useUserStore((state) => state.tournament);
  const draft: DraftType = useUserStore((state) => state.draft);

  const curDraftRound: DraftRoundType = useUserStore((state) => state.curDraftRound);

  useEffect(() => {}, [curDraftRound]);

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-2">Draft View</h1>

      <DraftTable curRound={curRound} />
    </div>
  );
};

export default DraftView;
