import { useMemo } from 'react';
import { DataTable } from '~/components/ui/data-table';
import {
  makeAttendanceColumns,
  type AttendanceColumnId,
  type AttendanceTableRow,
} from './attendanceColumns';
import type { Outcome, StaffSettableOutcome } from './schemas';

export type { AttendanceTableRow } from './attendanceColumns';

export interface AttendanceTableProps {
  rows: AttendanceTableRow[];
  editable: boolean;
  selected: ReadonlySet<string>;
  onToggle: (rowKey: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
  outcomeFor: (row: AttendanceTableRow) => Outcome;
  onOutcomeChange: (rowKey: string, outcome: StaffSettableOutcome) => void;
  onRemoveWalkIn: (userPk: number) => void;
  columns?: readonly AttendanceColumnId[];
  testIdPrefix?: string;
}

export function AttendanceTable({
  rows,
  editable,
  selected,
  onToggle,
  onToggleAll,
  outcomeFor,
  onOutcomeChange,
  onRemoveWalkIn,
  columns,
  testIdPrefix = 'attendance',
}: AttendanceTableProps) {
  const selectableKeys = useMemo(
    () => rows.flatMap((r) => (r.provisional ? [] : [r.key])),
    [rows],
  );
  const cols = useMemo(
    () =>
      makeAttendanceColumns({
        testIdPrefix,
        editable,
        selected,
        selectableKeys,
        onToggle,
        onToggleAll,
        outcomeFor,
        onOutcomeChange,
        onRemoveWalkIn,
        columns,
      }),
    [
      testIdPrefix,
      editable,
      selected,
      selectableKeys,
      onToggle,
      onToggleAll,
      outcomeFor,
      onOutcomeChange,
      onRemoveWalkIn,
      columns,
    ],
  );
  return (
    <DataTable
      columns={cols}
      data={rows}
      getRowId={(r) => r.key}
      getRowTestId={(r) => `${testIdPrefix}-row-${r.key}`}
      initialSorting={[{ id: 'member', desc: false }]}
      toolbarTestIdPrefix={testIdPrefix}
      pageSize={Math.max(rows.length, 25)}
      emptyMessage="No expected members for this event"
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
