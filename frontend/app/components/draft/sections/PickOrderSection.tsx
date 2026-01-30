import { memo } from 'react';
import { Badge } from '~/components/ui/badge';
import { TeamPopover } from '~/components/team';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { AvatarUrl, DisplayName } from '~/components/user/avatar';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/index';

const MAX_TEAM_SIZE = 5;

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

  // Compute pick order captains
  const pickOrderCaptains = (() => {
    const teamList = teams || [];
    const isShuffle = draftStyle === 'shuffle';

    if (isShuffle) {
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
    } else {
      const currentRoundIndex = draftRounds?.findIndex(
        (r) => r.pk === curDraftRoundPk
      ) ?? 0;

      const upcomingRounds = draftRounds?.slice(currentRoundIndex, currentRoundIndex + 4) || [];
      const seenTeamPks = new Set<number>();
      const result: PickOrderCaptain[] = [];

      for (const round of upcomingRounds) {
        const team = teamList.find((t) => t.captain?.pk === round.captain?.pk);
        if (team && !seenTeamPks.has(team.pk!)) {
          seenTeamPks.add(team.pk!);
          result.push({
            team,
            totalMmr: getTeamMmr(team),
            isCurrent: result.length === 0,
            pickOrder: result.length + 1,
            isMaxed: isTeamMaxed(team),
          });
        }
      }

      for (const team of teamList) {
        if (!seenTeamPks.has(team.pk!) && isTeamMaxed(team)) {
          result.push({
            team,
            totalMmr: getTeamMmr(team),
            isCurrent: false,
            pickOrder: 0,
            isMaxed: true,
          });
        }
      }

      return result;
    }
  })();

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
                <img
                  src={AvatarUrl(captain.team.captain)}
                  alt={captain.team.captain?.username || 'Captain'}
                  className={cn(
                    'w-8 h-8 md:w-10 md:h-10 rounded-full transition-all shrink-0',
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
