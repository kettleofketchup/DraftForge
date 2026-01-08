import { cn } from '~/lib/utils';
import { Badge } from '~/components/ui/badge';
import { Card } from '~/components/ui/card';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';

interface TeamPickStatus {
  team: TeamType;
  totalMmr: number;
  picksMade: number;
  pickOrder: number;
}

export const ShufflePickOrder: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const getTeamPickStatus = (): TeamPickStatus[] => {
    const teams = tournament?.teams || [];

    const statuses = teams.map((team) => {
      const totalMmr = getTeamMmr(team);

      const picksMade =
        draft?.draft_rounds?.filter(
          (r) => r.choice && r.captain?.pk === team.captain?.pk
        ).length || 0;

      return { team, totalMmr, picksMade, pickOrder: 0 };
    });

    statuses.sort((a, b) => a.totalMmr - b.totalMmr);
    statuses.forEach((s, idx) => {
      s.pickOrder = idx + 1;
    });

    return statuses;
  };

  const getPickDelta = (
    picksMade: number,
    allStatuses: TeamPickStatus[]
  ): string => {
    const avgPicks =
      allStatuses.reduce((sum, s) => sum + s.picksMade, 0) / allStatuses.length;
    const delta = picksMade - avgPicks;

    if (delta > 0.5) return `+${Math.round(delta)}`;
    if (delta < -0.5) return `${Math.round(delta)}`;
    return '0';
  };

  const isCurrentPicker = (team: TeamType): boolean => {
    return curDraftRound?.captain?.pk === team.captain?.pk;
  };

  const statuses = getTeamPickStatus();

  return (
    <div className="mb-4">
      <h3 className="text-sm font-medium text-muted-foreground mb-2">
        Pick Order
      </h3>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {statuses.map((status) => (
          <Card
            key={status.team.pk}
            className={cn(
              'flex-shrink-0 p-3 min-w-[140px]',
              isCurrentPicker(status.team)
                ? 'border-green-500 border-2 bg-green-950/20'
                : 'border-muted'
            )}
          >
            <div className="flex flex-col gap-1">
              <span className="font-medium text-sm truncate">
                {status.team.name}
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
