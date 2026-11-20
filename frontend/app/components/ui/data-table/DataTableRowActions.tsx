import { EllipsisVertical } from 'lucide-react';
import type { ReactNode } from 'react';

import { brandBg, SecondaryButton } from '~/components/ui/buttons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { cn } from '~/lib/utils';

export interface DataTableRowAction {
  key: string;
  label: string;
  onSelect: () => void;
  icon?: ReactNode;
  destructive?: boolean;
  disabled?: boolean;
  /** Why a disabled action is unavailable, shown under its label. */
  hint?: string;
  testId?: string;
}

export interface DataTableRowActionsProps {
  /** Accessible name of the trigger, e.g. "Actions for <player>". */
  label: string;
  actions: DataTableRowAction[];
  disabled?: boolean;
  'data-testid'?: string;
}

/**
 * Per-row actions menu for a DataTable `actions` column. Disabled actions stay
 * listed with their `hint`; clicks never reach the row's `onRowClick`.
 */
export function DataTableRowActions({
  label,
  actions,
  disabled = false,
  'data-testid': testId,
}: DataTableRowActionsProps) {
  if (actions.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <SecondaryButton
          size="icon"
          aria-label={label}
          disabled={disabled}
          data-testid={testId}
          className="size-11 sm:size-8"
          onClick={(e) => e.stopPropagation()}
        >
          <EllipsisVertical className="size-4" aria-hidden />
        </SecondaryButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className={cn(brandBg, 'min-w-44 border-primary/30 p-1.5')}
        onClick={(e) => e.stopPropagation()}
      >
        {actions.map((action) => (
          <DropdownMenuItem
            key={action.key}
            disabled={action.disabled}
            data-testid={action.testId}
            onSelect={action.onSelect}
            className={cn(
              'flex min-h-11 cursor-pointer flex-col items-start gap-0.5 rounded-md px-3 py-2 text-sm sm:min-h-9',
              action.destructive
                ? 'font-medium text-error focus:bg-error/20 focus:text-error'
                : 'text-foreground focus:bg-selection/20',
            )}
          >
            <span className="flex items-center gap-2">
              {action.icon}
              {action.label}
            </span>
            {action.hint ? (
              <span className="text-xs text-muted-foreground">
                {action.hint}
              </span>
            ) : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
