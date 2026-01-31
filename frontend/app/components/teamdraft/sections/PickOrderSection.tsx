import { memo, useMemo } from 'react';
import { Badge } from '~/components/ui/badge';
import { TeamPopover } from '~/components/team';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/index';
import type { DraftRoundType } from '../types';

const MAX_TEAM_SIZE = 5;
const MAX_UPCOMING_PICKS = 8;

// Granular selectors
const selectTeams = (state: ReturnType<typeof useUserStore.getState>) => state.tournament?.teams;
const selectDraftStyle = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_style;
const selectDraftRounds = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_rounds;
const selectCurDraftRoundPk = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.pk;

interface PickOrderCaptain {
  team: TeamType;
  totalMmr: number;
  isCurrent: boolean;
  pickOrder: number;
  isMaxed: boolean;
}

interface UpcomingPick {
  round: DraftRoundType;
  team: TeamType;
  isCurrent: boolean;
  pickNumber: number;
}

const getOrdinal = (n: number): string => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

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

export const PickOrderSection = memo(() => {
  const teams = useUserStore(selectTeams);
  const draftStyle = useUserStore(selectDraftStyle);
  const draftRounds = useUserStore(selectDraftRounds);
  const curDraftRoundPk = useUserStore(selectCurDraftRoundPk);

  // Build a map of team pk to team for quick lookup
  const teamMap = useMemo(() => {
    const map = new Map<number, TeamType>();
    teams?.forEach((team) => {
      if (team.pk) map.set(team.pk, team);
    });
    return map;
  }, [teams]);

  // For snake/normal draft: compute upcoming picks from draftRounds
  const upcomingPicks = useMemo((): UpcomingPick[] => {
    if (draftStyle === 'shuffle' || !draftRounds?.length) return [];

    const currentRoundIndex = draftRounds.findIndex((r) => r.pk === curDraftRoundPk);
    if (currentRoundIndex === -1) return [];

    // Limit to min of captain count or MAX_UPCOMING_PICKS
    const numCaptains = teams?.length ?? 0;
    const maxPicks = Math.min(numCaptains, MAX_UPCOMING_PICKS);

    // Get upcoming rounds (including current) that haven't been picked yet
    const upcoming: UpcomingPick[] = [];
    for (let i = currentRoundIndex; i < draftRounds.length && upcoming.length < maxPicks; i++) {
      const round = draftRounds[i];
      // Skip rounds that already have a choice (already picked)
      if (round.choice) continue;

      const team = round.team?.pk ? teamMap.get(round.team.pk) : undefined;
      if (!team) continue;

      upcoming.push({
        round,
        team,
        isCurrent: i === currentRoundIndex,
        pickNumber: round.pick_number ?? i + 1,
      });
    }

    // Ensure we never exceed maxPicks (safeguard)
    return upcoming.slice(0, maxPicks);
  }, [draftStyle, draftRounds, curDraftRoundPk, teamMap, teams?.length]);

  // Compute pick order captains for shuffle draft (original logic)
  const pickOrderCaptains = useMemo((): PickOrderCaptain[] => {
    if (draftStyle !== 'shuffle') return [];

    const teamList = teams || [];
    const allTeams = teamList
      .map((team) => ({
        team,
        totalMmr: getTeamMmr(team),
        isCurrent: false,
        pickOrder: 0,
        isMaxed: isTeamMaxed(team),
      }))
      .sort((a, b) => {
        if (a.isMaxed !== b.isMaxed) return a.isMaxed ? 1 : -1;
        return a.totalMmr - b.totalMmr;
      });

    let activeIdx = 0;
    allTeams.forEach((t) => {
      if (!t.isMaxed) {
        t.pickOrder = ++activeIdx;
        t.isCurrent = activeIdx === 1;
      } else {
        t.pickOrder = 0;
      }
    });

    return allTeams;
  }, [draftStyle, teams]);

  // For snake/normal draft, show upcoming picks
  if (draftStyle !== 'shuffle' && upcomingPicks.length > 0) {
    return (
      <div className="shrink-0">
        <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-2 md:mb-3 text-center lg:text-left">
          Upcoming Picks
        </h3>
        <div className="flex flex-row justify-center lg:justify-start gap-1 md:gap-1.5 flex-wrap">
          {upcomingPicks.map((pick, idx) => (
            <TeamPopover key={`${pick.round.pk}-${idx}`} team={pick.team}>
              <div
                className={cn(
                  'flex flex-row md:flex-col items-center p-1 md:p-1.5 rounded-lg cursor-pointer transition-all',
                  'gap-1.5 md:gap-0',
                  'md:min-w-[70px]',
                  pick.isCurrent
                    ? 'bg-green-950/40 border-2 border-green-500'
                    : 'bg-muted/30 border border-muted hover:bg-muted/50'
                )}
                data-testid={`upcoming-pick-${idx}`}
              >
                <Badge
                  variant={pick.isCurrent ? 'default' : 'secondary'}
                  className={cn(
                    'text-[9px] md:text-[10px] px-1 md:mb-0.5',
                    pick.isCurrent && 'bg-green-600'
                  )}
                >
                  {pick.isCurrent ? 'NOW' : `#${pick.pickNumber}`}
                </Badge>

                {pick.team.captain ? (
                  <UserAvatar
                    user={pick.team.captain}
                    size="lg"
                    className={cn(
                      'w-8 h-8 md:w-10 md:h-10 shrink-0',
                      pick.isCurrent && 'ring-2 ring-green-500'
                    )}
                  />
                ) : (
                  <div className="w-8 h-8 md:w-10 md:h-10 rounded-full bg-muted shrink-0" />
                )}

                <div className="flex flex-row md:flex-col items-center md:items-center gap-1 md:gap-0">
                  <span className="text-[10px] md:text-[10px] font-medium truncate max-w-[60px] md:max-w-[65px] md:mt-0.5 md:text-center">
                    {pick.team.captain ? DisplayName(pick.team.captain) : 'No Captain'}
                  </span>
                  <span className="text-xs md:text-sm font-medium text-muted-foreground">
                    {getTeamMmr(pick.team).toLocaleString()} · {(pick.team.members?.length || 1) - 1}/4
                  </span>
                </div>
              </div>
            </TeamPopover>
          ))}
        </div>
      </div>
    );
  }

  // For shuffle draft, show the original pick order view
  return (
    <div className="shrink-0">
      <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-2 md:mb-3 text-center lg:text-left">
        Pick Order
      </h3>
      <div className="flex flex-row justify-center lg:justify-start gap-1 md:gap-1.5 flex-wrap">
        {pickOrderCaptains.map((captain, idx) => (
          <TeamPopover key={captain.team.pk || idx} team={captain.team}>
            <div
              className={cn(
                'flex flex-row md:flex-col items-center p-1 md:p-1.5 rounded-lg cursor-pointer transition-all',
                'gap-1.5 md:gap-0',
                'md:min-w-[70px]',
                captain.isMaxed
                  ? 'bg-muted/20 border border-muted/50 opacity-50 grayscale'
                  : captain.isCurrent
                    ? 'bg-green-950/40 border-2 border-green-500'
                    : 'bg-muted/30 border border-muted hover:bg-muted/50'
              )}
              data-testid={`pick-order-captain-${idx}`}
            >
              <Badge
                variant={captain.isMaxed ? 'outline' : captain.isCurrent ? 'default' : 'secondary'}
                className={cn(
                  'text-[9px] md:text-[10px] px-1 md:mb-0.5',
                  captain.isCurrent && 'bg-green-600',
                  captain.isMaxed && 'bg-muted/50 text-muted-foreground'
                )}
              >
                {captain.isMaxed ? 'DONE' : captain.isCurrent ? 'NOW' : getOrdinal(captain.pickOrder)}
              </Badge>

              {captain.team.captain ? (
                <UserAvatar
                  user={captain.team.captain}
                  size="lg"
                  className={cn(
                    'w-8 h-8 md:w-10 md:h-10 shrink-0',
                    captain.isCurrent && 'ring-2 ring-green-500'
                  )}
                />
              ) : (
                <div className="w-8 h-8 md:w-10 md:h-10 rounded-full bg-muted shrink-0" />
              )}

              <div className="flex flex-row md:flex-col items-center md:items-center gap-1 md:gap-0">
                <span className="text-[10px] md:text-[10px] font-medium truncate max-w-[60px] md:max-w-[65px] md:mt-0.5 md:text-center">
                  {captain.team.captain ? DisplayName(captain.team.captain) : 'No Captain'}
                </span>
                <span className="text-xs md:text-sm font-medium text-muted-foreground">
                  {captain.totalMmr.toLocaleString()} · {(captain.team.members?.length || 1) - 1}/4
                </span>
              </div>
            </div>
          </TeamPopover>
        ))}
      </div>
    </div>
  );
});

PickOrderSection.displayName = 'PickOrderSection';
