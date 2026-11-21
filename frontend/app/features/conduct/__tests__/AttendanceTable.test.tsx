// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { toAttendanceTableRow, walkInTableRow } from '../attendanceColumns';
import { AttendanceTable, type AttendanceTableProps } from '../AttendanceTable';
import type { AttendanceRow } from '../schemas';
import { attendanceRow } from './fixtures';

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
});

afterEach(cleanup);

function member(n: number, username = `user${String(n).padStart(2, '0')}`) {
  return {
    org_user_pk: n,
    user_pk: n + 100,
    username,
    nickname: null,
    discordNickname: null,
    guildNickname: null,
    avatarUrl: null,
  };
}

function savedRow(n: number, overrides: Partial<AttendanceRow> = {}) {
  return attendanceRow({
    member: member(n),
    org_user_pk: n,
    outcome: 'attended',
    source: 'ready_check',
    virtual: false,
    ...overrides,
  });
}

function rowsOf(count: number) {
  return Array.from({ length: count }, (_, i) =>
    toAttendanceTableRow(savedRow(i + 1)),
  );
}

function props(
  overrides: Partial<AttendanceTableProps> = {},
): AttendanceTableProps {
  return {
    rows: rowsOf(2),
    editable: true,
    selected: new Set<string>(),
    onToggle: vi.fn(),
    onToggleAll: vi.fn(),
    outcomeFor: (r) => r.outcome,
    onOutcomeChange: vi.fn(),
    onRemoveWalkIn: vi.fn(),
    ...overrides,
  };
}

const WALK_IN = {
  user_pk: 900,
  username: 'walker',
  nickname: null,
  avatarUrl: null,
};

