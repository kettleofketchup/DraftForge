import { Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import type { TeamType, UserType } from '~/index';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';

export const DoublePickThreshold: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);

  if (draft?.draft_style !== 'shuffle') return null;

  const isCurrentPicker = curDraftRound?.captain?.pk === currentUser?.pk;
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

  const getCurrentTeam = (): TeamType | undefined => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === curDraftRound?.captain?.pk
    );
  };

  const getThresholdTeam = (): { team: TeamType; mmr: number } | null => {
    const teams = tournament?.teams || [];
    const currentTeam = getCurrentTeam();
    if (!currentTeam) return null;

    const otherTeams = teams
      .filter((t) => t.pk !== currentTeam.pk)
      .map((t) => ({ team: t, mmr: getTeamMmr(t) }))
      .sort((a, b) => a.mmr - b.mmr);

    return otherTeams[0] || null;
  };

  const currentTeam = getCurrentTeam();
  const threshold = getThresholdTeam();

  if (!currentTeam || !threshold) return null;

  const currentMmr = getTeamMmr(currentTeam);
  const canDoublePick = currentMmr < threshold.mmr;

  return (
    <Card
      className={cn(
        'mb-4',
        canDoublePick ? 'border-green-500 bg-green-950/20' : 'border-muted'
      )}
    >
      <CardHeader className="pb-2 pt-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Zap
            className={cn(
              'h-4 w-4',
              canDoublePick ? 'text-green-500' : 'text-muted-foreground'
            )}
          />
          Double Pick Threshold
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
              ({threshold.team.name})
            </span>
          </span>
          <span className="text-muted-foreground">
            Your current MMR:{' '}
            <span
              className={cn(
                'font-medium',
                canDoublePick ? 'text-green-400' : 'text-foreground'
              )}
            >
              {currentMmr.toLocaleString()}
            </span>
            {canDoublePick && (
              <span className="text-green-400 ml-2">
                ({(threshold.mmr - currentMmr).toLocaleString()} buffer)
              </span>
            )}
          </span>
        </div>
      </CardContent>
    </Card>
  );
};
