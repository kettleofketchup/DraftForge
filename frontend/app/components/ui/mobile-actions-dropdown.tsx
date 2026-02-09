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
  brandErrorPrimary,
  brandGradient,
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
  primary: `${brandGradient} rounded-sm`,
  destructive: `${brandErrorPrimary} rounded-sm`,
} as const;

/**
 * Reusable branded dropdown that collapses action buttons on mobile.
 * Each action item supports icon, label, onClick, and variant styling.
 * Destructive actions use brandErrorPrimary, primary actions use brandGradient.
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
      <DropdownMenuContent align="end" className={cn(brandBg, 'border-primary/30')}>
        {actions.map((action) => (
          <DropdownMenuItem
            key={action.key}
            onClick={action.onClick}
            disabled={action.disabled}
            data-testid={action['data-testid']}
            className={cn(
              'min-h-[44px] flex items-center gap-2 text-base cursor-pointer',
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
