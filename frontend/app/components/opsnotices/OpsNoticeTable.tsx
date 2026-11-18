import {
  createColumnHelper,
  type ColumnDef,
  type Row,
} from '@tanstack/react-table';
import { formatDistanceToNow } from 'date-fns';
import { useMemo } from 'react';
import { Link } from 'react-router';

import type { OpsNotice } from '~/components/api/opsNoticesAPI';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { DataTable, DataTableColumnHeader } from '~/components/ui/data-table';
import type { NoticeSeverity } from '~/lib/opsnotices/noticeTypes.generated';

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

export interface OpsNoticeTableProps {
  notices: OpsNotice[];
  showEvent?: boolean;
  noticeHref?: (n: OpsNotice) => string;
  onResolve?: (n: OpsNotice) => void;
  resolving?: boolean;
  emptyMessage?: string;
}

const col = createColumnHelper<OpsNotice>();

const lastSeen = (n: OpsNotice): number => new Date(n.last_seen_at).getTime();

function bySeverityThenLastSeen(a: Row<OpsNotice>, b: Row<OpsNotice>): number {
  const rank =
    SEVERITY_RANK[a.original.severity] - SEVERITY_RANK[b.original.severity];
  return rank || lastSeen(a.original) - lastSeen(b.original);
}

function buildColumns({
  showEvent,
  noticeHref,
  onResolve,
  resolving,
}: Omit<OpsNoticeTableProps, 'notices' | 'emptyMessage'>): ColumnDef<
  OpsNotice,
  any
>[] {
  const columns: ColumnDef<OpsNotice, any>[] = [
    col.accessor((n) => SEVERITY_RANK[n.severity], {
      id: 'severity',
      enableSorting: true,
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
    }),
    col.accessor('category', {
      header: 'Type',
      cell: ({ getValue }) => <Badge variant="outline">{getValue()}</Badge>,
    }),
    col.accessor('summary', {
      header: 'Notice',
      meta: { cellClassName: 'min-w-40 whitespace-normal wrap-anywhere' },
      cell: ({ row, getValue }) =>
        noticeHref ? (
          <Link to={noticeHref(row.original)} className="hover:underline">
            {getValue()}
          </Link>
        ) : (
          getValue()
        ),
    }),
  ];
  if (showEvent) {
    columns.push(
      col.accessor('event_name', {
        header: 'Event',
        meta: { cellClassName: 'text-muted-foreground' },
        cell: ({ getValue }) => getValue() || '—',
      }),
    );
  }
  columns.push(
    col.accessor('occurrences', {
      header: 'Count',
      meta: {
        headerClassName: 'text-right',
        cellClassName: 'text-right tabular-nums text-muted-foreground',
      },
      cell: ({ getValue }) => (getValue() > 1 ? `x${getValue()}` : ''),
    }),
    col.accessor(lastSeen, {
      id: 'last_seen',
      enableSorting: true,
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Last seen" />
      ),
      meta: { cellClassName: 'text-muted-foreground' },
      cell: ({ row }) =>
        formatDistanceToNow(new Date(row.original.last_seen_at), {
          addSuffix: true,
        }),
    }),
  );
  if (onResolve) {
    columns.push(
      col.display({
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        meta: { cellClassName: 'text-right' },
        cell: ({ row }) =>
          row.original.category === 'urgent' ? (
            <SecondaryButton
              size="sm"
              data-testid={`ops-notice-resolve-${row.original.id}`}
              disabled={resolving}
              onClick={() => onResolve(row.original)}
            >
              Resolve
            </SecondaryButton>
          ) : null,
      }),
    );
  }
  return columns;
}

export function OpsNoticeTable({
  notices,
  showEvent = true,
  noticeHref,
  onResolve,
  resolving = false,
  emptyMessage = 'No open notices',
}: OpsNoticeTableProps) {
  const columns = useMemo(
    () => buildColumns({ showEvent, noticeHref, onResolve, resolving }),
    [showEvent, noticeHref, onResolve, resolving],
  );
  return (
    <DataTable
      columns={columns}
      data={notices}
      getRowId={(n) => String(n.id)}
      initialSorting={[{ id: 'severity', desc: true }]}
      emptyMessage={emptyMessage}
      data-testid="ops-notice-table"
      rowTestId={(n) => `ops-notice-row-${n.id}`}
    />
  );
}