describe('AttendanceTable', () => {
  it('renders every row when there are more than 25', () => {
    render(<AttendanceTable {...props({ rows: rowsOf(30) })} />);
    expect(screen.getAllByTestId(/^attendance-row-/)).toHaveLength(30);
    expect(screen.queryByTestId('data-table-next')).toBeNull();
  });

  it('a row added after mount stays on the page', () => {
    const initial = rowsOf(25);
    const { rerender } = render(
      <AttendanceTable {...props({ rows: initial })} />,
    );
    rerender(
      <AttendanceTable
        {...props({ rows: [...initial, walkInTableRow(WALK_IN)] })}
      />,
    );
    expect(screen.getByTestId('attendance-row-walkin-900')).toBeInTheDocument();
    expect(screen.getAllByTestId(/^attendance-row-/)).toHaveLength(26);
    expect(screen.queryByTestId('data-table-next')).toBeNull();
  });

  it('a virtual unflagged row reads Attended (default)', () => {
    const row = toAttendanceTableRow(attendanceRow());
    render(<AttendanceTable {...props({ rows: [row] })} />);
    expect(screen.getByTestId('attendance-outcome-7')).toHaveTextContent(
      'Attended (default)',
    );
  });

  it('a virtual unflagged row reads Attended (default) when read-only', () => {
    const row = toAttendanceTableRow(attendanceRow());
    render(<AttendanceTable {...props({ rows: [row], editable: false })} />);
    expect(screen.getByTestId('attendance-outcome-7')).toHaveTextContent(
      'Attended (default)',
    );
  });

  it('a flagged virtual row reads Pending and the flag text', () => {
    const row = toAttendanceTableRow(
      attendanceRow({ flag: 'roll_call_unconfirmed' }),
    );
    render(<AttendanceTable {...props({ rows: [row] })} />);
    const outcome = screen.getByTestId('attendance-outcome-7');
    expect(outcome).toHaveTextContent('Pending');
    expect(outcome).not.toHaveTextContent('Attended (default)');
    expect(screen.getByTestId('attendance-flag-7')).toHaveTextContent(
      'Did not confirm at roll call',
    );
  });

  it('the select-all checkbox selects only saved rows and shows indeterminate', () => {
    const onToggleAll = vi.fn();
    const rows = [...rowsOf(2), walkInTableRow(WALK_IN)];
    const { rerender } = render(
      <AttendanceTable {...props({ rows, onToggleAll })} />,
    );
    const all = screen.getByTestId('attendance-select-all') as HTMLInputElement;
    expect(all).toHaveAccessibleName('Select all members');
    expect(all.indeterminate).toBe(false);
    fireEvent.click(all);
    expect(onToggleAll).toHaveBeenCalledWith(true);

    rerender(
      <AttendanceTable
        {...props({ rows, onToggleAll, selected: new Set(['1']) })}
      />,
    );
    const partial = screen.getByTestId(
      'attendance-select-all',
    ) as HTMLInputElement;
    expect(partial.indeterminate).toBe(true);
    expect(partial.checked).toBe(false);

    rerender(
      <AttendanceTable
        {...props({ rows, onToggleAll, selected: new Set(['1', '2']) })}
      />,
    );
    const full = screen.getByTestId(
      'attendance-select-all',
    ) as HTMLInputElement;
    expect(full.checked).toBe(true);
    expect(full.indeterminate).toBe(false);
  });

  it('toggles a single row by key', () => {
    const onToggle = vi.fn();
    render(<AttendanceTable {...props({ onToggle })} />);
    const box = screen.getByTestId('attendance-select-2');
    expect(box).toHaveAccessibleName('Select user02');
    fireEvent.click(box);
    expect(onToggle).toHaveBeenCalledWith('2', true);
  });

  it('choosing an outcome calls onOutcomeChange with the row key', () => {
    const onOutcomeChange = vi.fn();
    render(<AttendanceTable {...props({ onOutcomeChange })} />);
    const trigger = screen.getByTestId('attendance-outcome-2');
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(screen.getByTestId('attendance-outcome-option-no_show'));
    expect(onOutcomeChange).toHaveBeenCalledWith('2', 'no_show');
  });

  it('read-only hides checkboxes and selects and renders chips', () => {
    render(<AttendanceTable {...props({ editable: false })} />);
    expect(screen.queryByTestId('attendance-select-all')).toBeNull();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.getAllByTestId('conduct-outcome-attended')).toHaveLength(2);
  });

  it('a provisional walk-in has a remove button and no checkbox', () => {
    const onRemoveWalkIn = vi.fn();
    render(
      <AttendanceTable
        {...props({ rows: [walkInTableRow(WALK_IN)], onRemoveWalkIn })}
      />,
    );
    const row = screen.getByTestId('attendance-row-walkin-900');
    expect(within(row).queryByRole('checkbox')).toBeNull();
    expect(within(row).queryByRole('combobox')).toBeNull();
    expect(
      within(row).getByTestId('conduct-outcome-attended'),
    ).toBeInTheDocument();
    expect(within(row).getByText('—')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('attendance-walkin-remove-900'));
    expect(onRemoveWalkIn).toHaveBeenCalledWith(900);
  });

  it('a saved walk-in row shows the Walk-in badge', () => {
    const row = toAttendanceTableRow(
      savedRow(3, { source: 'staff', committed: false }),
    );
    render(<AttendanceTable {...props({ rows: [row] })} />);
    expect(screen.getByTestId('attendance-source-3')).toHaveTextContent(
      'Walk-in',
    );
  });

  it('a member without an OrgUser is keyed by user pk', () => {
    const row = toAttendanceTableRow(
      attendanceRow({
        org_user_pk: null,
        member: { ...member(4), org_user_pk: null },
      }),
    );
    render(<AttendanceTable {...props({ rows: [row] })} />);
    expect(screen.getByTestId('attendance-row-user-104')).toBeInTheDocument();
    expect(
      screen.getByTestId('attendance-select-user-104'),
    ).toBeInTheDocument();
  });

  it('the source, flag and rate columns are hidden below sm and stacked under the member', () => {
    const row = toAttendanceTableRow(
      savedRow(5, {
        source: 'staff',
        flag: 'dropped_unattributed',
        show_rate: 0.87,
      }),
    );
    render(<AttendanceTable {...props({ rows: [row] })} />);
    const tr = screen.getByTestId('attendance-row-5');
    const cells = Array.from(tr.querySelectorAll('td'));
    const hidden = cells.filter((td) => td.className.includes('hidden'));
    expect(hidden).toHaveLength(3);
    const stacked = within(tr).getByTestId('attendance-stacked-5');
    expect(stacked.className).toContain('sm:hidden');
    expect(stacked).toHaveTextContent('Staff');
    expect(stacked).toHaveTextContent('87%');
    const stackedFlag = within(tr).getByTestId('attendance-stacked-flag-5');
    expect(stackedFlag.className).toContain('md:hidden');
    expect(stackedFlag).toHaveTextContent('Dropped, needs review');
  });

  it('shows the empty message with no rows', () => {
    render(<AttendanceTable {...props({ rows: [] })} />);
    expect(
      screen.getByText('No expected members for this event'),
    ).toBeInTheDocument();
  });
});
