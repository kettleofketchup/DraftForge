import { EllipsisVertical } from 'lucide-react';
import { useId, type ReactNode } from 'react';

import { brandBg, SecondaryButton } from '~/components/ui/buttons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { useMediaQuery } from '~/hooks/useMediaQuery';
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
  /**
   * From this breakpoint up, the actions render as inline buttons and the
   * menu is gone; below it only the menu renders. Unset: always the menu.
   */
  inlineFrom?: 'md' | 'lg';
  'data-testid'?: string;
}

const INLINE_QUERY: Record<'md' | 'lg', string> = {
  md: '(min-width: 768px)',
  lg: '(min-width: 1024px)',
};

function InlineAction({
  action,
  disabled,
}: {
  action: DataTableRowAction;
  disabled: boolean;
}) {
  const hintId = useId();
  const button = (
    <SecondaryButton
      size="sm"
      color={action.destructive ? 'red' : undefined}
      disabled={disabled || action.disabled}
      data-testid={action.testId}
      className="min-h-11 sm:min-h-8"
      onClick={(e) => {
        e.stopPropagation();
        action.onSelect();
      }}
    >
      {action.icon}
      {action.label}
    </SecondaryButton>
  );
  if (!action.disabled || !action.hint) return button;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            aria-describedby={hintId}
            className="inline-flex cursor-not-allowed rounded-md"
            onClick={(e) => e.stopPropagation()}
          >
            {button}
            <span id={hintId} className="sr-only">
              {action.hint}
            </span>
          </span>
        </TooltipTrigger>
        <TooltipContent>{action.hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Per-row actions for a DataTable `actions` column: a menu, or inline buttons
 * from `inlineFrom` up. Disabled actions stay shown with their `hint` (menu
 * text or tooltip); clicks never reach the row's `onRowClick`.
 */
export function DataTableRowActions({
  label,
  actions,
  disabled = false,
  inlineFrom,
  'data-testid': testId,
}: DataTableRowActionsProps) {
  const wide = useMediaQuery(inlineFrom ? INLINE_QUERY[inlineFrom] : 'not all');
  if (actions.length === 0) return null;
  if (inlineFrom && wide) {
    return (
      <div
        role="group"
        aria-label={label}
        data-testid={testId}
        className="flex flex-wrap items-center justify-end gap-1.5"
      >
        {actions.map((action) => (
          <InlineAction key={action.key} action={action} disabled={disabled} />
        ))}
      </div>
    );
  }
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
