import { ChevronDown, TriangleAlert } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { TeamType } from '~/components/tournament/types';
import {
  brandErrorBg,
  brandErrorCard,
  SecondaryButton,
} from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import { cn } from '~/lib/utils';
import type { LeadershipProblem } from '../leadershipProblemSchema';
import { leadershipProblemSentence } from './LeadershipProblemBadge';

export interface TeamLeadershipAlertProps {
  teams: readonly TeamType[];
  canEdit: boolean;
  onReview: (team: TeamType) => void;
}

/** Teams-tab summary of every team whose captain or deputy needs fixing. */
export function TeamLeadershipAlert({
  teams,
  canEdit,
  onReview,
}: TeamLeadershipAlertProps) {
  const [open, setOpen] = useState(true);
  const affected = useMemo(
    () => teams.filter((t) => (t.leadership_problems?.length ?? 0) > 0),
    [teams],
  );

  if (!canEdit || affected.length === 0) return null;

  const label = `Teams with leadership problems (${affected.length})`;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn('rounded-lg shadow-md w-full mb-4', brandErrorBg)}
      data-testid="team-leadership-alert"
    >
      <CollapsibleTrigger
        className="grid grid-cols-[auto_1fr_auto] items-center gap-3 w-full p-3 sm:p-4 text-destructive font-bold cursor-pointer min-h-11"
        data-testid="team-leadership-alert-toggle"
        aria-label={open ? `Hide ${label}` : `Show ${label}`}
      >
        <TriangleAlert className="size-5" aria-hidden />
        <span className="truncate text-center">{label}</span>
        <ChevronDown
          className={cn(
            'size-5 transition-transform duration-200',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden">
        <ul className="flex flex-col gap-2 p-3 sm:p-4 pt-0 sm:pt-0">
          {affected.map((team) => (
            <li
              key={team.pk}
              data-testid={`team-leadership-alert-row-${team.pk}`}
              className={cn(
                'flex flex-col gap-2 rounded-lg p-3 sm:flex-row sm:items-center',
                brandErrorCard,
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="font-bold break-words">{team.name}</div>
                <ul className="text-sm">
                  {(team.leadership_problems ?? []).map(
                    (problem: LeadershipProblem, i: number) => (
                      <li key={`${problem.code}-${i}`}>
                        {leadershipProblemSentence(problem, team)}
                      </li>
                    ),
                  )}
                </ul>
              </div>
              <SecondaryButton
                size="sm"
                className="min-h-11 sm:min-h-0"
                onClick={() => onReview(team)}
                aria-label={`Review ${team.name}`}
              >
                Review
              </SecondaryButton>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
