import { TrendingDown, TrendingUp } from 'lucide-react';
import React from 'react';
import { Badge } from '~/components/ui/badge';
import { Card, CardContent } from '~/components/ui/card';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';

export const DraftBalanceDisplay: React.FC = () => {
  const draft = useUserStore((state) => state.draft);
  const draftPredictedMMRs = useTournamentStore(
    (state) => state.draftPredictedMMRs,
  );

  if (!draft || !draft.current_draft_first_pick_mmr) {
    return null;
  }

  const formatMMR = (mmr: number) => {
    return mmr.toLocaleString();
  };
  const firstPickMMR = () =>
    draft.draft_style === 'snake'
      ? draftPredictedMMRs?.snake_first_pick_mmr
      : draftPredictedMMRs?.normal_first_pick_mmr;
  const lastPickMMR = () =>
    draft.draft_style === 'snake'
      ? draftPredictedMMRs?.snake_last_pick_mmr
      : draftPredictedMMRs?.normal_last_pick_mmr;

  const difference = () => Math.abs(firstPickMMR() - lastPickMMR());
  const avg = () => (firstPickMMR() + lastPickMMR()) / 2;
  const balancePercentage = () =>
    avg() > 0 ? (difference() / avg()) * 100 : 0;

  const isBalanced = balancePercentage() < 10; // Less than 10% difference is considered balanced

  return (
    <Card className="w-full">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">
            Draft Balance ({draft.draft_style === 'snake' ? 'Snake' : 'Normal'}{' '}
            Style)
          </h3>
          <Badge
            variant={isBalanced ? 'default' : 'secondary'}
            className={
              isBalanced
                ? 'bg-green-100 text-green-800'
                : 'bg-orange-100 text-orange-800'
            }
          >
            {balancePercentage().toFixed(1)}% imbalance
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-blue-500" />
            <div>
              <div className="text-muted-foreground">First Pick</div>
              <div className="font-medium">{formatMMR(firstPickMMR())} MMR</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-orange-500" />
            <div>
              <div className="text-muted-foreground">Last Pick</div>
              <div className="font-medium">{formatMMR(lastPickMMR())} MMR</div>
            </div>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t">
          <div className="flex justify-between items-center text-xs">
            <span className="text-muted-foreground">MMR Difference:</span>
            <span className="font-medium">{formatMMR(difference())}</span>
          </div>
        </div>

        {/* Visual balance indicator */}
        <div className="mt-3">
          <div className="flex h-2 rounded-full overflow-hidden bg-muted">
            <div
              className="bg-blue-500 transition-all duration-300"
              style={{
                width: `${(firstPickMMR() / (firstPickMMR() + lastPickMMR())) * 100}%`,
              }}
            />
            <div
              className="bg-orange-500 transition-all duration-300"
              style={{
                width: `${(lastPickMMR() / (firstPickMMR() + lastPickMMR())) * 100}%`,
              }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>First Pick Team</span>
            <span>Last Pick Team</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
