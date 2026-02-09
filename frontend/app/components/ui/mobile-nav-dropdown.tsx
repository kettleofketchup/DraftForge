import { Menu } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { brandDepthColors, brandGradient } from '~/components/ui/buttons';
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
  'data-testid'?: string;
}

/**
 * Branded mobile dropdown that replaces tab bars on narrow screens.
 * Primary gradient background with 3D depth, hamburger icon, and
 * secondary highlights for the selected item.
 */
export function MobileNavDropdown({
  label,
  options,
  value,
  onValueChange,
  className,
  'data-testid': testId,
}: MobileNavDropdownProps) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'rounded-lg',
        brandGradient,
        `shadow-lg border-b-4 ${brandDepthColors}`,
        className,
      )}
    >
      {/* Subdued action label */}
      {label && (
        <div className="text-[10px] font-medium uppercase tracking-wider text-white/50 px-3 pt-2">
          {label}
        </div>
      )}

      {/* Dropdown trigger with hamburger icon */}
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="w-full h-10 border-0 rounded-none bg-transparent px-3 text-base font-semibold text-white text-left justify-start focus-visible:ring-0 focus-visible:ring-offset-0 [&>svg:last-child]:text-white/70">
          <Menu className="h-4 w-4 text-white/70 shrink-0 mr-2" />
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
