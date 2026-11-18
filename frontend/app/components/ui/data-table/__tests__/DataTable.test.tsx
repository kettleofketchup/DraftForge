// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DataTable,
  DataTableColumnHeader,
  isCellRendered,
  type AppColumnDef,
  type DataTableProps,
} from '..';

interface Row {
  id: number;
  name: string;
  score: number;
}

const rows: Row[] = [
  { id: 1, name: 'Bravo', score: 20 },
  { id: 2, name: 'Alpha', score: 30 },
  { id: 3, name: 'Charlie', score: 10 },
];

const columns: AppColumnDef<Row>[] = [
  {
    accessorKey: 'name',
    header: 'Name',
    meta: { cellClassName: 'font-medium' },
  },
  {
    accessorKey: 'score',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Score" />
    ),
    meta: {
      headClassName: 'hidden md:table-cell',
      cellClassName: 'hidden md:table-cell tabular-nums',
      headTestId: 'score-head',
    },
  },
];

function names(): string[] {
  return screen
    .getAllByTestId(/^row-/)
    .map((r) => within(r).getAllByRole('cell')[0].textContent ?? '');
}

function renderTable(props: Partial<DataTableProps<Row>> = {}) {
  return render(
    <DataTable
      columns={columns}
      data={rows}
      getRowId={(r) => r.id}
      getRowTestId={(r) => `row-${r.id}`}
      {...props}
    />,
  );
}

afterEach(cleanup);

describe('isCellRendered', () => {
  const none = { sm: false, md: false, lg: false };
  it('renders columns without a hide class', () => {
    expect(isCellRendered('w-24', none)).toBe(true);
    expect(isCellRendered(undefined, none)).toBe(true);
  });
  it('follows the breakpoint that reveals a hidden column', () => {
    expect(isCellRendered('hidden md:table-cell', none)).toBe(false);
    expect(isCellRendered('hidden md:table-cell', { ...none, md: true })).toBe(
      true,
    );
    expect(isCellRendered('hidden', { sm: true, md: true, lg: true })).toBe(
      false,
    );
  });
  it('does not mistake md:hidden for a hidden column', () => {
    expect(isCellRendered('md:hidden', none)).toBe(true);
  });
});

describe('DataTable', () => {
  it('renders rows in data order with row test ids and meta classes', () => {
    renderTable();
    expect(names()).toEqual(['Bravo', 'Alpha', 'Charlie']);
    const cells = within(screen.getByTestId('row-1')).getAllByRole('cell');
    expect(cells[0]).toHaveClass('font-medium', 'whitespace-normal');
    expect(cells[1]).toHaveClass('tabular-nums');
    expect(screen.getByTestId('score-head')).toHaveClass('hidden');
  });

  it('applies initial sorting', () => {
    renderTable({ initialSorting: [{ id: 'score', desc: true }] });
    expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie']);
  });

  it('cycles a numeric header descending, ascending, unsorted', () => {
    renderTable();
    const sort = screen.getByTestId('data-table-sort-score');
    const head = screen.getByTestId('score-head');
    expect(sort).toHaveAccessibleName('Sort by Score, descending');
    fireEvent.click(sort);
    expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie']);
    expect(head).toHaveAttribute('aria-sort', 'descending');
    fireEvent.click(sort);
    expect(names()).toEqual(['Charlie', 'Bravo', 'Alpha']);
    expect(head).toHaveAttribute('aria-sort', 'ascending');
    expect(sort).toHaveAccessibleName('Sort by Score, clear sort');
    fireEvent.click(sort);
    expect(names()).toEqual(['Bravo', 'Alpha', 'Charlie']);
    expect(head).not.toHaveAttribute('aria-sort');
  });

  it('renders a plain-string header without a sort button', () => {
    renderTable();
    expect(screen.queryByTestId('data-table-sort-name')).toBeNull();
  });

  it('paginates and hides pagination when everything fits', () => {
    renderTable({ pageSize: 2 });
    expect(names()).toEqual(['Bravo', 'Alpha']);
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('data-table-next'));
    expect(names()).toEqual(['Charlie']);
    cleanup();
    renderTable();
    expect(screen.queryByTestId('data-table-next')).toBeNull();
  });

  it('calls onRowClick, and a getRowProps onClick wins over it', () => {
    const onRowClick = vi.fn();
    renderTable({ onRowClick });
    fireEvent.click(screen.getByTestId('row-2'));
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
    cleanup();
    const own = vi.fn();
    renderTable({ onRowClick, getRowProps: () => ({ onClick: own }) });
    fireEvent.click(screen.getByTestId('row-2'));
    expect(own).toHaveBeenCalled();
    expect(onRowClick).toHaveBeenCalledTimes(1);
  });

  it('spans the empty row over rendered columns only', () => {
    renderTable({ data: [], emptyMessage: 'No rows yet' });
    expect(screen.getByText('No rows yet')).toHaveAttribute('colspan', '1');
  });

  it('wraps in a labelled, focusable scroll region under scrollX', () => {
    renderTable({
      scrollX: true,
      scrollTestId: 'scroller',
      scrollLabel: 'Scores',
    });
    const region = screen.getByRole('region', { name: 'Scores' });
    expect(region).toHaveAttribute('data-testid', 'scroller');
    expect(region).toHaveAttribute('tabindex', '0');
    const cells = within(screen.getByTestId('row-1')).getAllByRole('cell');
    expect(cells[0]).not.toHaveClass('whitespace-normal');
  });
});
