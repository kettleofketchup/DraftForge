import { AlertTriangle } from 'lucide-react';
import { cn } from '~/lib/utils';
import { Badge } from '~/components/ui/badge';
import { Card } from '~/components/ui/card';
import { useUserStore } from '~/store/userStore';
import { AvatarUrl, type TeamType, type UserType } from '~/index';
import type { DraftRoundType } from '../types';

const MAX_TEAM_SIZE = 5;

interface TeamPickStatus {
  team: TeamType;
  totalMmr: number;
  picksMade: number;
  pickOrder: number;
  isMaxed: boolean;
  hasMissingMmr: boolean;
}

export const ShufflePickOrder: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);

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

  const getTeamPickStatus = (): TeamPickStatus[] => {
    const teams = tournament?.teams || [];

    const statuses = teams.map((team) => {
      const totalMmr = getTeamMmr(team);
      const isMaxed = isTeamMaxed(team);
      const hasMissingMmr = !team.captain?.mmr || team.captain.mmr === 0;

      const picksMade =
        draft?.draft_rounds?.filter(
          (r: DraftRoundType) => r.choice && r.captain?.pk === team.captain?.pk
        ).length || 0;

      return { team, totalMmr, picksMade, pickOrder: 0, isMaxed, hasMissingMmr };
    });

    // Sort by MMR (lowest first) for pick order
    statuses.sort((a, b) => a.totalMmr - b.totalMmr);

    // Only assign pick order to non-maxed teams
    let orderCounter = 1;
    statuses.forEach((s) => {
      if (!s.isMaxed) {
        s.pickOrder = orderCounter++;
      } else {
        s.pickOrder = 0; // Maxed teams have no pick order
      }
    });

    return statuses;
  };

  const getPickDelta = (
    picksMade: number,
    allStatuses: TeamPickStatus[]
  ): string => {
    const activeStatuses = allStatuses.filter((s) => !s.isMaxed);
    if (activeStatuses.length === 0) return '0';

    const avgPicks =
      activeStatuses.reduce((sum, s) => sum + s.picksMade, 0) / activeStatuses.length;
    const delta = picksMade - avgPicks;

    if (delta > 0.5) return `+${Math.round(delta)}`;
    if (delta < -0.5) return `${Math.round(delta)}`;
    return '0';
  };

  const isCurrentPicker = (team: TeamType): boolean => {
    return curDraftRound?.captain?.pk === team.captain?.pk;
  };

  const statuses = getTeamPickStatus();
  const activeStatuses = statuses.filter((s) => !s.isMaxed);
  const captainsWithMissingMmr = statuses.filter((s) => s.hasMissingMmr && !s.isMaxed);

  return (
    <div className="mb-4">
      <h3 className="text-sm font-medium text-muted-foreground mb-2 text-center">
        Pick Order
      </h3>

      {/* Warning for captains with missing MMR */}
      {captainsWithMissingMmr.length > 0 && (
        <div className="mb-3 p-2 bg-red-950/30 border border-red-500 rounded-lg">
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <AlertTriangle className="h-4 w-4" />
            <span>
              {captainsWithMissingMmr.map((s) => s.team.captain?.nickname || s.team.captain?.username).join(', ')}
              {captainsWithMissingMmr.length === 1 ? ' has' : ' have'} no MMR set
            </span>
          </div>
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-2 justify-center">
        {activeStatuses.map((status) => (
          <Card
            key={status.team.pk}
            className={cn(
              'flex-shrink-0 p-3 min-w-[140px]',
              isCurrentPicker(status.team)
                ? 'border-green-500 border-2 bg-green-950/20'
                : 'border-muted'
            )}
          >
            <div className="flex flex-col gap-1 items-center">
              {/* Captain avatar */}
              <img
                src={AvatarUrl(status.team.captain)}
                alt={status.team.captain?.username || 'Captain'}
                className="w-10 h-10 rounded-full"
              />

              {/* Captain name */}
              <span className="font-medium text-sm truncate text-center">
                {status.team.captain?.nickname || status.team.captain?.username || 'Unknown'}
              </span>

              <span className="text-xs text-muted-foreground">
                {status.totalMmr.toLocaleString()} MMR
              </span>

              <div className="flex items-center gap-2 text-xs">
                <span>{status.picksMade} picks</span>
                <span
                  className={cn(
                    parseInt(getPickDelta(status.picksMade, statuses)) < 0
                      ? 'text-red-400'
                      : parseInt(getPickDelta(status.picksMade, statuses)) > 0
                        ? 'text-green-400'
                        : 'text-muted-foreground'
                  )}
                >
                  {getPickDelta(status.picksMade, statuses)}
                </span>
              </div>

              {isCurrentPicker(status.team) && (
                <Badge variant="default" className="mt-1 bg-green-600 text-xs">
                  PICKING
                </Badge>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};
