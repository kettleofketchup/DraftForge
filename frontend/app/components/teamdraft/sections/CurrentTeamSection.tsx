import { memo, useMemo } from 'react';
import { useUserStore } from '~/store/userStore';
import { DisplayName } from '~/components/user/avatar';
import { TeamTable } from '~/components/team/teamTable/teamTable';
import { TeamPositionCoverageRow } from '../TeamPositionCoverage';

// Granular selectors
const selectTeams = (state: ReturnType<typeof useUserStore.getState>) => state.tournament?.teams;
const selectCurDraftRoundCaptainPk = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.captain?.pk;
const selectCurDraftRoundCaptain = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.captain;

export const CurrentTeamSection = memo(() => {
  const teams = useUserStore(selectTeams);
  const curDraftRoundCaptainPk = useUserStore(selectCurDraftRoundCaptainPk);
  const curDraftRoundCaptain = useUserStore(selectCurDraftRoundCaptain);

  // Get current team
  const currentTeam = useMemo(() => {
    return teams?.find((t) => t.captain?.pk === curDraftRoundCaptainPk);
  }, [teams, curDraftRoundCaptainPk]);

  const teamName = curDraftRoundCaptain ? `${DisplayName(curDraftRoundCaptain)}'s Team` : 'Current Team';

  return (
    <div className="flex-1 flex flex-col gap-2 overflow-visible">
      {/* Team Position Coverage - centered across the section */}
      <TeamPositionCoverageRow team={currentTeam} className="mb-2 pt-2" teamName={teamName} />

      {/* Team Members */}
      <div>
        <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-1 text-center lg:text-left">
          {teamName}
        </h3>
        <TeamTable team={currentTeam} compact useStrips />
      </div>
    </div>
  );
});

CurrentTeamSection.displayName = 'CurrentTeamSection';
