import { EllipsisVertical } from 'lucide-react';
import { Button } from '~/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import {
  brandBg,
  brandDepthColors,
  button3DBase,
} from '~/components/ui/buttons';
import { cn } from '~/lib/utils';

export interface MobileAction {
  key: string;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'destructive';
  disabled?: boolean;
  'data-testid'?: string;
}

interface MobileActionsDropdownProps {
  actions: MobileAction[];
  className?: string;
  'data-testid'?: string;
}

const variantStyles = {
  default: 'text-foreground',
  primary: 'text-primary font-medium',
  destructive: 'text-error font-medium',
} as const;

/**
 * Reusable branded dropdown that collapses action buttons on mobile.
 * Each action item supports icon, label, onClick, and variant styling.
 * Variants use text color accents (not gradient backgrounds).
 */
export function MobileActionsDropdown({
  actions,
  className,
  'data-testid': testId,
}: MobileActionsDropdownProps) {
  const enabledActions = actions.filter((a) => !a.disabled);

  if (enabledActions.length === 0) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          data-testid={testId}
          className={cn(
            button3DBase,
            brandBg,
            `border border-primary/25 ${brandDepthColors}`,
            'text-foreground',
            className,
          )}
        >
          <EllipsisVertical className="h-5 w-5" />
          <span className="sr-only">Actions</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className={cn(brandBg, 'border-primary/30 min-w-[180px] p-1.5')}>
        {actions.map((action) => (
          <DropdownMenuItem
            key={action.key}
            onClick={action.onClick}
            disabled={action.disabled}
            data-testid={action['data-testid']}
            className={cn(
              'min-h-[40px] flex items-center gap-2.5 px-3 py-2 text-sm cursor-pointer rounded-md',
              variantStyles[action.variant ?? 'default'],
            )}
          >
            {action.icon}
            {action.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
