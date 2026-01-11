import { Zap } from 'lucide-react';
import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import type { TeamType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('DoublePickThreshold');
const MAX_TEAM_SIZE = 5;

export const DoublePickThreshold: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);

  // Derive the actual latest round from draft data (single source of truth)
  // This ensures we always use fresh data even if curDraftRound is stale
  const latestRound = useMemo(() => {
    if (!draft?.draft_rounds || !draft?.latest_round) return null;
    return draft.draft_rounds.find((r) => r.pk === draft.latest_round) || null;
  }, [draft?.draft_rounds, draft?.latest_round]);

  if (draft?.draft_style !== 'shuffle') return null;

  // Don't show if no latest round
  if (!latestRound) return null;

  // Don't show if a pick has already been made for the latest round
  if (latestRound.choice) return null;

  // Only show when user is viewing the latest round
  if (curDraftRound?.pk !== draft?.latest_round) return null;

  // Check if this is already the 2nd pick of a double pick
  // If the previous round was completed by the same captain, don't show indicator
  const currentPickNumber = latestRound.pick_number;
  if (currentPickNumber && currentPickNumber > 1 && draft?.draft_rounds) {
    const previousRound = draft.draft_rounds.find(
      (r) => r.pick_number === currentPickNumber - 1
    );
    if (
      previousRound?.choice &&
      previousRound?.captain?.pk === latestRound.captain?.pk
    ) {
      // This is the 2nd pick of a double pick, don't show the indicator
      log.debug('Hiding double pick indicator - already on 2nd pick of double pick');
      return null;
    }
  }

  const isCurrentPicker = latestRound.captain?.pk === currentUser?.pk;
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

  const getCurrentTeam = (): TeamType | undefined => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === latestRound?.captain?.pk
    );
  };

  const getThresholdTeam = (): { team: TeamType; mmr: number } | null => {
    const teams = tournament?.teams || [];
    const currentTeam = getCurrentTeam();
    if (!currentTeam) return null;

    // Only consider active (non-maxed) teams for threshold
    const otherTeams = teams
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t))
      .map((t) => ({ team: t, mmr: getTeamMmr(t) }))
      .sort((a, b) => a.mmr - b.mmr);

    return otherTeams[0] || null;
  };

  const currentTeam = getCurrentTeam();
  const threshold = getThresholdTeam();

  if (!currentTeam || !threshold) return null;

  // Don't show if current team is already maxed
  if (isTeamMaxed(currentTeam)) return null;

  // Don't show if current team only has 1 slot remaining (can't double pick)
  const currentTeamSize = currentTeam.members?.length || 0;
  if (currentTeamSize >= MAX_TEAM_SIZE - 1) return null;

  const currentMmr = getTeamMmr(currentTeam);
  const buffer = threshold.mmr - currentMmr;

  // Check if any available player would result in staying under threshold
  const availablePlayers = draft?.users_remaining || [];
  const lowestAvailablePlayerMmr = availablePlayers.length > 0
    ? Math.min(...availablePlayers.map((p: UserType) => p.mmr || 0))
    : Infinity;

  // Can only double pick if there's a player low enough to stay under threshold
  const canDoublePick = currentMmr < threshold.mmr && lowestAvailablePlayerMmr < buffer;

  log.debug('DoublePickThreshold check', {
    currentTeamCaptain: currentTeam.captain?.username,
    currentMmr,
    thresholdTeamCaptain: threshold.team.captain?.username,
    thresholdMmr: threshold.mmr,
    buffer,
    lowestAvailablePlayerMmr,
    canDoublePick,
    currentTeamMembers: currentTeam.members?.length,
    latestRoundPk: latestRound?.pk,
    latestRoundCaptain: latestRound?.captain?.username,
    curDraftRoundPk: curDraftRound?.pk,
  });

  // Only show when double pick is actually possible with available players
  if (!canDoublePick) return null;

  return (
    <Card className="mb-4 border-green-500 bg-green-950/20">
      <CardHeader className="pb-2 pt-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Zap className="h-4 w-4 text-green-500" />
          Double Pick Available!
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm pb-3">
        <div className="flex flex-col gap-1">
          <span>
            Stay under{' '}
            <span className="font-semibold">
              {threshold.mmr.toLocaleString()} MMR
            </span>{' '}
            to pick again
            <span className="text-muted-foreground">
              {' '}
              ({threshold.team.captain?.nickname || threshold.team.captain?.username || threshold.team.name})
            </span>
          </span>
          <span className="text-muted-foreground">
            Your current MMR:{' '}
            <span className="font-medium text-green-400">
              {currentMmr.toLocaleString()}
            </span>
            <span className="text-green-400 ml-2">
              ({(threshold.mmr - currentMmr).toLocaleString()} buffer)
            </span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
};
