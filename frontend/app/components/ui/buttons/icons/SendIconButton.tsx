import { Send } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

export interface SendIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {}

/**
 * A send icon button with secondary styling.
 * Used for sending messages or submissions.
 *
 * @example
 * ```tsx
 * <SendIconButton onClick={handleSend} disabled={!message} />
 * ```
 */
const SendIconButton = React.forwardRef<HTMLButtonElement, SendIconButtonProps>(
  ({ className, ...props }, ref) => {
    return (
      <Button
        ref={ref}
        variant="secondary"
        size="icon"
        className={cn(
          'rounded-full',
          'shadow-lg shadow-black/30 border-b-4 border-b-secondary/50',
          'active:border-b-0 active:translate-y-1 transition-all duration-75',
          className
        )}
        {...props}
      >
        <Send className="h-4 w-4" />
        <span className="sr-only">Send</span>
      </Button>
    );
  }
);

SendIconButton.displayName = 'SendIconButton';

export { SendIconButton };
