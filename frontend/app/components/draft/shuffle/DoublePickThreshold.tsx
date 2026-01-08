import { Zap } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '~/components/ui/alert';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';

export const DoublePickThreshold: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const user = useUserStore((state) => state.user);
  const isStaff = useUserStore((state) => state.isStaff);

  if (draft?.draft_style !== 'shuffle') return null;

  const isCurrentPicker = curDraftRound?.captain?.pk === user?.pk;
  if (!isCurrentPicker && !isStaff()) return null;

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
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
    <Alert
      className={cn(
        'mb-4',
        canDoublePick ? 'border-green-500 bg-green-950/20' : 'border-muted'
      )}
    >
      <Zap
        className={cn(
          'h-4 w-4',
          canDoublePick ? 'text-green-500' : 'text-muted-foreground'
        )}
      />
      <AlertTitle className="text-sm font-medium">
        Double Pick Threshold
      </AlertTitle>
      <AlertDescription className="text-sm">
        <div className="flex flex-col gap-1 mt-1">
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
      </AlertDescription>
    </Alert>
  );
};
