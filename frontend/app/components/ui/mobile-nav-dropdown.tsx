import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { brandGlowLift, brandGradient, brandSecondary } from '~/components/ui/buttons';
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
  /** data-testid on the wrapper (kept for backwards compatibility) */
  'data-testid'?: string;
  /** data-testid on the SelectTrigger so tests can open the dropdown */
  triggerTestId?: string;
  /** prefix for per-option SelectItem data-testids: `${prefix}${option.value}` */
  itemTestIdPrefix?: string;
}

/**
 * Branded mobile dropdown that replaces tab bars on narrow screens.
 * Primary variant: bold gradient lift for navbar.
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
  triggerTestId,
  itemTestIdPrefix,
}: MobileNavDropdownProps) {
  const isPrimary = variant === 'primary';

  return (
    <div
      data-testid={testId}
      className={cn(
        'rounded-lg',
        isPrimary
          ? [brandGradient, `shadow-lg ${brandGlowLift}`]
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
        <SelectTrigger
          data-testid={triggerTestId}
          className="w-full h-10 border-0 rounded-none bg-transparent px-3 text-base font-semibold text-white text-left justify-start focus-visible:ring-0 focus-visible:ring-offset-0 [&>svg:last-child]:text-white [&>svg:last-child]:h-5 [&>svg:last-child]:w-5"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="border-primary/30">
          {options.map((option) => (
            <SelectItem
              key={option.value}
              value={option.value}
              data-testid={
                itemTestIdPrefix ? `${itemTestIdPrefix}${option.value}` : undefined
              }
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
