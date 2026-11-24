import { useMemo } from 'react';

import {
  DataTable,
  DataTableColumnHeader,
  type AppColumnDef,
} from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import type { ApiUsageUser } from './schemas';

export function todayRequests(row: ApiUsageUser, today: string): number {
  return row.days.find((d) => d.date === today)?.requests ?? 0;
}

/** The server's "today": the last day of the window that starts at `since`. */
export function usageToday(since: string, days: number): string {
  const date = new Date(`${since}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days - 1);
  return date.toISOString().slice(0, 10);
}

const NUMERIC = 'w-24 text-right tabular-nums';

function makeUsageColumns(
  testIdPrefix: string,
  today: string,
): AppColumnDef<ApiUsageUser>[] {
  return [
    {
      id: 'user',
      accessorFn: (r) => DisplayName(r.user),
      enableSorting: false,
      header: 'User',
      cell: ({ row }) => (
        <span className="flex min-w-0 items-center gap-2">
          <UserAvatar user={row.original.user} size="xs" />
          <span className="truncate">{DisplayName(row.original.user)}</span>
        </span>
      ),
    },
    {
      id: 'requests',
      accessorKey: 'requests',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Requests" />
      ),
      cell: ({ row }) => (
        <span data-testid={`${testIdPrefix}-requests-${row.original.user.pk}`}>
          {row.original.requests.toLocaleString()}
        </span>
      ),
      meta: { headClassName: NUMERIC, cellClassName: NUMERIC },
    },
    {
      id: 'throttled',
      accessorKey: 'throttled',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Throttled" />
      ),
      cell: ({ row }) => row.original.throttled.toLocaleString(),
      meta: {
        headClassName: `hidden sm:table-cell ${NUMERIC}`,
        cellClassName: `hidden sm:table-cell ${NUMERIC}`,
      },
    },
    {
      id: 'today',
      accessorFn: (r) => todayRequests(r, today),
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Today" />
      ),
      cell: ({ row }) => todayRequests(row.original, today).toLocaleString(),
      meta: { headClassName: NUMERIC, cellClassName: NUMERIC },
    },
  ];
}

export interface ApiUsageTableProps {
  users: ApiUsageUser[];
  /** ISO date (YYYY-MM-DD) whose requests fill the Today column. */
  today: string;
  testIdPrefix?: string;
}

export function ApiUsageTable({
  users,
  today,
  testIdPrefix = 'api-usage',
}: ApiUsageTableProps) {
  const cols = useMemo(
    () => makeUsageColumns(testIdPrefix, today),
    [testIdPrefix, today],
  );
  return (
    <DataTable
      columns={cols}
      data={users}
      getRowId={(r) => r.user.pk}
      getRowTestId={(r) => `${testIdPrefix}-row-${r.user.pk}`}
      initialSorting={[{ id: 'requests', desc: true }]}
      emptyMessage="No API requests in this period"
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
