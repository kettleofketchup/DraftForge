import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { brandDepthColors, brandGradient, brandSecondary } from '~/components/ui/buttons';
import { cn } from '~/lib/utils';

export interface MobileNavOption {
  value: string;
  label: string;
}

interface MobileNavDropdownProps {
  /** Subdued action label (e.g. "Navigate to", "Switch view") */
  label?: string;
  options: MobileNavOption[];
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
  /** "primary" (bold gradient) for navbar, "secondary" (subtle) for in-page */
  variant?: 'primary' | 'secondary';
  'data-testid'?: string;
}

/**
 * Branded mobile dropdown that replaces tab bars on narrow screens.
 * Primary variant: bold gradient with 3D depth for navbar.
 * Secondary variant: subtle translucent gradient for in-page tabs.
 */
export function MobileNavDropdown({
  label,
  options,
  value,
  onValueChange,
  className,
  variant = 'primary',
  'data-testid': testId,
}: MobileNavDropdownProps) {
  const isPrimary = variant === 'primary';

  return (
    <div
      data-testid={testId}
      className={cn(
        'rounded-lg',
        isPrimary
          ? [brandGradient, `shadow-lg border-b-4 ${brandDepthColors}`]
          : brandSecondary,
        className,
      )}
    >
      {/* Subdued action label */}
      {label && (
        <div className="text-[10px] font-medium uppercase tracking-wider text-white/50 px-3 pt-2">
          {label}
        </div>
      )}

      {/* Dropdown trigger with chevron indicator */}
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="w-full h-10 border-0 rounded-none bg-transparent px-3 text-base font-semibold text-white text-left justify-start focus-visible:ring-0 focus-visible:ring-offset-0 [&>svg:last-child]:text-white [&>svg:last-child]:h-5 [&>svg:last-child]:w-5">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="border-primary/30">
          {options.map((option) => (
            <SelectItem
              key={option.value}
              value={option.value}
              className={cn(
                'min-h-[44px] flex items-center text-base cursor-pointer',
                option.value === value &&
                  'bg-secondary/20 text-secondary font-medium',
              )}
            >
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
