import {
  DataTableColumnHeader,
  type AppColumnDef,
  type AppRow,
} from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import type { MemberSummary } from '~/features/contributions/schemas';
import type { ScoreStatus } from './schemas';
import { scoreLabel } from './scoring';

export interface ConductTableRow {
  member: MemberSummary;
  show_rate: number;
  counted_events: number;
  rank: number | null;
  status: ScoreStatus;
}

export type ConductLeaderboardColumnId = 'rank' | 'member' | 'rate' | 'events';

export const DEFAULT_CONDUCT_LEADERBOARD_COLUMNS: readonly ConductLeaderboardColumnId[] =
  ['rank', 'member', 'rate', 'events'];

function byRankNullsLast(
  a: AppRow<ConductTableRow>,
  b: AppRow<ConductTableRow>,
): number {
  const ra = a.original.rank ?? Number.POSITIVE_INFINITY;
  const rb = b.original.rank ?? Number.POSITIVE_INFINITY;
  return ra === rb ? 0 : ra < rb ? -1 : 1;
}

export interface MakeConductLeaderboardColumnsOptions {
  testIdPrefix: string;
  ownPk: number | null;
  columns?: readonly ConductLeaderboardColumnId[];
}

export function makeConductLeaderboardColumns({
  testIdPrefix,
  ownPk,
  columns = DEFAULT_CONDUCT_LEADERBOARD_COLUMNS,
}: MakeConductLeaderboardColumnsOptions): AppColumnDef<ConductTableRow>[] {
  const all: Record<
    ConductLeaderboardColumnId,
    AppColumnDef<ConductTableRow>
  > = {
    rank: {
      id: 'rank',
      accessorFn: (r) => r.rank,
      sortFn: byRankNullsLast,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="#" />
      ),
      cell: ({ row }) => row.original.rank ?? '—',
      meta: {
        headClassName: 'w-16',
        cellClassName: 'w-16 font-medium tabular-nums text-muted-foreground',
      },
    },
    member: {
      id: 'member',
      accessorFn: (r) => DisplayName(r.member),
      enableSorting: false,
      header: 'Member',
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex min-w-0 items-center gap-2">
            <UserAvatar
              user={{ ...r.member, pk: r.member.user_pk }}
              size="sm"
            />
            <div className="flex min-w-0 flex-col">
              <span className="wrap-anywhere font-medium">
                {DisplayName(r.member)}
                {r.member.org_user_pk === ownPk && (
                  <span className="ml-1.5 text-xs text-primary">(you)</span>
                )}
              </span>
              <span className="text-xs text-muted-foreground sm:hidden">
                {r.counted_events} {r.counted_events === 1 ? 'event' : 'events'}
              </span>
            </div>
          </div>
        );
      },
    },
    rate: {
      id: 'rate',
      accessorFn: (r) => r.show_rate,
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Show rate" />
      ),
      cell: ({ row }) => (
        <span
          data-testid={`${testIdPrefix}-row-${row.original.member.org_user_pk}-rate`}
        >
          {scoreLabel(row.original)}
        </span>
      ),
      meta: {
        headClassName: 'w-28 text-right',
        cellClassName: 'w-28 text-right font-semibold tabular-nums',
      },
    },
    events: {
      id: 'events',
      accessorFn: (r) => r.counted_events,
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Events" />
      ),
      cell: ({ row }) => row.original.counted_events,
      meta: {
        headClassName: 'hidden w-24 text-right sm:table-cell',
        cellClassName:
          'hidden w-24 text-right tabular-nums text-muted-foreground sm:table-cell',
      },
    },
  };
  return columns.map((id) => all[id]);
}
