import { useMemo } from 'react';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { CELL_BREAKPOINT_QUERIES, DataTable } from '~/components/ui/data-table';
import { DisplayName } from '~/components/user/avatar';
import { useMediaQuery } from '~/hooks/useMediaQuery';
import { formatRating } from './format';
import {
  makeModerationColumns,
  type MakeModerationColumnsOptions,
} from './moderationColumns';
import { formatReleaseTime, releaseBadge } from './releaseState';
import type { EventCaptainReviews } from './schemas';

export type ReviewModerationTableProps = Omit<
  MakeModerationColumnsOptions,
  'stacked'
> & {
  captain: EventCaptainReviews;
  onRelease: (captain: EventCaptainReviews) => void;
};

const OWN_SNAPSHOT_NOTE =
  'You captained this team. Another org moderator, or site staff, has to release it. Your results show here once released.';

export function ReviewModerationTable({
  captain,
  viewerPk,
  traits,
  onVoid,
  onUnvoid,
  pendingPk,
  onRelease,
}: ReviewModerationTableProps) {
  const stacked = !useMediaQuery(CELL_BREAKPOINT_QUERIES.sm);
  const columns = useMemo(
    () =>
      makeModerationColumns({
        viewerPk,
        traits,
        onVoid,
        onUnvoid,
        pendingPk,
        stacked,
      }),
    [viewerPk, traits, onVoid, onUnvoid, pendingPk, stacked],
  );
  const id = captain.org_user_id;
  const rating = captain.aggregate?.rating ?? null;
  const badge = releaseBadge(captain.release_state);
  const own = captain.own_snapshot || captain.reviews === null;
  return (
    <div
      className="flex flex-col gap-2"
      data-testid={`leadership-moderation-${id}`}
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-medium break-words">
            {DisplayName(captain.captain)}
          </div>
          <div className="text-sm break-words text-muted-foreground">
            {captain.team_name}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 sm:justify-end">
          <Badge
            variant={badge.tone}
            data-testid={`leadership-release-state-${id}`}
          >
            {badge.label}
          </Badge>
          {captain.live_reviews !== null && captain.release_floor !== null && (
            <span
              className="text-sm tabular-nums text-muted-foreground"
              data-testid={`leadership-release-count-${id}`}
            >
              {captain.live_reviews} / {captain.release_floor} reviews
            </span>
          )}
          {captain.release_state === 'pending' &&
            captain.auto_release_at !== null && (
              <span
                className="text-sm text-muted-foreground"
                data-testid={`leadership-auto-release-${id}`}
              >
                auto-releases {formatReleaseTime(captain.auto_release_at)}
              </span>
            )}
          {captain.release_state === 'released' &&
            captain.released_at !== null && (
              <span
                className="text-sm break-words text-muted-foreground"
                data-testid={`leadership-released-by-${id}`}
              >
                {captain.released_by
                  ? `by ${DisplayName(captain.released_by)} · `
                  : ''}
                {formatReleaseTime(captain.released_at)}
              </span>
            )}
          {rating !== null && (
            <span className="text-sm tabular-nums">
              {formatRating(rating)} overall
            </span>
          )}
          {captain.can_release && !own && (
            <SecondaryButton
              type="button"
              size="sm"
              className="min-h-11 sm:min-h-8"
              data-testid={`leadership-release-${id}`}
              onClick={() => onRelease(captain)}
            >
              Release
            </SecondaryButton>
          )}
        </div>
      </div>
      {captain.own_snapshot || captain.reviews === null ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid={`leadership-moderation-own-${id}`}
        >
          {OWN_SNAPSHOT_NOTE}
        </p>
      ) : (
        <DataTable
          columns={columns}
          data={captain.reviews}
          getRowId={(r) => String(r.pk)}
          getRowTestId={(r) => `leadership-review-row-${r.pk}`}
          emptyMessage="No reviews"
          density="compact"
          data-testid={`leadership-moderation-table-${id}`}
        />
      )}
    </div>
  );
}
