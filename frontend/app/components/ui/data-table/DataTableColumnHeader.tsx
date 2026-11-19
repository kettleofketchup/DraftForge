import type { RowData } from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';

import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

import type { AppColumn } from './DataTable';

export interface DataTableColumnHeaderProps<TData extends RowData, TValue> {
  column: AppColumn<TData, TValue>;
  title: string;
  className?: string;
}

/**
 * Sortable header: `header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />`.
 * Clicks follow TanStack's order (first direction from `sortDescFirst`, then the
 * other, then unsorted). Plain text when the column can't sort.
 */
export function DataTableColumnHeader<TData extends RowData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <span className={className}>{title}</span>;
  }
  const sorted = column.getIsSorted();
  const next = column.getNextSortingOrder();
  const Icon =
    sorted === 'asc' ? ArrowUp : sorted === 'desc' ? ArrowDown : ChevronsUpDown;
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn(
        '-ml-2 h-8 gap-1 pl-2 text-muted-foreground data-[active=true]:text-foreground',
        className,
      )}
      data-active={sorted ? 'true' : 'false'}
      data-testid={`data-table-sort-${column.id}`}
      onClick={() =>
        next === false
          ? column.clearSorting()
          : column.toggleSorting(next === 'desc')
      }
      aria-label={`Sort by ${title}, ${
        next === 'asc'
          ? 'ascending'
          : next === 'desc'
            ? 'descending'
            : 'clear sort'
      }`}
    >
      {title}
      <Icon
        className={cn(
          'size-3.5',
          sorted ? 'text-foreground' : 'text-muted-foreground',
        )}
        aria-hidden
      />
    </Button>
  );
}
