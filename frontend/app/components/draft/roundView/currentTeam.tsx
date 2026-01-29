import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { TeamTable } from '~/components/team/teamTable/teamTable';
import type { DraftRoundType } from '~/index';
import { getLogger } from '~/lib/logger';
import { Spinner } from '../helpers/spinner';
import { useTeamDraftStore } from '~/store/teamDraftStore';
const log = getLogger('CurrentTeamView');
interface CurrentTeamViewProps {
}
export const CurrentTeamView: React.FC<CurrentTeamViewProps> = ({
}) => {
  // Only subscribe to draft_rounds (not entire draft)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);

  // Derive current round from subscribed state (reactive)
  const curRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]) as DraftRoundType;
  const [updating, setUpdating] = useState(false);

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
      <TeamTable team={curRound?.team} />
    </Suspense>
  );
};
