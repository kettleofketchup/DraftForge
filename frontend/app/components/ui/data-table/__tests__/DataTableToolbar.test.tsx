// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import {
  DataTable,
  TABLE_TOOLBAR_MOBILE_QUERY,
  type AppColumnDef,
  type DataTableProps,
} from '..';

interface Row {
  id: number;
  name: string;
  team: string | null;
  role: string;
}

const rows: Row[] = [
  { id: 1, name: 'Ana', team: 'Radiant', role: 'carry' },
  { id: 2, name: 'Bo', team: 'Dire', role: 'support' },
  { id: 3, name: 'Cy', team: 'Radiant', role: 'support' },
  { id: 4, name: 'Di', team: null, role: 'mid' },
];

const columns: AppColumnDef<Row>[] = [
  { accessorKey: 'name', header: 'Name' },
  {
    accessorKey: 'team',
    header: 'Team',
    filterFn: 'oneOf',
    meta: { filterLabel: 'Team', columnLabel: 'Team' },
  },
  {
    accessorKey: 'role',
    header: 'Role',
    filterFn: 'oneOf',
    meta: {
      filterLabel: 'Role',
      facetLabel: (v) => v.toUpperCase(),
    },
  },
];

function names(): string[] {
  return screen
    .queryAllByTestId(/^row-/)
    .map((r) => within(r).getAllByRole('cell')[0].textContent ?? '');
}

function renderTable(props: Partial<DataTableProps<Row>> = {}) {
  return render(
    <DataTable
      columns={columns}
      data={rows}
      getRowId={(r) => r.id}
      getRowTestId={(r) => `row-${r.id}`}
      enableToolbar
      {...props}
    />,
  );
}

function setMobile(mobile: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: mobile && query === TABLE_TOOLBAR_MOBILE_QUERY,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function openFacet(id: string) {
  fireEvent.click(screen.getByTestId(`table-facet-trigger-${id}`));
  return screen.getByTestId(`table-facet-panel-${id}`);
}

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.scrollIntoView ??= vi.fn();
});

afterEach(() => {
  cleanup();
  setMobile(false);
});

