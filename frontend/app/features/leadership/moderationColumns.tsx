import { Badge } from '~/components/ui/badge';
import { DestructiveButton, SecondaryButton } from '~/components/ui/buttons';
import type { AppColumnDef } from '~/components/ui/data-table';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { formatOrgDate } from '~/features/standing/periods';
import type { ModerationReview, Scores } from './schemas';

export interface ModerationTrait {
  key: string;
  label: string;
}

export interface MakeModerationColumnsOptions {
  /** Reviews this viewer wrote get no Void or Restore. */
  viewerPk: number | null;
  traits: ModerationTrait[];
  onVoid: (r: ModerationReview) => void;
  onUnvoid: (r: ModerationReview) => void;
  pendingPk: number | null;
}

const STATUS_LABELS = {
  '': 'Live',
  withdrawn: 'Withdrawn',
  lifecycle: 'Reopened',
  moderated: 'Voided by staff',
} as const;

function StatusBadge({ review }: { review: ModerationReview }) {
  return (
    <Badge
      variant={review.void_kind === '' ? 'secondary' : 'outline'}
      className="whitespace-nowrap"
    >
      {STATUS_LABELS[review.void_kind]}
    </Badge>
  );
}

function scoreChips(scores: Scores, traits: ModerationTrait[]) {
  const labels = new Map(traits.map((t) => [t.key, t.label]));
  const ordered = [
    ...traits.map((t) => t.key).filter((key) => key in scores),
    ...Object.keys(scores).filter((key) => !labels.has(key)),
  ];
  return ordered.map((key) => (
    <Badge key={key} variant="outline">
      {`${labels.get(key) ?? key}: ${scores[key]}`}
    </Badge>
  ));
}

export function makeModerationColumns({
  viewerPk,
  traits,
  onVoid,
  onUnvoid,
  pendingPk,
}: MakeModerationColumnsOptions): AppColumnDef<ModerationReview>[] {
  return [
    {
      id: 'rater',
      enableSorting: false,
      header: 'Rater',
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex min-w-0 items-center gap-2">
              {r.rater && (
                <span className="hidden shrink-0 sm:inline-flex">
                  <UserAvatar
                    user={{ ...r.rater, pk: r.rater.user_pk }}
                    size="sm"
                  />
                </span>
              )}
              <span className="min-w-0 font-medium break-words">
                {r.rater ? DisplayName(r.rater) : 'Deleted account'}
              </span>
            </div>
            <div
              className="sm:hidden"
              data-testid={`leadership-stacked-status-${r.pk}`}
            >
              <StatusBadge review={r} />
            </div>
            <div
              className="flex flex-wrap gap-1 md:hidden"
              data-testid={`leadership-stacked-scores-${r.pk}`}
            >
              {scoreChips(r.scores, traits)}
            </div>
            {r.void_reason !== '' && (
              <p
                className="line-clamp-3 text-xs whitespace-normal break-words text-muted-foreground"
                title={r.void_reason}
                data-testid={`leadership-void-reason-${r.pk}`}
              >
                {r.void_reason}
              </p>
            )}
          </div>
        );
      },
    },
    {
      id: 'scores',
      enableSorting: false,
      header: 'Scores',
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {scoreChips(row.original.scores, traits)}
        </div>
      ),
      meta: {
        headClassName: 'hidden md:table-cell',
        cellClassName: 'hidden md:table-cell',
      },
    },
    {
      id: 'submitted',
      enableSorting: false,
      header: 'Submitted',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {formatOrgDate(row.original.submitted_at, undefined)}
        </span>
      ),
      meta: {
        headClassName: 'hidden w-28 sm:table-cell',
        cellClassName: 'hidden w-28 sm:table-cell',
      },
    },
    {
      id: 'status',
      enableSorting: false,
      header: 'Status',
      cell: ({ row }) => (
        <span data-testid={`leadership-status-${row.original.pk}`}>
          <StatusBadge review={row.original} />
        </span>
      ),
      meta: {
        headClassName: 'hidden sm:table-cell',
        cellClassName: 'hidden sm:table-cell',
      },
    },
    {
      id: 'actions',
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const r = row.original;
        const name = r.rater ? DisplayName(r.rater) : 'deleted account';
        if (viewerPk !== null && r.rater?.user_pk === viewerPk) {
          return (
            <span
              className="text-sm text-muted-foreground"
              data-testid={`leadership-own-review-${r.pk}`}
            >
              Your review
            </span>
          );
        }
        if (r.void_kind === 'moderated') {
          return (
            <SecondaryButton
              size="sm"
              className="min-h-11 sm:min-h-9"
              data-testid={`leadership-unvoid-${r.pk}`}
              aria-label={`Restore review by ${name}`}
              disabled={pendingPk !== null}
              onClick={(e) => {
                e.stopPropagation();
                onUnvoid(r);
              }}
            >
              Restore
            </SecondaryButton>
          );
        }
        if (r.voided_at !== null) return null;
        return (
          <DestructiveButton
            size="sm"
            className="min-h-11 sm:min-h-9"
            data-testid={`leadership-void-${r.pk}`}
            aria-label={`Void review by ${name}`}
            disabled={pendingPk !== null}
            onClick={(e) => {
              e.stopPropagation();
              onVoid(r);
            }}
          >
            Void
          </DestructiveButton>
        );
      },
      meta: { headClassName: 'w-24', cellClassName: 'w-24' },
    },
  ];
}
