import { Suspense, useEffect, useMemo, useState } from 'react';
import { TeamTable } from '~/components/team/teamTable/teamTable';
import type { DraftRoundType, TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
import { Spinner } from '../helpers/spinner';
import { useUserStore } from '~/store/userStore';
const log = getLogger('CurrentTeamView');
interface CurrentTeamViewProps {
}
export const CurrentTeamView: React.FC<CurrentTeamViewProps> = ({
}) => {
  const curRound: DraftRoundType = useUserStore((state) => state.curDraftRound);
  const tournament: TournamentType = useUserStore((state) => state.tournament);
  const [updating, setUpdating] = useState(false);

  // Derive current team from tournament.teams to ensure fresh data
  // This is necessary because curRound.team may contain stale data
  const currentTeam = useMemo(() => {
    if (!curRound?.captain?.pk || !tournament?.teams) {
      return curRound?.team;
    }
    return tournament.teams.find(
      (t) => t.captain?.pk === curRound.captain?.pk
    ) ?? curRound?.team;
  }, [tournament?.teams, curRound?.captain?.pk, curRound?.team]);

  useEffect(() => {
    // When curRound.choice changes, set updating to true
    if (curRound?.choice === null) {
      setUpdating(false);
      return;
    }

    setUpdating(true);

    // After a short delay, set it back to false to show the new table
    const timer = setTimeout(() => {
      setUpdating(false);
    }, 500); // 500ms delay

    // Cleanup the timer if the component unmounts or the effect re-runs
    return () => clearTimeout(timer);
  }, [curRound?.choice, curRound?.pk]);


  return (
    <Suspense fallback={<Spinner />}>
      <TeamTable team={currentTeam} />
    </Suspense>
  );
};
