import { useMemo } from 'react';
import { Badge } from '~/components/ui/badge';
import { DataTable } from '~/components/ui/data-table';
import { DisplayName } from '~/components/user/avatar';
import { formatRating } from './format';
import {
  makeModerationColumns,
  type MakeModerationColumnsOptions,
} from './moderationColumns';
import type { EventCaptainReviews } from './schemas';

export type ReviewModerationTableProps = MakeModerationColumnsOptions & {
  captain: EventCaptainReviews;
};

const OWN_SNAPSHOT_NOTE =
  'You captained this team. Another admin has to moderate its reviews.';

export function ReviewModerationTable({
  captain,
  traits,
  onVoid,
  onUnvoid,
  pendingPk,
}: ReviewModerationTableProps) {
  const columns = useMemo(
    () => makeModerationColumns({ traits, onVoid, onUnvoid, pendingPk }),
    [traits, onVoid, onUnvoid, pendingPk],
  );
  const id = captain.org_user_id;
  const rating = captain.aggregate?.rating ?? null;
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
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Badge variant="outline">
            {captain.released ? 'Released' : 'Not released'}
          </Badge>
          {rating !== null && (
            <span className="text-sm tabular-nums">
              {formatRating(rating)} overall
            </span>
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
