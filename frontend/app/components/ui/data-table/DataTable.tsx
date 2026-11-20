import {
  columnFacetingFeature,
  columnFilteringFeature,
  columnVisibilityFeature,
  constructFilterFn,
  createFacetedRowModel,
  createFacetedUniqueValues,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_includesString,
  flexRender,
  globalFilteringFeature,
  metaHelper,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
  type Column,
  type ColumnDef,
  type ColumnFiltersState,
  type ColumnVisibilityState,
  type Row,
  type RowData,
  type SortingState,
} from '@tanstack/react-table';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useState, type HTMLAttributes, type ReactNode } from 'react';

import { SecondaryButton } from '~/components/ui/buttons';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { useMediaQuery } from '~/hooks/useMediaQuery';
import { cn } from '~/lib/utils';

import {
  DataTableToolbar,
  type DataTableGlobalSearch,
  type DataTableSearch,
  type ToolbarColumnMeta,
} from './DataTableToolbar';
import { ScrollFrame } from './ScrollFrame';

/**
 * Multi-select "is any of" for faceted filters; an empty selection matches everything.
 * Both sides are compared as strings because facet values are stringified for display.
 */
export const filterFn_oneOf = constructFilterFn({
  filter: (dataValue, filterValue) =>
    !Array.isArray(filterValue) ||
    filterValue.length === 0 ||
    filterValue.includes(String(dataValue)),
  autoRemove: (filterValue) =>
    !Array.isArray(filterValue) || filterValue.length === 0,
});

/**
 * The app's TanStack v9 feature set. v9 registers features explicitly: an API that is
 * missing at runtime means its feature is not listed here. `columnMeta` types the
 * per-column classes DataTable reads.
 */
export const appTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  columnFacetingFeature,
  columnVisibilityFeature,
  rowSortingFeature,
  rowPaginationFeature,
  filteredRowModel: createFilteredRowModel(),
  facetedRowModel: createFacetedRowModel(),
  facetedUniqueValues: createFacetedUniqueValues(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: { includesString: filterFn_includesString, oneOf: filterFn_oneOf },
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
  columnMeta: metaHelper<
    {
      headClassName?: string;
      cellClassName?: string;
      headTestId?: string;
    } & ToolbarColumnMeta
  >(),
});

export type AppFeatures = typeof appTableFeatures;

/** Column def for DataTable. Import this rather than TanStack's `ColumnDef`. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AppColumnDef<TData extends RowData, TValue = any> = ColumnDef<
  AppFeatures,
  TData,
  TValue
>;
export type AppColumn<TData extends RowData, TValue = unknown> = Column<
  AppFeatures,
  TData,
  TValue
>;
export type AppRow<TData extends RowData> = Row<AppFeatures, TData>;

export const CELL_BREAKPOINT_QUERIES = {
  sm: '(min-width: 640px)',
  md: '(min-width: 768px)',
  lg: '(min-width: 1024px)',
} as const;

export type BreakpointMatches = Record<
  keyof typeof CELL_BREAKPOINT_QUERIES,
  boolean
>;

/** Whether a column renders at the current width, read off its `hidden <bp>:table-cell` meta class. */
export function isCellRendered(
  className: string | undefined,
  bp: BreakpointMatches,
): boolean {
  const c = className ?? '';
  if (!/(^|\s)hidden(\s|$)/.test(c)) return true;
  if (c.includes('lg:table-cell')) return bp.lg;
  if (c.includes('md:table-cell')) return bp.md;
  if (c.includes('sm:table-cell')) return bp.sm;
  return false;
}

function useCellBreakpoints(): BreakpointMatches {
  return {
    sm: useMediaQuery(CELL_BREAKPOINT_QUERIES.sm),
    md: useMediaQuery(CELL_BREAKPOINT_QUERIES.md),
    lg: useMediaQuery(CELL_BREAKPOINT_QUERIES.lg),
  };
}

export interface DataTableProps<TData extends RowData> {
  columns: AppColumnDef<TData>[];
  data: TData[];
  getRowId: (row: TData) => string | number;
  getRowTestId?: (row: TData) => string | undefined;
  /** Spread onto each row. Its `onClick` wins over `onRowClick`. */
  getRowProps?: (row: TData) => HTMLAttributes<HTMLTableRowElement>;
  onRowClick?: (row: TData) => void;
  initialSorting?: SortingState;
  /** Show the filter bar built from columns' `meta.filterLabel` / `meta.columnLabel`. */
  enableToolbar?: boolean;
  /** Client-side search across string columns, shown in the toolbar. */
  globalSearch?: DataTableGlobalSearch;
  /** Page-owned search (e.g. server-side), shown in the toolbar instead of `globalSearch`. */
  search?: DataTableSearch;
  initialColumnFilters?: ColumnFiltersState;
  initialColumnVisibility?: ColumnVisibilityState;
  /** Test-id namespace for the toolbar controls (default `table`). */
  toolbarTestIdPrefix?: string;
  /** Left side of the action bar above the table, e.g. a count. */
  toolbarStart?: ReactNode;
  /** Right side of the action bar, e.g. an "Add" button. Independent of `enableToolbar`. */
  toolbarActions?: ReactNode;
  /** Shown instead of `emptyMessage` when filters or search hide every row. */
  emptyFilteredMessage?: ReactNode;
  /** Rows per page; pagination hides itself when everything fits. */
  pageSize?: number;
  emptyMessage?: ReactNode;
  density?: 'default' | 'compact';
  /** Size to content and scroll sideways instead of fitting the container. */
  scrollX?: boolean;
  scrollTestId?: string;
  scrollLabel?: string;
  className?: string;
  'data-testid'?: string;
}

