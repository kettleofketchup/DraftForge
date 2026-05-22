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
import {
  brandBg,
  brandDepthColors,
  brandErrorBg,
  brandGradient,
  brandSecondary,
  button3DBase,
  button3DDisabled,
} from '~/components/ui/buttons';
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

// Per-variant text + icon tone. Hover wash is brand-aligned per row so the
// highlight matches the row's tone (Edit → emerald, Delete → red, etc.)
// instead of shadcn's default cyan `bg-accent`. Both `hover:` and `focus:`
// states are set — Radix moves focus on hover for mouse users, but the
// shadcn item base also carries `focus:bg-accent` which can race the
// merge; specifying `hover:` directly is the belt to that braces.
const variantStyles = {
  default: 'text-foreground hover:bg-violet-500/20 focus:bg-violet-500/20',
  primary: 'text-primary font-medium [&_svg]:text-primary hover:bg-violet-500/20 focus:bg-violet-500/20',
  edit: 'text-emerald-300 font-medium [&_svg]:text-emerald-300 hover:bg-emerald-500/20 focus:bg-emerald-500/20',
  success: 'text-success font-medium [&_svg]:text-success hover:bg-emerald-500/20 focus:bg-emerald-500/20',
  destructive: 'text-error font-medium [&_svg]:text-error hover:bg-red-500/20 focus:bg-red-500/20',
} as const;

// Triggers reuse the same brand pill recipes the standalone buttons use, so
// a `<BrandDropdownMenu variant="primary">` looks identical to a
// `<PrimaryButton>` (3D depth, indigo bottom-edge, brand-violet glow), a
// `secondary` variant matches `<SecondaryButton>` (violet ring outline),
// and `admin` matches the wine/violet error surface used for destructive
// action groups. Without the 3D classes the Reseed trigger went flat
// against the otherwise depthful toolbar.
const triggerVariants = {
  primary: `${button3DBase} ${button3DDisabled} ${brandGradient} ${brandDepthColors} border-0`,
  secondary: `${button3DBase} ${button3DDisabled} ${brandSecondary} border-b-violet-700/50`,
  admin: `${button3DBase} ${button3DDisabled} ${brandErrorBg} text-foreground hover:brightness-110 border-b-red-900/60 shadow-red-950/40`,
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
