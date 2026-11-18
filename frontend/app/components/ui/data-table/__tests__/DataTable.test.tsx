// @vitest-environment jsdom
import type { ColumnDef } from '@tanstack/react-table';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { DataTable, DataTableColumnHeader } from '..';

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

const columns: ColumnDef<Row, any>[] = [
  { accessorKey: 'name', header: 'Name' },
  {
    accessorKey: 'score',
    enableSorting: true,
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Score" />
    ),
    meta: { cellClassName: 'tabular-nums' },
  },
];

function names(): string[] {
  return screen
    .getAllByTestId(/^row-/)
    .map((r) => within(r).getAllByRole('cell')[0].textContent ?? '');
}

afterEach(cleanup);

describe('DataTable', () => {
  it('renders rows in data order with row test ids', () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => String(r.id)}
        rowTestId={(r) => `row-${r.id}`}
      />,
    );
    expect(names()).toEqual(['Bravo', 'Alpha', 'Charlie']);
    expect(screen.getByTestId('row-2')).toHaveTextContent('30');
  });

  it('applies initial sorting', () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => String(r.id)}
        rowTestId={(r) => `row-${r.id}`}
        initialSorting={[{ id: 'score', desc: true }]}
      />,
    );
    expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie']);
  });

  it('sorts only columns that opt in', () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => String(r.id)}
        rowTestId={(r) => `row-${r.id}`}
      />,
    );
    expect(screen.queryByTestId('data-table-sort-name')).toBeNull();
    const sort = screen.getByTestId('data-table-sort-score');
    const header = screen.getByRole('columnheader', { name: /Score/ });
    fireEvent.click(sort);
    expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie']);
    expect(header).toHaveAttribute('aria-sort', 'descending');
    fireEvent.click(sort);
    expect(names()).toEqual(['Charlie', 'Bravo', 'Alpha']);
    expect(header).toHaveAttribute('aria-sort', 'ascending');
  });

  it('applies meta cell classes', () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => String(r.id)}
        rowTestId={(r) => `row-${r.id}`}
      />,
    );
    const cells = within(screen.getByTestId('row-1')).getAllByRole('cell');
    expect(cells[1]).toHaveClass('tabular-nums');
  });

  it('shows the empty message spanning all columns', () => {
    render(
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(r) => String(r.id)}
        emptyMessage="No rows yet"
      />,
    );
    const cell = screen.getByText('No rows yet');
    expect(cell).toHaveAttribute('colspan', '2');
  });
});
