import * as React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { CheckIcon, ChevronDownIcon } from 'lucide-react';

import { brandBg } from '~/components/ui/buttons';
import {
  Select,
  SelectGroup,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectValue,
} from '~/components/ui/select';
import { cn } from '~/lib/utils';

/**
 * Brand-styled Select trigger and popover content.
 *
 * Maps the shadcn Select primitive to DraftForge's neon-cyber palette:
 * - Trigger sits on `bg-base-300` with a violet hairline that lights up
 *   to brand-violet on hover/focus, matching the PrimaryButton ring.
 * - Content (popover) uses the brand background gradient with a violet
 *   ring so the menu reads as part of the same surface family as
 *   PrimaryButton / Dialog content.
 * - Items use a brand-secondary gradient highlight on hover/focus.
 *
 * Use everywhere a value-picker would otherwise use the neutral shadcn
 * SelectTrigger — Captain Draft Order, role pickers, MMR brackets, etc.
 */

export const BrandSelect = Select;
export { SelectGroup, SelectLabel, SelectScrollDownButton, SelectScrollUpButton, SelectSeparator, SelectValue };

interface BrandSelectTriggerProps
  extends React.ComponentProps<typeof SelectPrimitive.Trigger> {
  /** `sm` height = 32px (h-8); `default` = 36px (h-9). */
  size?: 'sm' | 'default';
}

export const BrandSelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  BrandSelectTriggerProps
>(({ className, size = 'default', children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    data-slot="select-trigger"
    data-size={size}
    className={cn(
      // Base layout
      'inline-flex w-fit items-center justify-between gap-2 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-[box-shadow,background-color,border-color] outline-none',
      'data-[size=default]:h-9 data-[size=sm]:h-8',
      // Brand surface — `brandSecondary` violet→blue translucent gradient
      // with a visible violet hairline ring so the trigger reads as a brand
      // affordance at rest, not a neutral input. Bumped from the original
      // `bg-base-300 / border-violet-400/30` which was too subtle to
      // identify as brand on the captain table.
      'bg-gradient-to-r from-violet-500/20 to-blue-500/10 ring-1 ring-violet-400/60',
      'text-violet-50',
      'hover:from-violet-500/30 hover:to-blue-500/20 hover:ring-violet-400/80',
      // Focus / open state — stronger brand-violet ring
      'focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-1 focus-visible:ring-offset-base-200',
      'data-[state=open]:ring-2 data-[state=open]:ring-violet-400 data-[state=open]:from-violet-500/35 data-[state=open]:to-blue-500/25',
      // Placeholder + value tone
      'data-[placeholder]:text-muted-foreground',
      // Disabled
      'disabled:cursor-not-allowed disabled:opacity-50',
      // Icon defaults
      '[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*="size-"])]:size-4 [&_svg:not([class*="text-"])]:text-violet-300',
      '*:data-[slot=select-value]:line-clamp-1',
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDownIcon className="size-4 opacity-70" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
BrandSelectTrigger.displayName = 'BrandSelectTrigger';

export const BrandSelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentProps<typeof SelectPrimitive.Content>
>(({ className, children, position = 'popper', ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      data-slot="select-content"
      position={position}
      className={cn(
        // Neon-cyber popover surface — same brand-bg gradient + violet ring
        // that <BrandDropdownMenu> content uses, so a value-picker and an
        // action-menu read as siblings on the page.
        brandBg,
        'text-foreground border border-primary/30 shadow-[0_8px_30px_-8px_var(--glow-violet,rgba(124,58,237,0.45))]',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
        'data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2',
        'relative z-50 max-h-(--radix-select-content-available-height) min-w-[6rem] origin-(--radix-select-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-md',
        position === 'popper' &&
          'data-[side=bottom]:translate-y-1 data-[side=top]:-translate-y-1',
        className,
      )}
      {...props}
    >
      <SelectPrimitive.Viewport
        className={cn(
          'p-1',
          position === 'popper' &&
            'h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)] scroll-my-1',
        )}
      >
        {children}
      </SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
BrandSelectContent.displayName = 'BrandSelectContent';

export const BrandSelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentProps<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    data-slot="select-item"
    className={cn(
      'relative flex w-full cursor-pointer items-center gap-2 rounded-sm py-1.5 pr-8 pl-2 text-sm text-foreground select-none outline-hidden',
      'focus:outline-none',
      // Active / focused row — brand secondary gradient (violet→blue/30)
      'focus:bg-gradient-to-r focus:from-violet-500/30 focus:to-blue-500/20 focus:text-violet-100',
      'data-[state=checked]:bg-gradient-to-r data-[state=checked]:from-violet-500/40 data-[state=checked]:to-blue-500/30 data-[state=checked]:text-white',
      'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      '[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*="size-"])]:size-4',
      className,
    )}
    {...props}
  >
    <span className="absolute right-2 flex size-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <CheckIcon className="size-4 text-violet-300" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
BrandSelectItem.displayName = 'BrandSelectItem';