/**
 * Shared table for record lists: client-side sorting and pagination over `data`.
 *
 * Default layout is `table-fixed`: cells wrap, secondary columns take fixed widths
 * (`meta.cellClassName: 'w-24'`) and hide on small screens (`hidden md:table-cell`),
 * and one main column absorbs the rest. `scrollX` opts out of that.
 */
export function DataTable<TData extends RowData>({
  columns,
  data,
  getRowId,
  getRowTestId,
  getRowProps,
  onRowClick,
  initialSorting = [],
  enableToolbar = false,
  globalSearch,
  search,
  initialColumnFilters = [],
  initialColumnVisibility = {},
  toolbarTestIdPrefix = 'table',
  toolbarStart,
  toolbarActions,
  emptyFilteredMessage = 'No results match these filters.',
  pageSize = 25,
  emptyMessage = 'No results.',
  density = 'default',
  scrollX = false,
  scrollTestId,
  scrollLabel,
  className,
  'data-testid': testId,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [columnFilters, setColumnFilters] =
    useState<ColumnFiltersState>(initialColumnFilters);
  const [columnVisibility, setColumnVisibility] =
    useState<ColumnVisibilityState>(initialColumnVisibility);
  const [globalFilter, setGlobalFilter] = useState<string>('');
  const bp = useCellBreakpoints();
  const table = useTable({
    features: appTableFeatures,
    data,
    columns,
    getRowId: (row: TData) => String(getRowId(row)),
    state: { sorting, columnFilters, columnVisibility, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: 'includesString',
    enableMultiSort: false,
    initialState: { pagination: { pageIndex: 0, pageSize } },
  });

  const rows = table.getRowModel().rows;
  const filtering = columnFilters.length > 0 || globalFilter !== '';
  const pageCount = table.getPageCount();
  const { pageIndex } = table.state.pagination;
  const totalRows = table.getPrePaginatedRowModel().rows.length;
  const renderedSpan =
    table
      .getVisibleLeafColumns()
      .filter((c) => isCellRendered(c.columnDef.meta?.cellClassName, bp))
      .length || 1;

  const body = (
    <Table
      data-testid={testId}
      className={cn(
        scrollX ? 'w-max min-w-full' : 'table-fixed',
        '[&_td:first-child]:pl-4 [&_th:first-child]:pl-4',
        density === 'compact' &&
          '[&_td]:px-3 [&_td]:py-1.5 [&_th]:h-auto [&_th]:px-3 [&_th]:py-1.5 [&_th]:text-xs',
      )}
    >
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow
            key={group.id}
            className="border-border hover:bg-transparent"
          >
            {group.headers.map((header) => {
              const sorted = header.column.getIsSorted();
              return (
                <TableHead
                  key={header.id}
                  className={cn(
                    'text-muted-foreground',
                    header.column.columnDef.meta?.headClassName,
                  )}
                  data-testid={header.column.columnDef.meta?.headTestId}
                  aria-sort={
                    sorted === 'asc'
                      ? 'ascending'
                      : sorted === 'desc'
                        ? 'descending'
                        : undefined
                  }
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                </TableHead>
              );
            })}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.length ? (
          rows.map((row, i) => {
            const rowProps = getRowProps?.(row.original);
            const handleClick =
              rowProps?.onClick ??
              (onRowClick ? () => onRowClick(row.original) : undefined);
            const { className: rowClassName, ...restRowProps } = rowProps ?? {};
            return (
              <TableRow
                key={row.id}
                className={cn(
                  'border-border',
                  i % 2 === 0 && 'bg-base-200/40',
                  handleClick && 'cursor-pointer hover:bg-base-300/60',
                  rowClassName,
                )}
                data-testid={getRowTestId?.(row.original)}
                {...restRowProps}
                onClick={handleClick}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className={cn(
                      !scrollX && 'whitespace-normal break-words',
                      cell.column.columnDef.meta?.cellClassName,
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            );
          })
        ) : (
          <TableRow className="hover:bg-transparent">
            <TableCell
              colSpan={renderedSpan}
              className="h-16 text-center text-muted-foreground"
            >
              {filtering ? emptyFilteredMessage : emptyMessage}
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {toolbarStart || toolbarActions ? (
        <div
          data-testid={`${toolbarTestIdPrefix}-actions`}
          className="flex flex-wrap items-center justify-between gap-2"
        >
          <div className="min-w-0 text-sm text-muted-foreground">
            {toolbarStart}
          </div>
          {toolbarActions}
        </div>
      ) : null}
      {enableToolbar && (
        <DataTableToolbar
          table={table}
          search={search}
          globalSearch={globalSearch}
          testIdPrefix={toolbarTestIdPrefix}
        />
      )}
      {scrollX ? (
        <ScrollFrame testId={scrollTestId} label={scrollLabel}>
          {body}
        </ScrollFrame>
      ) : (
        <div className="[&_[data-slot=table-container]]:!overflow-x-hidden">
          {body}
        </div>
      )}
      {pageCount > 1 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Page {pageIndex + 1} of {pageCount} · {totalRows}{' '}
            {totalRows === 1 ? 'result' : 'results'}
          </p>
          <div className="flex items-center gap-2">
            <SecondaryButton
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              data-testid="data-table-prev"
            >
              <ChevronLeft className="size-4" aria-hidden />
              Previous
            </SecondaryButton>
            <SecondaryButton
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              data-testid="data-table-next"
            >
              Next
              <ChevronRight className="size-4" aria-hidden />
            </SecondaryButton>
          </div>
        </div>
      )}
    </div>
  );
}
