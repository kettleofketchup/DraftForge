import * as RadioGroupPrimitive from '@radix-ui/react-radio-group';
import * as React from 'react';

import { cn } from '~/lib/utils';

const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>
>(({ className, ...props }, ref) => {
  return (
    <RadioGroupPrimitive.Root
      className={cn('grid gap-2', className)}
      {...props}
      ref={ref}
    />
  );
});
RadioGroup.displayName = RadioGroupPrimitive.Root.displayName;

// h-4 w-4 rather than size-4: callers that hide the item with sr-only rely on
// the existing width/height cascade.
// p-0, outline-none and the hover border override app.css's base-layer button rules.
const RadioGroupItem = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Item>
>(({ className, ...props }, ref) => {
  return (
    <RadioGroupPrimitive.Item
      ref={ref}
      className={cn(
        'aspect-square h-4 w-4 shrink-0 rounded-full border border-primary/60 bg-input/30 p-0 shadow-sm outline-none transition-[border-color,box-shadow,background-color] duration-150',
        'enabled:hover:border-primary enabled:hover:bg-primary/10 enabled:hover:shadow-[0_0_8px_var(--glow-violet)]',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'data-[state=checked]:border-primary data-[state=checked]:bg-primary/15 enabled:data-[state=checked]:shadow-[0_0_10px_var(--glow-violet)]',
        'disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none',
        className,
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator className="flex size-full items-center justify-center">
        <span
          data-slot="radio-group-dot"
          className="size-2 rounded-full bg-gradient-to-br from-primary to-interactive"
        />
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  );
});
RadioGroupItem.displayName = RadioGroupPrimitive.Item.displayName;

export { RadioGroup, RadioGroupItem };
