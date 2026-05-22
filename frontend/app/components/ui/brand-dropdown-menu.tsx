import { ChevronDown } from 'lucide-react';
import { Fragment } from 'react';
import { Button } from '~/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { brandBg, brandErrorBg } from '~/components/ui/buttons';
import { cn } from '~/lib/utils';

export interface BrandDropdownAction {
  key: string;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'edit' | 'success' | 'destructive';
  disabled?: boolean;
  'data-testid'?: string;
}

interface BrandDropdownMenuProps {
  /** Button label text */
  label: string;
  /** Optional icon before label */
  icon?: React.ReactNode;
  /** Menu items */
  actions: BrandDropdownAction[];
  /** Optional group label inside the menu */
  menuLabel?: string;
  /** Visual style */
  variant?: 'primary' | 'secondary' | 'admin';
  className?: string;
  'data-testid'?: string;
}

// Per-variant text + icon tone. Hover/focus background is brand-aligned per
// row so the focus wash matches the row's brand tone (Edit → emerald, Delete
// → red, etc.) instead of shadcn's default cyan `bg-accent`.
//
// Edit text uses a solid emerald instead of a bg-clip-text gradient because
// the gradient owns the element's background-image, which would compete with
// the focus background and end up invisible.
const variantStyles = {
  default: 'text-foreground focus:bg-violet-500/20',
  primary: 'text-primary font-medium [&_svg]:text-primary focus:bg-violet-500/20',
  edit: 'text-emerald-300 font-medium [&_svg]:text-emerald-300 focus:bg-emerald-500/20',
  success: 'text-success font-medium [&_svg]:text-success focus:bg-emerald-500/20',
  destructive: 'text-error font-medium [&_svg]:text-error focus:bg-red-500/20',
} as const;

const triggerVariants = {
  primary: 'bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white border-0',
  secondary: 'bg-transparent border border-border text-foreground hover:bg-accent',
  admin: `${brandErrorBg} text-foreground hover:brightness-110`,
} as const;

/**
 * Branded dropdown menu with a labeled trigger button.
 * Variants:
 * - primary: brand gradient trigger (for main CTAs)
 * - secondary: outline trigger (general actions)
 * - admin: brandErrorBg trigger (admin/destructive action groups)
 */
export function BrandDropdownMenu({
  label,
  icon,
  actions,
  menuLabel,
  variant = 'secondary',
  className,
  'data-testid': testId,
}: BrandDropdownMenuProps) {
  const visibleActions = actions.filter((a) => !a.disabled);
  if (visibleActions.length === 0) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          data-testid={testId}
          className={cn(
            'gap-1.5',
            triggerVariants[variant],
            className,
          )}
        >
          {icon}
          {label}
          <ChevronDown className="h-3.5 w-3.5 opacity-70" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className={cn(brandBg, 'border-primary/30 min-w-[200px] p-1.5 space-y-0.5')}
      >
        {menuLabel && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground px-3 py-1.5">
              {menuLabel}
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-border/50" />
          </>
        )}
        {actions.map((action, idx) => (
          <Fragment key={action.key}>
            {idx > 0 && (
              <DropdownMenuSeparator className="!my-0 bg-border/40" />
            )}
            <DropdownMenuItem
              onClick={action.onClick}
              disabled={action.disabled}
              data-testid={action['data-testid']}
              className={cn(
                'min-h-[36px] flex items-center gap-2.5 px-3 py-2 text-sm cursor-pointer rounded-md',
                variantStyles[action.variant ?? 'default'],
              )}
            >
              {action.icon}
              {action.label}
            </DropdownMenuItem>
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
