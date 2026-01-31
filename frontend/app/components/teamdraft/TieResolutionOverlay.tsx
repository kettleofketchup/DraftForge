import React from 'react';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { DIALOG_CSS } from '~/components/reusable/modal';
import type { TieResolution } from './types';

interface TieResolutionOverlayProps {
  tieResolution: TieResolution;
  onDismiss: () => void;
}

export const TieResolutionOverlay: React.FC<TieResolutionOverlayProps> = ({
  tieResolution,
  onDismiss,
}) => {
  const { tied_teams, roll_rounds, winner_id } = tieResolution;
  const winner = tied_teams.find((t) => t.id === winner_id);

  return (
    <Dialog open={true} onOpenChange={onDismiss}>
      <DialogContent className={`${DIALOG_CSS} max-w-md`}>
        <DialogHeader>
          <DialogTitle className="text-center text-xl">
            Tie Breaker!
          </DialogTitle>
        </DialogHeader>

        {/* Team headers */}
        <div
          className="grid gap-4 text-center"
          style={{
            gridTemplateColumns: `repeat(${tied_teams.length}, minmax(0, 1fr))`,
          }}
        >
          {tied_teams.map((team) => (
            <div
              key={team.id}
              className={team.id === winner_id ? 'font-bold' : ''}
            >
              <div className="truncate">{team.name}</div>
              <div className="text-sm text-muted-foreground">
                {team.mmr.toLocaleString()} MMR
              </div>
            </div>
          ))}
        </div>

        {/* Roll rounds */}
        <div className="space-y-2 mt-4">
          {roll_rounds.map((round, roundIdx) => (
            <div
              key={roundIdx}
              className="grid grid-cols-[auto,1fr] gap-2 items-center"
            >
              <span className="text-sm text-muted-foreground whitespace-nowrap">
                Round {roundIdx + 1}:
              </span>
              <div
                className="grid gap-4 text-center"
                style={{
                  gridTemplateColumns: `repeat(${tied_teams.length}, minmax(0, 1fr))`,
                }}
              >
                {tied_teams.map((team) => {
                  const roll = round.find((r) => r.team_id === team.id);
                  if (!roll) return <span key={team.id}>-</span>;

                  const isLastRound = roundIdx === roll_rounds.length - 1;
                  const isWinner = isLastRound && roll.team_id === winner_id;

                  return (
                    <span
                      key={roll.team_id}
                      className={isWinner ? 'text-green-600 font-bold' : ''}
                    >
                      {roll.roll} {isWinner && '✓'}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Winner announcement */}
        <div className="text-center mt-4 p-3 bg-green-50 dark:bg-green-950/20 rounded-lg">
          <span className="text-green-700 dark:text-green-300 font-medium">
            {winner?.name} picks next!
          </span>
        </div>

        <DialogFooter>
          <Button onClick={onDismiss} className="w-full">
            Continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
