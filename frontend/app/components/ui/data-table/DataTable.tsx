import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type RowData,
  type SortingState,
} from '@tanstack/react-table';
import { useState, type ReactNode } from 'react';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { cn } from '~/lib/utils';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    headerClassName?: string;
    cellClassName?: string;
  }
}

export interface DataTableProps<TData> {
  columns: ColumnDef<TData, any>[];
  data: TData[];
  getRowId: (row: TData) => string;
  initialSorting?: SortingState;
  emptyMessage?: ReactNode;
  className?: string;
  'data-testid'?: string;
  rowTestId?: (row: TData) => string;
}

export function DataTable<TData>({
  columns,
  data,
  getRowId,
  initialSorting = [],
  emptyMessage = 'Nothing to show',
  className,
  'data-testid': testId,
  rowTestId,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: { sorting },
    onSortingChange: setSorting,
    enableMultiSort: false,
    defaultColumn: { enableSorting: false },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;

  return (
    <Table className={className} data-testid={testId}>
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow
            key={group.id}
            className="border-border hover:bg-transparent"
          >
            {group.headers.map((header) => (
              <TableHead
                key={header.id}
                className={cn(
                  'text-muted-foreground',
                  header.column.columnDef.meta?.headerClassName,
                )}
                aria-sort={
                  header.column.getIsSorted() === 'asc'
                    ? 'ascending'
                    : header.column.getIsSorted() === 'desc'
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
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.length ? (
          rows.map((row) => (
            <TableRow
              key={row.id}
              className="border-border"
              data-testid={rowTestId?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell
                  key={cell.id}
                  className={cell.column.columnDef.meta?.cellClassName}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))
        ) : (
          <TableRow className="hover:bg-transparent">
            <TableCell
              colSpan={table.getVisibleLeafColumns().length}
              className="h-16 text-center text-muted-foreground"
            >
              {emptyMessage}
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
