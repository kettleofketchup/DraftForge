import { TriangleAlert } from 'lucide-react';

import type { ManagedTeam } from '~/components/api/teamManagementAPI';
import { Alert, AlertDescription, AlertTitle } from '~/components/ui/alert';
import { SecondaryButton } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import { leadershipProblemSentence } from './LeadershipProblemBadge';
import type { PendingTeamAction } from './pendingTeamAction';
import { clearDeputyRequest, reseatCaptainRequest } from './teamActionCopy';

export interface LeadershipProblemsBannerProps {
  team: ManagedTeam;
  onRequestAction: (request: PendingTeamAction) => void;
  onChooseCaptain: () => void;
  onChooseDeputy: () => void;
  disabled?: boolean;
}

export function LeadershipProblemsBanner({
  team,
  onRequestAction,
  onChooseCaptain,
  onChooseDeputy,
  disabled = false,
}: LeadershipProblemsBannerProps) {
  const problems = team.leadership_problems;
  if (problems.length === 0) return null;

  const deputyActions = (
    <>
      <SecondaryButton
        size="sm"
        disabled={disabled}
        onClick={() => onRequestAction(clearDeputyRequest(team))}
      >
        Clear deputy
      </SecondaryButton>
      <SecondaryButton size="sm" disabled={disabled} onClick={onChooseDeputy}>
        Choose another deputy
      </SecondaryButton>
    </>
  );

  return (
    <Alert variant="destructive" data-testid="team-leadership-banner">
      <TriangleAlert aria-hidden />
      <AlertTitle>Leadership problems ({problems.length})</AlertTitle>
      <AlertDescription>
        <ul className="flex flex-col gap-2">
          {problems.map((problem, i) => {
            const captain = team.captain;
            let actions = null;
            if (problem.code === 'captain_not_member' && captain) {
              actions = (
                <>
                  <SecondaryButton
                    size="sm"
                    disabled={disabled}
                    onClick={() =>
                      onRequestAction(reseatCaptainRequest(team, captain))
                    }
                  >
                    Reseat {DisplayName(captain)} as member
                  </SecondaryButton>
                  <SecondaryButton
                    size="sm"
                    disabled={disabled}
                    onClick={onChooseCaptain}
                  >
                    Choose another captain
                  </SecondaryButton>
                </>
              );
            } else if (
              problem.code === 'deputy_not_member' ||
              problem.code === 'deputy_is_captain'
            ) {
              actions = deputyActions;
            }
            return (
              <li
                key={`${problem.code}-${i}`}
                className="flex flex-wrap items-center gap-2"
              >
                <span>{leadershipProblemSentence(problem, team)}</span>
                {actions}
              </li>
            );
          })}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
