import { useMemo } from 'react';
import { DataTable } from '~/components/ui/data-table';
import {
  makeAttendanceColumns,
  type AttendanceTableRow,
  type MakeAttendanceColumnsOptions,
} from './attendanceColumns';

export type { AttendanceTableRow } from './attendanceColumns';

// DataTable reads pageSize only into initialState; a fixed size keeps rows added later on page 1.
export const ATTENDANCE_PAGE_SIZE = 1000;

export type AttendanceTableProps = Omit<
  MakeAttendanceColumnsOptions,
  'selectableKeys' | 'testIdPrefix'
> & {
  rows: AttendanceTableRow[];
  testIdPrefix?: string;
};

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
      pageSize={ATTENDANCE_PAGE_SIZE}
      emptyMessage="No expected members for this event"
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
