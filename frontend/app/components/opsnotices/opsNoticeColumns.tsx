import type { Row } from '@tanstack/react-table';
import { formatDistanceToNow } from 'date-fns';
import { Link } from 'react-router';

import type { OpsNotice } from '~/components/api/opsNoticesAPI';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  DataTableColumnHeader,
  type AppColumnDef,
} from '~/components/ui/data-table';
import type { NoticeSeverity } from '~/lib/opsnotices/noticeTypes.generated';

export type OpsNoticeColumnId =
  | 'severity'
  | 'category'
  | 'summary'
  | 'event'
  | 'occurrences'
  | 'last_seen'
  | 'actions';

export const DEFAULT_OPS_NOTICE_COLUMNS: readonly OpsNoticeColumnId[] = [
  'severity',
  'category',
  'summary',
  'event',
  'occurrences',
  'last_seen',
  'actions',
];

const SEVERITY_VARIANT: Record<
  NoticeSeverity,
  'destructive' | 'secondary' | 'outline'
> = {
  critical: 'destructive',
  warning: 'secondary',
  info: 'outline',
};

const SEVERITY_RANK: Record<NoticeSeverity, number> = {
  info: 0,
  warning: 1,
  critical: 2,
};

const lastSeen = (n: OpsNotice): number => new Date(n.last_seen_at).getTime();
const age = (n: OpsNotice): string =>
  formatDistanceToNow(new Date(n.last_seen_at), { addSuffix: true });

function bySeverityThenLastSeen(a: Row<OpsNotice>, b: Row<OpsNotice>): number {
  const rank =
    SEVERITY_RANK[a.original.severity] - SEVERITY_RANK[b.original.severity];
  return rank || lastSeen(a.original) - lastSeen(b.original);
}

export interface MakeOpsNoticeColumnsOptions {
  testIdPrefix: string;
  columns?: readonly OpsNoticeColumnId[];
  sortable?: boolean;
  noticeHref?: (n: OpsNotice) => string;
  onResolve?: (n: OpsNotice) => void;
  resolving?: boolean;
}

/**
 * Column defs for OpsNoticeTable. Phones show severity, the notice (with its type and
 * age stacked under it) and Resolve; the other columns appear from `sm`/`md`.
 */
export function makeOpsNoticeColumns({
  testIdPrefix,
  columns = DEFAULT_OPS_NOTICE_COLUMNS,
  sortable = true,
  noticeHref,
  onResolve,
  resolving = false,
}: MakeOpsNoticeColumnsOptions): AppColumnDef<OpsNotice>[] {
  const all: Record<OpsNoticeColumnId, AppColumnDef<OpsNotice> | null> = {
    severity: {
      id: 'severity',
      accessorFn: (n) => SEVERITY_RANK[n.severity],
      enableSorting: sortable,
      sortDescFirst: true,
      sortingFn: bySeverityThenLastSeen,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Severity" />
      ),
      cell: ({ row }) => (
        <Badge variant={SEVERITY_VARIANT[row.original.severity]}>
          {row.original.severity}
        </Badge>
      ),
      meta: { headClassName: 'w-24 sm:w-28', cellClassName: 'w-24 sm:w-28' },
    },
    category: {
      id: 'category',
      accessorKey: 'category',
      enableSorting: false,
      header: 'Type',
      cell: ({ row }) => (
        <Badge variant="outline">{row.original.category}</Badge>
      ),
      meta: {
        headClassName: 'hidden w-24 sm:table-cell',
        cellClassName: 'hidden w-24 sm:table-cell',
      },
    },
    summary: {
      id: 'summary',
      accessorKey: 'summary',
      enableSorting: false,
      header: 'Notice',
      cell: ({ row }) => {
        const n = row.original;
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            {noticeHref ? (
              <Link
                to={noticeHref(n)}
                className="wrap-anywhere hover:underline"
              >
                {n.summary}
              </Link>
            ) : (
              <span className="wrap-anywhere">{n.summary}</span>
            )}
            <span className="text-xs text-muted-foreground md:hidden">
              <span className="sm:hidden">{n.category} · </span>
              {age(n)}
            </span>
          </div>
        );
      },
    },
    event: {
      id: 'event',
      accessorKey: 'event_name',
      enableSorting: false,
      header: 'Event',
      cell: ({ row }) => row.original.event_name || '—',
      meta: {
        headClassName: 'hidden w-48 lg:table-cell',
        cellClassName: 'hidden w-48 text-muted-foreground lg:table-cell',
      },
    },
    occurrences: {
      id: 'occurrences',
      accessorKey: 'occurrences',
      enableSorting: false,
      header: 'Count',
      cell: ({ row }) =>
        row.original.occurrences > 1 ? `x${row.original.occurrences}` : '',
      meta: {
        headClassName: 'hidden w-20 text-right sm:table-cell',
        cellClassName:
          'hidden w-20 text-right tabular-nums text-muted-foreground sm:table-cell',
      },
    },
    last_seen: {
      id: 'last_seen',
      accessorFn: lastSeen,
      enableSorting: sortable,
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Last seen" />
      ),
      cell: ({ row }) => age(row.original),
      meta: {
        headClassName: 'hidden w-36 md:table-cell',
        cellClassName: 'hidden w-36 text-muted-foreground md:table-cell',
      },
    },
    actions: onResolve
      ? {
          id: 'actions',
          enableSorting: false,
          header: () => <span className="sr-only">Actions</span>,
          cell: ({ row }) =>
            row.original.category === 'urgent' ? (
              <SecondaryButton
                size="sm"
                className="min-h-11 sm:min-h-8"
                data-testid={`${testIdPrefix}-resolve-${row.original.id}`}
                disabled={resolving}
                onClick={(e) => {
                  e.stopPropagation();
                  onResolve(row.original);
                }}
              >
                Resolve
              </SecondaryButton>
            ) : null,
          meta: {
            headClassName: 'w-24 sm:w-28',
            cellClassName: 'w-24 text-right sm:w-28',
          },
        }
      : null,
  };
  return columns
    .map((id) => all[id])
    .filter((c): c is AppColumnDef<OpsNotice> => c !== null);
}
