import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandSecondary, button3DBase } from '../styles';

export interface DotabuffIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size' | 'asChild'> {
  /** Steam Friend ID (32-bit account ID). Used to build the Dotabuff URL. */
  steamAccountId: number | null | undefined;
  /** Override the title (native tooltip). Defaults to "View Dotabuff profile". */
  title?: string;
}

const DOTABUFF_LOGO =
  'https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B';

/**
 * Icon-only Dotabuff external-link button. Renders nothing if
 * `steamAccountId` is missing. Same brand-secondary treatment as
 * `<DotabuffButton>` but compact (icon only) for dense card layouts.
 *
 * Native `title` attribute provides the hover tooltip without mounting
 * a Radix Tooltip per visible card (zero React render cost).
 *
 * @example
 * ```tsx
 * <DotabuffIconButton steamAccountId={user.steam_account_id} />
 * ```
 */
const DotabuffIconButton = React.forwardRef<HTMLButtonElement, DotabuffIconButtonProps>(
  ({ steamAccountId, title = 'View Dotabuff profile', className, ...props }, ref) => {
    if (!steamAccountId) return null;
    const url = `https://www.dotabuff.com/players/${steamAccountId}`;
    return (
      <Button
        ref={ref}
        size="icon"
        asChild
        className={cn(
          'rounded-full',
          brandSecondary,
          button3DBase,
          'border-b-violet-700/50 shadow-black/30',
          className,
        )}
        {...props}
      >
        <a href={url} target="_blank" rel="noopener noreferrer" title={title}>
          <img
            src={DOTABUFF_LOGO}
            alt=""
            aria-hidden="true"
            className="w-4 h-4"
          />
          <span className="sr-only">{title}</span>
        </a>
      </Button>
    );
  },
);

DotabuffIconButton.displayName = 'DotabuffIconButton';

export { DotabuffIconButton };
