import { useMemo, type ReactNode } from 'react';

import type { ManagedTeam } from '~/components/api/teamManagementAPI';
import { DataTable } from '~/components/ui/data-table';
import type { PendingTeamAction } from './pendingTeamAction';
import {
  buildRosterRows,
  DEFAULT_ROSTER_COLUMNS,
  makeRosterColumns,
  type RosterColumnId,
  type RosterRow,
} from './rosterColumns';

export type { RosterColumnId } from './rosterColumns';

export interface RosterTableProps {
  team: ManagedTeam;
  pending: boolean;
  onRequestAction: (request: PendingTeamAction) => void;
  onReplaceCaptain?: () => void;
  /** Test id namespace: the table is `${prefix}-table`, row menus `${prefix}-actions-<pk>`. */
  testIdPrefix?: string;
  columns?: readonly RosterColumnId[];
  /** Right side of the bar above the table, e.g. the add stand-in picker. */
  toolbarActions?: ReactNode;
}

const plural = (n: number, word: string): string =>
  `${n} ${word}${n === 1 ? '' : 's'}`;

/** Rows keep the pre-table ids (`team-member-row-<pk>` etc.) that tests target. */
const rowTestId = (r: RosterRow): string => `team-${r.status}-row-${r.user.pk}`;

/** A team's roster, one row per user: DataTable over makeRosterColumns. */
export function RosterTable({
  team,
  pending,
  onRequestAction,
  onReplaceCaptain,
  testIdPrefix = 'team-roster',
  columns = DEFAULT_ROSTER_COLUMNS,
  toolbarActions,
}: RosterTableProps) {
  const rows = useMemo(() => buildRosterRows(team), [team]);
  const cols = useMemo(
    () =>
      makeRosterColumns({
        team,
        testIdPrefix,
        onRequestAction,
        onReplaceCaptain,
        columns,
        pending,
      }),
    [team, testIdPrefix, onRequestAction, onReplaceCaptain, columns, pending],
  );
  const counts = [
    plural(team.members.length, 'member'),
    plural(team.dropin_members.length, 'stand-in'),
    plural(team.left_members.length, 'dropout'),
  ].join(' · ');
  return (
    <DataTable
      columns={cols}
      data={rows}
      getRowId={(r) => r.user.pk}
      getRowTestId={rowTestId}
      initialSorting={
        columns.includes('role') ? [{ id: 'role', desc: false }] : []
      }
      toolbarTestIdPrefix={testIdPrefix}
      toolbarStart={counts}
      toolbarActions={toolbarActions}
      density="compact"
      pageSize={100}
      emptyMessage="No players on this team."
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
