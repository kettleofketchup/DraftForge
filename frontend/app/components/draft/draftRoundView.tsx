// Holds the general draft view

// Holds the general draft view

import { useEffect } from 'react';
import { UserCard } from '~/components/user/userCard';
import type {
  DraftRoundType,
  DraftType,
  TournamentType,
  UserClassType,
} from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { TeamTable } from '../team/teamTable/teamTable';
import { DraftTable } from './draftTable';
const log = getLogger('DraftRoundView');
export const DraftRoundView: React.FC = () => {
  const tournament: TournamentType = useUserStore((state) => state.tournament);
  const draft: DraftType = useUserStore((state) => state.draft);

  const curDraftRound: DraftRoundType = useUserStore(
    (state) => state.curDraftRound,
  );

  useEffect(() => {}, [curDraftRound]);

  useEffect(() => {}, [tournament.teams]);
  const teamView = () => {
    if (!draft || !curDraftRound) return null;
    const team = tournament.teams?.find(
      (team) => team.captain?.pk === curDraftRound?.captain?.pk,
    );
    log.debug('Found team for captain:', team);

    // Only render TeamTable if team exists and has members
    if (!team) {
      return (
        <div className="mb-4">
          <h3 className="text-xl font-bold">Team</h3>
          <p className="text-gray-500">No team found for this captain</p>
        </div>
      );
    }

    return <TeamTable team={team} />;
  };
  const playerChoiceView = () => {
    if (!curDraftRound || !curDraftRound.choice)
      return <DraftTable curRound={curDraftRound} />;

    return (
      <div className="mb-4">
        <h3 className="text-xl font-bold">Current Choice</h3>
        <div className="flex flex-col items-center justify-center">
          <UserCard
            user={curDraftRound.choice as UserClassType}
            compact={true}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="p-4">
      <h2 className="text-2xl font-bold mb-2">Draft View</h2>

      {teamView()}
      {playerChoiceView()}
    </div>
  );
};

export default DraftRoundView;
