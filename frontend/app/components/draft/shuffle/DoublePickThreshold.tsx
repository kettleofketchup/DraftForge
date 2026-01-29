import React, { useMemo } from 'react';
import { Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { DisplayName, type TeamType, type UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('DoublePickThreshold');
const MAX_TEAM_SIZE = 5;

export const DoublePickThreshold: React.FC = () => {
  const teams = useTournamentDataStore((state) => state.teams);
  // Subscribe to specific draft fields (not entire draft)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const latestRoundPk = useTeamDraftStore((state) => state.draft?.latest_round);
  const draftStyle = useTeamDraftStore((state) => state.draft?.draft_style);
  const usersRemaining = useTeamDraftStore((state) => state.draft?.users_remaining);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);

  // Derive current round from subscribed state (reactive)
  const curDraftRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);

  // Derive the actual latest round from draft data (single source of truth)
  // This ensures we always use fresh data even if curDraftRound is stale
  const latestRound = useMemo(() => {
    if (!draftRounds || !latestRoundPk) return null;
    return draftRounds.find((r) => r.pk === latestRoundPk) || null;
  }, [draftRounds, latestRoundPk]);

  if (draftStyle !== 'shuffle') return null;

  // Don't show if no latest round
  if (!latestRound) return null;

  // Don't show if a pick has already been made for the latest round
  if (latestRound.choice) return null;

  // Only show when user is viewing the latest round
  if (curDraftRound?.pk !== latestRoundPk) return null;

  // Check if this is already the 2nd pick of a double pick
  // If the previous round was completed by the same captain, don't show indicator
  const currentPickNumber = latestRound.pick_number;
  if (currentPickNumber && currentPickNumber > 1 && draftRounds) {
    const previousRound = draftRounds.find(
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
    return teams?.find(
      (t) => t.captain?.pk === latestRound?.captain?.pk
    );
  };

  const getThresholdTeam = (): { team: TeamType; mmr: number } | null => {
    const teamsData = teams || [];
    const currentTeam = getCurrentTeam();
    if (!currentTeam) return null;

    // Only consider active (non-maxed) teams for threshold
    const otherTeams = teamsData
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
  const availablePlayers = usersRemaining || [];
  const lowestAvailablePlayerMmr = availablePlayers.length > 0
    ? Math.min(...availablePlayers.map((p: UserType) => p.mmr || 0))
    : Infinity;

  // Can only double pick if there's a player low enough to stay under threshold
  const canDoublePick = currentMmr < threshold.mmr && lowestAvailablePlayerMmr < buffer;

  // Only show when double pick is actually possible with available players
  if (!canDoublePick) return null;

  // Only log when we're actually showing the indicator
  log.debug('DoublePickThreshold showing', {
    currentTeamCaptain: currentTeam.captain?.username,
    currentMmr,
    thresholdMmr: threshold.mmr,
    buffer,
  });

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
              ({threshold.team.captain ? DisplayName(threshold.team.captain) : threshold.team.name})
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
