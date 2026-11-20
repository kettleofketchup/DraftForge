import { TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import type {
  LeadershipProblem,
  ManagedTeam,
} from '~/components/api/teamManagementAPI';
import { SecondaryButton } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { leadershipProblemParts } from './leadershipProblemText';
import type { PendingTeamAction } from './pendingTeamAction';
import { clearDeputyRequest, reseatCaptainRequest } from './teamActionCopy';

export interface LeadershipProblemsBannerProps {
  team: ManagedTeam;
  onRequestAction: (request: PendingTeamAction) => void;
  onChooseCaptain: () => void;
  onChooseDeputy: () => void;
  disabled?: boolean;
}

const NOT_ON_ROSTER = "isn't on this team's roster.";

/** Role prefix and text around the subject's name, e.g. "Captain <name> isn't on…". */
function describe(code: string): { before: string; after: string } | null {
  switch (code) {
    case 'captain_not_member':
      return { before: 'Captain ', after: ` ${NOT_ON_ROSTER}` };
    case 'deputy_not_member':
      return { before: 'Deputy ', after: ` ${NOT_ON_ROSTER}` };
    case 'deputy_is_captain':
      return { before: '', after: ' is both captain and deputy.' };
    default:
      return null;
  }
}

const fixButton = 'w-full min-h-11 sm:w-auto sm:min-h-8';

/**
 * The manage dialog's leadership problems: an error panel (the team cards
 * flag the same problems with a destructive badge), one row per problem
 * with the player, a plain sentence and that problem's fixes.
 */
export function LeadershipProblemsBanner({
  team,
  onRequestAction,
  onChooseCaptain,
  onChooseDeputy,
  disabled = false,
}: LeadershipProblemsBannerProps) {
  const problems = team.leadership_problems;
  if (problems.length === 0) return null;

  const fixesFor = (problem: LeadershipProblem): ReactNode => {
    const captain = team.captain;
    if (problem.code === 'captain_not_member' && captain) {
      return (
        <>
          <SecondaryButton
            size="sm"
            className={fixButton}
            disabled={disabled}
            onClick={() => onRequestAction(reseatCaptainRequest(team, captain))}
          >
            Reseat {DisplayName(captain)} as member
          </SecondaryButton>
          <SecondaryButton
            size="sm"
            className={fixButton}
            disabled={disabled}
            onClick={onChooseCaptain}
          >
            Choose another captain
          </SecondaryButton>
        </>
      );
    }
    if (
      problem.code === 'deputy_not_member' ||
      problem.code === 'deputy_is_captain'
    ) {
      return (
        <>
          <SecondaryButton
            size="sm"
            className={fixButton}
            disabled={disabled}
            onClick={() => onRequestAction(clearDeputyRequest(team))}
          >
            Clear deputy
          </SecondaryButton>
          <SecondaryButton
            size="sm"
            className={fixButton}
            disabled={disabled}
            onClick={onChooseDeputy}
          >
            Choose another deputy
          </SecondaryButton>
        </>
      );
    }
    return null;
  };

  const heading = `${problems.length} leadership problem${problems.length === 1 ? '' : 's'}`;

  return (
    <section
      role="alert"
      aria-labelledby="team-leadership-banner-heading"
      data-testid="team-leadership-banner"
      className="rounded-lg border border-error/70 bg-error-surface p-4 text-error-tint shadow-sm"
    >
      <h3
        id="team-leadership-banner-heading"
        className="flex items-center gap-2 text-base font-semibold"
      >
        <TriangleAlert className="size-5 shrink-0 text-error" aria-hidden />
        {heading}
      </h3>
      <ul className="mt-2 flex flex-col divide-y divide-error/30">
        {problems.map((problem, i) => {
          const { subject } = leadershipProblemParts(problem, team);
          const copy = describe(problem.code);
          const fixes = fixesFor(problem);
          return (
            <li
              key={`${problem.code}-${i}`}
              data-testid={`team-leadership-banner-row-${problem.code}`}
              className="flex flex-col gap-3 py-3 last:pb-0 md:flex-row md:items-center md:justify-between"
            >
              <div className="flex min-w-0 items-center gap-3">
                {subject ? (
                  <span
                    aria-hidden
                    className="flex shrink-0"
                    data-testid="team-leadership-banner-avatar"
                  >
                    <UserAvatar user={subject} size="md" />
                  </span>
                ) : null}
                <p
                  className="min-w-0 text-sm leading-snug wrap-anywhere"
                  data-testid="team-leadership-banner-text"
                >
                  {subject && copy ? (
                    <>
                      {copy.before}
                      <span className="font-semibold">
                        {DisplayName(subject)}
                      </span>
                      {copy.after}
                    </>
                  ) : (
                    problem.message
                  )}
                </p>
              </div>
              {fixes ? (
                <div
                  className="flex flex-col gap-2 sm:flex-row sm:flex-wrap md:shrink-0 md:justify-end"
                  data-testid="team-leadership-banner-actions"
                >
                  {fixes}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
