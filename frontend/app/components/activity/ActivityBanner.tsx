import { Radio } from 'lucide-react';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import type {
  ActivityDraftList,
  ActivityTeamDraftEntry,
  ActivityView,
} from '~/lib/activity-types';
import { sameView, useActivityViewStore } from '~/store/activityViewStore';
import { useActivityMenu } from './ActivityHeader';
import { useLeaveGuard } from './LeaveDraftConfirm';

interface Entry {
  view: Extract<ActivityView, { id: number }>;
  label: string;
  entry: ActivityTeamDraftEntry;
}

type Banner = { kind: 'mine'; target: Entry } | { kind: 'many'; count: number };

function entries(drafts: ActivityDraftList): Entry[] {
  const team = drafts.team_draft;
  return [
    ...(team
      ? [
          {
            view: { kind: 'team' as const, id: team.id },
            label: 'Team draft',
            entry: team,
          },
        ]
      : []),
    ...drafts.hero_drafts.map((d) => ({
      view: { kind: 'hero' as const, id: d.id },
      label: d.label,
      entry: d,
    })),
  ];
}

export function activityBanner(
  view: ActivityView | null,
  drafts: ActivityDraftList | null,
): Banner | null {
  if (!view || !drafts) return null;
  const all = entries(drafts);
  const viewed = all.find((e) => sameView(e.view, view));
  if (view.kind !== 'bracket' && !viewed) return null;
  const viewedLive = !!viewed && viewed.entry.status !== 'finished';
  const viewedMine = !!viewed?.entry.involves_me;
  if (viewedLive && viewedMine) return null;

  const live = all.filter((e) => e.entry.status !== 'finished');
  const mine = live.filter((e) => e.entry.involves_me && e !== viewed);
  if (mine.length === 1) return { kind: 'mine', target: mine[0] };
  if (!viewedLive && live.length > 0)
    return { kind: 'many', count: live.length };
  return null;
}

export function ActivityBanner() {
  const view = useActivityViewStore((s) => s.view);
  const drafts = useActivityViewStore((s) => s.drafts);
  const guard = useLeaveGuard();
  const banner = activityBanner(view, drafts);
  if (!banner) return null;

  return (
    <div
      role="status"
      data-testid="activity-banner"
      className="flex w-full min-w-0 shrink-0 items-center gap-2 border-b border-success/40 bg-success/10 px-2 py-1.5 text-sm text-foreground sm:px-4"
    >
      <Radio className="size-4 shrink-0 text-success" />
      {banner.kind === 'mine' ? (
        <>
          <span className="min-w-0 truncate">
            {banner.target.label} is live
          </span>
          <PrimaryButton
            size="sm"
            className="ml-auto shrink-0"
            data-testid="activity-banner-view"
            onClick={() =>
              guard(() =>
                useActivityViewStore
                  .getState()
                  .setView(banner.target.view, 'banner'),
              )
            }
          >
            View
          </PrimaryButton>
        </>
      ) : (
        <>
          <span className="min-w-0 truncate">
            {banner.count} {banner.count === 1 ? 'draft' : 'drafts'} live
          </span>
          <SecondaryButton
            size="sm"
            className="ml-auto shrink-0"
            data-testid="activity-banner-choose"
            onClick={() => useActivityMenu.getState().setOpen(true)}
          >
            Choose
          </SecondaryButton>
        </>
      )}
    </div>
  );
}
