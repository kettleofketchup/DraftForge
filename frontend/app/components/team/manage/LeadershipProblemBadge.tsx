import { TriangleAlert } from 'lucide-react';

import { Badge } from '~/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { leadershipProblemParts } from './leadershipProblemText';

type Problem = Parameters<typeof leadershipProblemParts>[0];
type Team = Parameters<typeof leadershipProblemParts>[1];

export interface LeadershipProblemBadgeProps {
  problems: Problem[];
  team: Team;
}

export function leadershipProblemSentence(
  problem: Problem,
  team: Team,
): string {
  const { subject, text } = leadershipProblemParts(problem, team);
  return subject ? `${DisplayName(subject)} ${text}` : text;
}

export function LeadershipProblemBadge({
  problems,
  team,
}: LeadershipProblemBadgeProps) {
  if (problems.length === 0) return null;
  const sentences = problems.map((p) => leadershipProblemSentence(p, team));
  const label =
    problems.length === 1
      ? 'Leadership issue'
      : `${problems.length} leadership issues`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="destructive"
          tabIndex={0}
          aria-label={`${label}: ${sentences.join(' ')}`}
          data-testid="team-leadership-problem"
        >
          <TriangleAlert aria-hidden />
          {label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <ul className="flex flex-col gap-1">
          {sentences.map((sentence, i) => (
            <li key={`${problems[i].code}-${i}`}>{sentence}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}
