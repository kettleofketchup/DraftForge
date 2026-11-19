// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { toAttendanceTableRow } from '../attendanceColumns';
import { AttendanceTable, type AttendanceTableProps } from '../AttendanceTable';
import type { AttendanceRow } from '../schemas';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

function row(
  orgUserPk: number,
  username: string,
  showRate: number,
): AttendanceRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: orgUserPk + 100,
      username,
      nickname: null,
      avatarUrl: null,
    },
    org_user_pk: orgUserPk,
    signup_status: 'approved',
    outcome: 'attended',
    source: 'default',
    committed: true,
    virtual: false,
    finalized: false,
    voided: false,
    flag: null,
    set_by: null,
    reason: '',
    show_rate: showRate,
    status: 'scored',
  };
}

const rows = [
  row(12, 'bob', 0.6),
  row(11, 'alice', 0.9),
  row(13, 'carol', 0.75),
];

function props(
  overrides: Partial<AttendanceTableProps> = {},
): AttendanceTableProps {
  return {
    rows: rows.map(toAttendanceTableRow),
    editable: true,
    selected: new Set<number>(),
    onToggle: vi.fn(),
    onToggleAll: vi.fn(),
    outcomeFor: (r) => r.outcome,
    onOutcomeChange: vi.fn(),
    onRemoveWalkIn: vi.fn(),
    ...overrides,
  };
}

function rowIds(): string[] {
  return screen
    .getAllByTestId(/^attendance-row-\d+$/)
    .map((r) => r.getAttribute('data-testid') ?? '');
}

afterEach(cleanup);

describe('AttendanceTable', () => {
  it('orders rows by member name by default', () => {
    render(<AttendanceTable {...props()} />);
    expect(rowIds()).toEqual([
      'attendance-row-11',
      'attendance-row-12',
      'attendance-row-13',
    ]);
    expect(screen.getByTestId('attendance-outcome-11')).toHaveTextContent(
      'Attended',
    );
  });

  it('re-sorts by show rate when that header is clicked', () => {
    render(<AttendanceTable {...props()} />);
    fireEvent.click(screen.getByTestId('data-table-sort-rate'));
    expect(rowIds()).toEqual([
      'attendance-row-11',
      'attendance-row-13',
      'attendance-row-12',
    ]);
  });

  it('shows the empty message with no rows', () => {
    render(<AttendanceTable {...props({ rows: [] })} />);
    expect(
      screen.getByText('No expected members for this event'),
    ).toBeInTheDocument();
  });

  it('toggles a row and the whole set from the checkboxes', () => {
    const onToggle = vi.fn();
    const onToggleAll = vi.fn();
    render(<AttendanceTable {...props({ onToggle, onToggleAll })} />);
    fireEvent.click(screen.getByTestId('attendance-select-12'));
    expect(onToggle).toHaveBeenCalledWith(12, true);
    fireEvent.click(screen.getByTestId('attendance-select-all'));
    expect(onToggleAll).toHaveBeenCalledWith(true);
  });

  it('renders outcome chips and no controls when not editable', () => {
    render(<AttendanceTable {...props({ editable: false })} />);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.queryByTestId('attendance-select-all')).toBeNull();
    expect(screen.getAllByTestId('conduct-outcome-attended')).toHaveLength(3);
  });
});
