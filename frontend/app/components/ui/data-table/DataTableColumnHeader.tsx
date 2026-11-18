import type { Column } from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

export interface DataTableColumnHeaderProps<TData, TValue> {
  column: Column<TData, TValue>;
  title: string;
  className?: string;
}

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <span className={className}>{title}</span>;
  }
  const sorted = column.getIsSorted();
  const Icon =
    sorted === 'asc' ? ArrowUp : sorted === 'desc' ? ArrowDown : ArrowUpDown;
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn('-ml-2 h-8 gap-1 px-2 text-muted-foreground', className)}
      onClick={column.getToggleSortingHandler()}
      data-testid={`data-table-sort-${column.id}`}
    >
      {title}
      <Icon className={cn('size-3.5', !sorted && 'opacity-50')} aria-hidden />
    </Button>
  );
}
