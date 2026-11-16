import { Check, ChevronDown, ExternalLink } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { postActivityView } from '~/lib/activity-api';
import { activityExternalUrl } from '~/lib/activity-session';
import type {
  ActivityDraftList,
  ActivityView,
  DraftStatus,
} from '~/lib/activity-types';
import { openExternal } from '~/lib/discord';
import { cn } from '~/lib/utils';
import { sameView, useActivityViewStore } from '~/store/activityViewStore';
import { LeaveDraftConfirm, useLeaveGuard } from './LeaveDraftConfirm';

const STATUS_LABEL: Record<DraftStatus, string> = {
  waiting: 'Waiting',
  drafting: 'Drafting',
  paused: 'Paused',
  finished: 'Finished',
};

const STATUS_CLASS: Record<DraftStatus, string> = {
  waiting: 'border-info/40 text-info',
  drafting: 'border-success/40 text-success',
  paused: 'border-warning/40 text-warning',
  finished: 'text-muted-foreground',
};

function StatusChip({ status }: { status: DraftStatus }) {
  return (
    <Badge variant="outline" className={cn('ml-auto', STATUS_CLASS[status])}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

function viewLabel(
  view: ActivityView | null,
  drafts: ActivityDraftList | null,
): string {
  if (!view) return 'Choose a view';
  if (view.kind === 'bracket') return 'Bracket';
  if (view.kind === 'team') return 'Team draft';
  return (
    drafts?.hero_drafts.find((d) => d.id === view.id)?.label ??
    `Hero draft ${view.id}`
  );
}

export function ActivityHeader() {
  const view = useActivityViewStore((s) => s.view);
  const drafts = useActivityViewStore((s) => s.drafts);
  const guard = useLeaveGuard();
  const externalUrl = view ? activityExternalUrl(view) : undefined;

  const select = (target: ActivityView) => {
    if (sameView(useActivityViewStore.getState().view, target)) return;
    guard(() => useActivityViewStore.getState().setView(target, 'menu'));
  };

  const openInBrowser = () => {
    if (!view || !externalUrl) return;
    guard(() => {
      postActivityView({ action: 'open_external', view });
      void openExternal(externalUrl);
    });
  };

  const isCurrent = (target: ActivityView) => sameView(view, target);
  const teamDraft = drafts?.team_draft;

  return (
    <div
      className="flex w-full min-w-0 shrink-0 items-center gap-2 border-b border-border bg-background px-2 py-1.5 sm:px-4"
      data-testid="activity-header"
    >
      {drafts?.tournament?.name && (
        <span
          className="min-w-0 max-w-[35%] truncate text-sm font-semibold text-foreground"
          data-testid="activity-tournament-name"
        >
          {drafts.tournament.name}
        </span>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SecondaryButton
            size="sm"
            className="min-w-0 max-w-[60%] sm:max-w-xs"
            data-testid="activity-menu-trigger"
          >
            <span className="truncate">{viewLabel(view, drafts)}</span>
            <ChevronDown className="size-4 shrink-0" />
          </SecondaryButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          className="w-[min(20rem,calc(100vw-2rem))]"
        >
          {teamDraft && (
            <DropdownMenuItem
              onSelect={() => select({ kind: 'team', id: teamDraft.id })}
              data-testid="activity-menu-team"
            >
              {isCurrent({ kind: 'team', id: teamDraft.id }) && (
                <Check className="size-4" />
              )}
              <span className="truncate">Team draft</span>
              <StatusChip status={teamDraft.status} />
            </DropdownMenuItem>
          )}
          {drafts && drafts.hero_drafts.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Hero drafts</DropdownMenuLabel>
              {drafts.hero_drafts.map((d) => (
                <DropdownMenuItem
                  key={d.id}
                  onSelect={() => select({ kind: 'hero', id: d.id })}
                  data-testid={`activity-menu-hero-${d.id}`}
                >
                  {isCurrent({ kind: 'hero', id: d.id }) && (
                    <Check className="size-4" />
                  )}
                  <span className="truncate">{d.label}</span>
                  <StatusChip status={d.status} />
                </DropdownMenuItem>
              ))}
            </>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => select({ kind: 'bracket' })}
            data-testid="activity-menu-bracket"
          >
            {isCurrent({ kind: 'bracket' }) && <Check className="size-4" />}
            <span>Bracket</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <SecondaryButton
        size="sm"
        className="ml-auto shrink-0"
        onClick={openInBrowser}
        disabled={!externalUrl}
        aria-label="Open in browser"
        data-testid="activity-open-browser"
      >
        <ExternalLink className="size-4" />
        <span className="hidden sm:inline">Open in browser</span>
      </SecondaryButton>
      <LeaveDraftConfirm />
    </div>
  );
}
