import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
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

import { ScrollFrame } from './ScrollFrame';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    headClassName?: string;
    cellClassName?: string;
    headTestId?: string;
  }
}

/** Column def for DataTable. Import this rather than TanStack's `ColumnDef`. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AppColumnDef<TData extends RowData, TValue = any> = ColumnDef<
  TData,
  TValue
>;

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
  const bp = useCellBreakpoints();
  const table = useReactTable({
    data,
    columns,
    getRowId: (row) => String(getRowId(row)),
    state: { sorting },
    onSortingChange: setSorting,
    enableMultiSort: false,
    initialState: { pagination: { pageIndex: 0, pageSize } },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const rows = table.getRowModel().rows;
  const pageCount = table.getPageCount();
  const { pageIndex } = table.getState().pagination;
  const totalRows = table.getPrePaginationRowModel().rows.length;
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
              {emptyMessage}
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );

  return (
    <div className={cn('flex flex-col gap-3', className)}>
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
