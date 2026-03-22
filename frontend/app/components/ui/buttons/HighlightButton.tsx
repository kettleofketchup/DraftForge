import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

export interface HighlightButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Optional avatar URL displayed as a rounded image before children */
  avatarUrl?: string;
  /** Alt text for the avatar */
  avatarAlt?: string;
}

/**
 * Cyberpunk emerald-to-violet highlight button for featured info
 * (org links, stats, callouts). Brighter teal/cyan gradient with
 * a subtle glow effect.
 *
 * @example
 * ```tsx
 * <HighlightButton avatarUrl={org.logo} avatarAlt={org.name} onClick={...}>
 *   {org.name}
 * </HighlightButton>
 * ```
 */
const HighlightButton = React.forwardRef<HTMLButtonElement, HighlightButtonProps>(
  ({ className, children, avatarUrl, avatarAlt, ...props }, ref) => (
    <Button
      ref={ref}
      className={cn(
        'bg-gradient-to-r from-teal-600/50 to-violet-600/40',
        'border border-teal-400/30',
        'hover:from-teal-500/60 hover:to-violet-500/50 hover:border-teal-300/50',
        'text-teal-100 shadow-lg shadow-teal-900/30',
        'transition-all',
        className,
      )}
      {...props}
    >
      {avatarUrl && (
        <img
          src={avatarUrl}
          alt={avatarAlt ?? ''}
          className="h-5 w-5 rounded-full object-cover ring-1 ring-teal-400/50"
        />
      )}
      {children}
    </Button>
  ),
);

HighlightButton.displayName = 'HighlightButton';

export { HighlightButton };