describe('DataTableToolbar', () => {
  it('renders nothing when no column opts in and there is no search', () => {
    render(
      <DataTable
        columns={[{ accessorKey: 'name', header: 'Name' }]}
        data={rows}
        getRowId={(r) => r.id}
        enableToolbar
      />,
    );
    expect(screen.queryByTestId('table-toolbar')).toBeNull();
  });

  it('lists facet options with counts, labels and a Not set entry', () => {
    renderTable();
    const panel = openFacet('team');
    expect(
      within(panel).getByTestId('table-facet-option-team-radiant'),
    ).toHaveTextContent(/Radiant\s*2/);
    expect(
      within(panel).getByTestId('table-facet-option-team-none'),
    ).toHaveTextContent(/Not set\s*1/);
    fireEvent.keyDown(panel, { key: 'Escape' });
    const roles = openFacet('role');
    expect(
      within(roles).getByTestId('table-facet-option-role-support'),
    ).toHaveTextContent('SUPPORT');
  });

  it('filters rows by the selected facet values and shows a removable chip', () => {
    renderTable();
    const panel = openFacet('team');
    fireEvent.click(
      within(panel).getByTestId('table-facet-option-team-radiant'),
    );
    expect(names()).toEqual(['Ana', 'Cy']);
    expect(
      within(panel).getByTestId('table-facet-option-team-radiant'),
    ).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(within(panel).getByTestId('table-facet-option-team-dire'));
    expect(names()).toEqual(['Ana', 'Bo', 'Cy']);
    expect(
      screen.getByTestId('table-filter-chip-team-radiant'),
    ).toHaveTextContent('Team: Radiant');
    fireEvent.click(
      screen.getByTestId('table-filter-chip-remove-team-radiant'),
    );
    expect(names()).toEqual(['Bo']);
  });

  it('combines filters across columns', () => {
    renderTable({
      initialColumnFilters: [
        { id: 'team', value: ['Radiant'] },
        { id: 'role', value: ['support'] },
      ],
    });
    expect(names()).toEqual(['Cy']);
    expect(screen.getByTestId('table-facet-trigger-team')).toHaveTextContent(
      'Radiant',
    );
    expect(screen.getByTestId('table-facet-trigger-role')).toHaveTextContent(
      'SUPPORT',
    );
  });

  it('reads All with nothing selected and counts past two values', () => {
    renderTable({
      initialColumnFilters: [
        { id: 'role', value: ['carry', 'mid', 'support'] },
      ],
    });
    expect(screen.getByTestId('table-facet-trigger-team')).toHaveTextContent(
      'All',
    );
    expect(screen.getByTestId('table-facet-trigger-role')).toHaveTextContent(
      '3 selected',
    );
  });

  it('orders options by meta.facetOrder, then alphabetically', () => {
    render(
      <DataTable
        columns={[
          { accessorKey: 'name', header: 'Name' },
          {
            accessorKey: 'role',
            header: 'Role',
            filterFn: 'oneOf',
            meta: { filterLabel: 'Role', facetOrder: ['support', 'carry'] },
          },
        ]}
        data={rows}
        getRowId={(r) => r.id}
        enableToolbar
      />,
    );
    const panel = openFacet('role');
    const opts = within(panel)
      .getAllByTestId(/^table-facet-option-role-/)
      .map((o) => o.getAttribute('data-testid'));
    expect(opts).toEqual([
      'table-facet-option-role-support',
      'table-facet-option-role-carry',
      'table-facet-option-role-mid',
    ]);
  });

  it('searches string columns client-side', () => {
    renderTable({ globalSearch: { placeholder: 'Search players' } });
    const input = screen.getByTestId('table-search');
    expect(input).toHaveAccessibleName('Search');
    fireEvent.change(input, { target: { value: 'bo' } });
    expect(names()).toEqual(['Bo']);
  });

  it('uses a page-owned search when given', () => {
    const onChange = vi.fn();
    renderTable({ search: { value: 'x', onChange, label: 'Find' } });
    const input = screen.getByTestId('table-search');
    expect(input).toHaveValue('x');
    fireEvent.change(input, { target: { value: 'xy' } });
    expect(onChange).toHaveBeenCalledWith('xy');
    expect(names()).toHaveLength(4);
  });

  it('resets filters and search together', () => {
    renderTable({
      globalSearch: {},
      initialColumnFilters: [{ id: 'team', value: ['Dire'] }],
    });
    fireEvent.change(screen.getByTestId('table-search'), {
      target: { value: 'zzz' },
    });
    expect(
      screen.getByText('No results match these filters.'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('table-filters-reset'));
    expect(names()).toHaveLength(4);
    expect(screen.getByTestId('table-search')).toHaveValue('');
    expect(screen.queryByTestId('table-filters-reset')).toBeNull();
  });

  it('hides and shows columns from the Columns menu', () => {
    renderTable();
    expect(
      screen.getByRole('columnheader', { name: 'Team' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('table-columns-trigger')).toHaveTextContent(
      'All shown',
    );
    fireEvent.click(screen.getByTestId('table-columns-trigger'));
    fireEvent.click(screen.getByTestId('table-columns-option-team'));
    expect(screen.getByTestId('table-columns-trigger')).toHaveTextContent(
      '1 hidden',
    );
    expect(screen.queryByRole('columnheader', { name: 'Team' })).toBeNull();
    expect(
      screen.getByRole('columnheader', { name: 'Role' }),
    ).toBeInTheDocument();
  });

  it('namespaces toolbar test ids', () => {
    renderTable({ toolbarTestIdPrefix: 'players' });
    expect(screen.getByTestId('players-toolbar')).toBeInTheDocument();
    expect(
      screen.getByTestId('players-facet-trigger-team'),
    ).toBeInTheDocument();
  });

  it('moves the controls into a Filters sheet on phones, keeping chips on the bar', () => {
    setMobile(true);
    renderTable({ initialColumnFilters: [{ id: 'team', value: ['Dire'] }] });
    expect(screen.queryByTestId('table-facet-trigger-team')).toBeNull();
    const trigger = screen.getByTestId('table-filters-sheet-trigger');
    expect(trigger).toHaveTextContent('Filters1');
    expect(screen.queryByTestId('table-filters-sheet')).toBeNull();
    expect(
      screen.getByTestId('table-filter-chip-team-dire'),
    ).toBeInTheDocument();
    fireEvent.click(trigger);
    const sheet = screen.getByTestId('table-filters-sheet');
    expect(
      within(sheet).getByTestId('table-facet-trigger-team'),
    ).toBeInTheDocument();
  });
});
