import { X } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

export interface RemoveIconButtonProps extends Omit<
  React.ComponentProps<typeof Button>,
  'variant' | 'size'
> {
  /** Accessible name, e.g. "Remove critical filter". */
  label: string;
}

/**
 * A small round "x" that removes the thing it sits in (a filter chip, a tag).
 *
 * @example
 * ```tsx
 * <RemoveIconButton label="Remove critical filter" onClick={clear} />
 * ```
 */
const RemoveIconButton = React.forwardRef<
  HTMLButtonElement,
  RemoveIconButtonProps
>(({ label, className, type = 'button', ...props }, ref) => (
  <Button
    ref={ref}
    type={type}
    variant="ghost"
    size="icon"
    aria-label={label}
    className={cn(
      '-mr-0.5 size-5 rounded-full text-muted-foreground hover:bg-base-300 hover:text-foreground',
      className,
    )}
    {...props}
  >
    <X className="size-3" aria-hidden />
  </Button>
));

RemoveIconButton.displayName = 'RemoveIconButton';

export { RemoveIconButton };
