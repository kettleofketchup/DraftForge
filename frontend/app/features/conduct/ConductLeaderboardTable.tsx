import { useMemo, type HTMLAttributes } from 'react';
import { DataTable } from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { HiddenRowsNote } from '~/features/contributions/Leaderboard';
import { cn } from '~/lib/utils';
import {
  makeConductLeaderboardColumns,
  type ConductLeaderboardColumnId,
  type ConductTableRow,
} from './conductLeaderboardColumns';
import type { ConductLeaderboard as ConductLeaderboardData } from './schemas';

export type { ConductTableRow } from './conductLeaderboardColumns';

export interface ConductLeaderboardTableProps {
  rows: ConductTableRow[];
  ownPk: number | null;
  selectedPk: number | null;
  /** Staff can open any member; everyone else only their own row. */
  canSelect: boolean;
  onSelect: (orgUserPk: number) => void;
  columns?: readonly ConductLeaderboardColumnId[];
  testIdPrefix?: string;
}

export function ConductLeaderboardTable({
  rows,
  ownPk,
  selectedPk,
  canSelect,
  onSelect,
  columns,
  testIdPrefix = 'conduct',
}: ConductLeaderboardTableProps) {
  const cols = useMemo(
    () => makeConductLeaderboardColumns({ testIdPrefix, ownPk, columns }),
    [testIdPrefix, ownPk, columns],
  );
  const rowProps = (
    r: ConductTableRow,
  ): HTMLAttributes<HTMLTableRowElement> => {
    const pk = r.member.org_user_pk;
    const own = pk === ownPk;
    const selectable = canSelect || own;
    return {
      className: cn(
        own && 'bg-primary/10 ring-1 ring-inset ring-primary/40',
        pk === selectedPk && 'bg-base-300/60',
        selectable && 'cursor-pointer hover:bg-base-300/60',
      ),
      'aria-selected': pk === selectedPk ? true : undefined,
      'aria-current': own ? true : undefined,
      ...(selectable
        ? {
            role: 'button',
            tabIndex: 0,
            'aria-label': `View ${DisplayName(r.member)}'s attendance`,
            onClick: () => onSelect(pk),
            onKeyDown: (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(pk);
              }
            },
          }
        : {}),
    };
  };
  return (
    <DataTable
      columns={cols}
      data={rows}
      getRowId={(r) => r.member.org_user_pk}
      getRowTestId={(r) => `${testIdPrefix}-row-${r.member.org_user_pk}`}
      getRowProps={rowProps}
      initialSorting={[{ id: 'rank', desc: false }]}
      toolbarTestIdPrefix={testIdPrefix}
      emptyMessage="No members have enough attendance history yet"
      data-testid={`${testIdPrefix}-table`}
    />
  );
}

export interface ConductLeaderboardProps {
  data: ConductLeaderboardData;
  viewerPk: number | null;
  membersPrivate: boolean;
  selectedPk: number | null;
  canSelect: boolean;
  onSelect: (orgUserPk: number) => void;
}

export function ConductLeaderboard({
  data,
  viewerPk,
  membersPrivate,
  selectedPk,
  canSelect,
  onSelect,
}: ConductLeaderboardProps) {
  const ownPk = data.own_row?.member.org_user_pk ?? null;
  const rows = useMemo<ConductTableRow[]>(() => {
    if (data.rows_visible) {
      return data.rows.map((r) => ({ ...r, status: 'scored' as const }));
    }
    return data.own_row ? [data.own_row] : [];
  }, [data]);

  return (
    <section className="flex flex-col gap-4" data-testid="conduct-leaderboard">
      {!data.rows_visible && (
        <HiddenRowsNote
          membersPrivate={membersPrivate}
          signedIn={viewerPk != null}
          hasOwnRow={data.own_row != null}
          testIdPrefix="conduct"
        />
      )}
      {(data.rows_visible || rows.length > 0) && (
        <ConductLeaderboardTable
          rows={rows}
          ownPk={ownPk}
          selectedPk={selectedPk}
          canSelect={canSelect}
          onSelect={onSelect}
        />
      )}
      {data.rows_visible && data.new_members.length > 0 && (
        <div className="flex flex-col gap-2" data-testid="conduct-new-members">
          <h3 className="text-sm font-semibold text-muted-foreground">
            New members
          </h3>
          <ul className="flex flex-col divide-y divide-border">
            {data.new_members.map((m) => (
              <li
                key={m.member.org_user_pk}
                className="flex items-center justify-between gap-3 py-2"
                data-testid={`conduct-new-member-${m.member.org_user_pk}`}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <UserAvatar
                    user={{ ...m.member, pk: m.member.user_pk }}
                    size="sm"
                  />
                  <span className="wrap-anywhere font-medium">
                    {DisplayName(m.member)}
                  </span>
                </div>
                <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                  {m.counted_events}{' '}
                  {m.counted_events === 1 ? 'event' : 'events'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
