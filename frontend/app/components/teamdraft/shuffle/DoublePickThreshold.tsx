import { Zap } from 'lucide-react';
import { memo, useMemo } from 'react';
import { Card, CardContent } from '~/components/ui/card';
import { DisplayName, type TeamType, type UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('DoublePickThreshold');
const MAX_TEAM_SIZE = 5;

// Granular selectors to minimize re-renders
const selectDraftStyle = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_style;
const selectLatestRoundPk = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.latest_round;
const selectDraftRounds = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_rounds;
const selectUsersRemaining = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.users_remaining;
const selectTeams = (state: ReturnType<typeof useUserStore.getState>) => state.tournament?.teams;
const selectCurDraftRoundPk = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.pk;
const selectCurrentUserPk = (state: ReturnType<typeof useUserStore.getState>) => state.currentUser?.pk;

export const DoublePickThreshold: React.FC = memo(() => {
  // Use granular selectors - component only re-renders when these specific values change
  const draftStyle = useUserStore(selectDraftStyle);
  const latestRoundPk = useUserStore(selectLatestRoundPk);
  const draftRounds = useUserStore(selectDraftRounds);
  const usersRemaining = useUserStore(selectUsersRemaining);
  const teams = useUserStore(selectTeams);
  const curDraftRoundPk = useUserStore(selectCurDraftRoundPk);
  const currentUserPk = useUserStore(selectCurrentUserPk);
  const isStaff = useUserStore((state) => state.isStaff);

  // Derive the actual latest round from draft data (single source of truth)
  const latestRound = useMemo(() => {
    if (!draftRounds || !latestRoundPk) return null;
    return draftRounds.find((r) => r.pk === latestRoundPk) || null;
  }, [draftRounds, latestRoundPk]);

  // Early returns for non-shuffle or missing data
  if (draftStyle !== 'shuffle') return null;
  if (!latestRound) return null;
  if (latestRound.choice) return null;
  if (curDraftRoundPk !== latestRoundPk) return null;

  // Check if this is already the 2nd pick of a double pick
  const currentPickNumber = latestRound.pick_number;
  if (currentPickNumber && currentPickNumber > 1 && draftRounds) {
    const previousRound = draftRounds.find(
      (r) => r.pick_number === currentPickNumber - 1
    );
    if (
      previousRound?.choice &&
      previousRound?.captain?.pk === latestRound.captain?.pk
    ) {
      return null;
    }
  }

  const isCurrentPicker = latestRound.captain?.pk === currentUserPk;
  if (!isCurrentPicker && !isStaff()) return null;

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member: UserType) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const isTeamMaxed = (team: TeamType): boolean => {
    return (team.members?.length || 0) >= MAX_TEAM_SIZE;
  };

  const currentTeam = teams?.find(
    (t) => t.captain?.pk === latestRound?.captain?.pk
  );

  if (!currentTeam) return null;
  if (isTeamMaxed(currentTeam)) return null;

  const currentTeamSize = currentTeam.members?.length || 0;
  if (currentTeamSize >= MAX_TEAM_SIZE - 1) return null;

  // Find threshold team (lowest MMR among other active teams)
  const otherActiveTeams = (teams || [])
    .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t))
    .map((t) => ({ team: t, mmr: getTeamMmr(t) }))
    .sort((a, b) => a.mmr - b.mmr);

  const threshold = otherActiveTeams[0];
  if (!threshold) return null;

  const currentMmr = getTeamMmr(currentTeam);
  const buffer = threshold.mmr - currentMmr;

  // Check if any available player would result in staying under threshold
  const lowestAvailablePlayerMmr = usersRemaining && usersRemaining.length > 0
    ? Math.min(...usersRemaining.map((p: UserType) => p.mmr || 0))
    : Infinity;

  const canDoublePick = currentMmr < threshold.mmr && lowestAvailablePlayerMmr < buffer;
  if (!canDoublePick) return null;

  log.debug('DoublePickThreshold showing', {
    currentTeamCaptain: currentTeam.captain?.username,
    currentMmr,
    thresholdMmr: threshold.mmr,
    buffer,
  });

  return (
    <Card className="mb-4 border-green-500 bg-green-950/20">
      <CardContent className="py-3 text-sm">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="flex items-center gap-2 font-medium">
              <Zap className="h-4 w-4 text-green-500" />
              Double Pick Available!
            </span>
            <span className="text-muted-foreground">
              Stay under{' '}
              <span className="font-semibold text-foreground">
                {threshold.mmr.toLocaleString()} MMR
              </span>{' '}
              to pick again
              {' '}
              ({threshold.team.captain ? DisplayName(threshold.team.captain) : threshold.team.name})
            </span>
          </div>
          <span className="text-muted-foreground">
            Your current MMR:{' '}
            <span className="font-medium text-green-400">
              {currentMmr.toLocaleString()}
            </span>
            <span className="text-green-400 ml-1">
              ({buffer.toLocaleString()} buffer)
            </span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
});

DoublePickThreshold.displayName = 'DoublePickThreshold';
