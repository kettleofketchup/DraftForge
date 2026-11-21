import { Badge } from '~/components/ui/badge';
import type { AppColumnDef } from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { formatMetricValue } from './format';
import type { Metric, StandingLeaderboard, StandingRow } from './schemas';

export type StandingTableRow = StandingRow & {
  rank: number | null;
  own: boolean;
};

export function toStandingTableRows(
  board: StandingLeaderboard,
  viewerPk: number | null,
): StandingTableRow[] {
  const source = board.rows_visible
    ? board.rows
    : board.own_row
      ? [board.own_row]
      : [];
  const ownPk = board.own_row?.member.org_user_pk ?? null;
  let rank = 0;
  let previous: StandingRow | null = null;
  return source.map((row) => {
    const own =
      row.member.org_user_pk === ownPk ||
      (viewerPk != null && row.member.user_pk === viewerPk);
    if (!board.rows_visible || row.status !== 'ranked') {
      return { ...row, rank: null, own };
    }
    if (
      previous === null ||
      previous.value !== row.value ||
      previous.sample !== row.sample
    ) {
      rank += 1;
    }
    previous = row;
    return { ...row, rank, own };
  });
}

export interface MakeStandingLeaderboardColumnsOptions {
  testIdPrefix: string;
  metric: Metric;
  sampleLabel: string | null;
  showRank: boolean;
}

export function makeStandingLeaderboardColumns({
  testIdPrefix,
  metric,
  sampleLabel,
  showRank,
}: MakeStandingLeaderboardColumnsOptions): AppColumnDef<StandingTableRow>[] {
  const columns: AppColumnDef<StandingTableRow>[] = [];
  if (showRank) {
    columns.push({
      id: 'rank',
      header: '#',
      enableSorting: false,
      accessorFn: (r) => r.rank,
      cell: ({ row }) => row.original.rank ?? '—',
      meta: {
        headClassName: 'w-12',
        cellClassName: 'w-12 font-medium text-muted-foreground tabular-nums',
      },
    });
  }
  columns.push(
    {
      id: 'member',
      header: 'Member',
      enableSorting: false,
      accessorFn: (r) => DisplayName(r.member),
      cell: ({ row }) => {
        const { member, own } = row.original;
        return (
          <div className="flex items-center gap-2">
            <UserAvatar user={{ ...member, pk: member.user_pk }} size="sm" />
            <span className="font-medium">{DisplayName(member)}</span>
            {own && <span className="text-xs text-primary">(you)</span>}
          </div>
        );
      },
    },
    {
      id: 'value',
      header: metric.label,
      enableSorting: false,
      accessorFn: (r) => r.value,
      cell: ({ row }) => (
        <span
          data-testid={`${testIdPrefix}-row-${row.original.member.org_user_pk}-value`}
        >
          {row.original.status === 'new' || row.original.value === null ? (
            <Badge variant="outline">New</Badge>
          ) : (
            formatMetricValue(row.original, metric.format)
          )}
        </span>
      ),
      meta: {
        headClassName: 'w-24 text-right',
        cellClassName: 'w-24 text-right font-semibold tabular-nums',
      },
    },
  );
  if (sampleLabel !== null) {
    columns.push({
      id: 'sample',
      header: sampleLabel,
      enableSorting: false,
      accessorFn: (r) => r.sample,
      cell: ({ row }) => row.original.sample.toLocaleString('en-US'),
      meta: {
        headClassName: 'hidden w-20 text-right sm:table-cell',
        cellClassName:
          'hidden w-20 text-right tabular-nums text-muted-foreground sm:table-cell',
      },
    });
  }
  return columns;
}
