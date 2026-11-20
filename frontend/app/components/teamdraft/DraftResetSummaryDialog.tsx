import type {
  DraftResetReport,
  DraftResetTeamOutcome,
} from '~/components/api/types';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ScrollArea } from '~/components/ui/scroll-area';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import {
  countOf,
  ineligibleReasonText,
  usageBreakdown,
} from './draftResetText';

type Props = {
  report: DraftResetReport | null;
  onOpenChange: (open: boolean) => void;
};

function TeamOutcomeRow({ team }: { team: DraftResetTeamOutcome }) {
  return (
    <li
      className="flex flex-col gap-1 rounded-md border border-border bg-base-200/40 p-3"
      data-testid="draft-reset-team"
    >
      <span className="font-semibold">{team.name}</span>
      <span className="text-sm text-muted-foreground">
        {ineligibleReasonText(team.reason)}
      </span>
      {team.captain && (
        <span className="flex items-center gap-2 text-sm">
          <UserAvatar user={team.captain} size="xs" />
          <span className="text-muted-foreground">Captain</span>
          <span>{DisplayName(team.captain)}</span>
        </span>
      )}
      {team.usage?.length ? (
        <span className="text-sm">
          Kept because {usageBreakdown(team.usage)}{' '}
          {team.usage.reduce((n, u) => n + u.count, 0) === 1 ? 'uses' : 'use'}{' '}
          it
        </span>
      ) : null}
    </li>
  );
}

function OutcomeSection({
  title,
  teams,
  testId,
}: {
  title: string;
  teams: DraftResetTeamOutcome[];
  testId: string;
}) {
  if (!teams.length) return null;
  return (
    <section className="flex flex-col gap-2" data-testid={testId}>
      <h3 className="text-sm font-semibold">
        {title} ({teams.length})
      </h3>
      <ul className="flex flex-col gap-2">
        {teams.map((team) => (
          <TeamOutcomeRow key={team.pk} team={team} />
        ))}
      </ul>
    </section>
  );
}

/** Names the teams a draft reset dropped or kept; stays open until closed. */
export function DraftResetSummaryDialog({ report, onOpenChange }: Props) {
  const reset = report?.reset_team_names ?? [];
  const resetCount = report?.reset_teams.length ?? 0;
  return (
    <Dialog open={report !== null} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[calc(100%-2rem)] sm:max-w-lg"
        data-testid="draft-reset-summary"
      >
        <DialogHeader>
          <DialogTitle>Draft reset summary</DialogTitle>
          <DialogDescription>
            {countOf(resetCount, 'team', 'teams')} reset to captains
            {reset.length ? `: ${reset.map((t) => t.name).join(', ')}` : ''}
          </DialogDescription>
        </DialogHeader>
        {report && (
          <ScrollArea className="max-h-[60vh] pr-4">
            <div className="flex flex-col gap-4">
              <OutcomeSection
                title="Dropped"
                teams={report.dropped_teams}
                testId="draft-reset-dropped"
              />
              <OutcomeSection
                title="Kept out of the draft"
                teams={report.kept_teams}
                testId="draft-reset-kept"
              />
            </div>
          </ScrollArea>
        )}
        <DialogFooter>
          <SecondaryButton
            onClick={() => onOpenChange(false)}
            data-testid="draft-reset-summary-close"
          >
            Close
          </SecondaryButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
