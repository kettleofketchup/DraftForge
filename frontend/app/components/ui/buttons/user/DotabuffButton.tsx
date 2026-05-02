import * as React from 'react';
import { SecondaryButton } from '../SecondaryButton';
import type { SecondaryButtonProps } from '../SecondaryButton';
import { DotabuffIconButton } from './DotabuffIconButton';

export interface DotabuffButtonProps
  extends Omit<SecondaryButtonProps, 'children' | 'asChild' | 'color'> {
  /** Steam Friend ID (32-bit account ID). Used to build the Dotabuff URL. */
  steamAccountId: number | null | undefined;
  /** Override the rendered label text. Defaults to "Dotabuff". */
  label?: string;
  /** Override the title (native tooltip). Defaults to "View Dotabuff profile". */
  title?: string;
  /**
   * On screens smaller than `sm` (640px), collapse to the icon-only
   * `<DotabuffIconButton>`. On `sm`+, render the full text+icon variant.
   * Default: true. Pass `false` to always render the full button.
   */
  responsive?: boolean;
}

const DOTABUFF_LOGO =
  'https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B';

/**
 * Dotabuff external-link button. Renders nothing if `steamAccountId` is
 * missing. Wraps the brand `<SecondaryButton>` (per THEMING-GUIDE:
 * "Supporting/contextual action") with `asChild` so the anchor element
 * survives — preserving `target="_blank"` + `rel="noopener noreferrer"`
 * external-link semantics.
 *
 * Native `title` attribute provides the hover tooltip without mounting
 * a Radix Tooltip per visible card (zero React render cost).
 *
 * Responsive behavior (default on): collapses to the icon-only
 * `<DotabuffIconButton>` on screens < sm so dense card lists don't get
 * a wide "[icon] Dotabuff" pill on mobile. Pass `responsive={false}` to
 * keep the full button at every breakpoint.
 *
 * @example
 * ```tsx
 * // Default: icon on mobile, icon+label on sm+
 * <DotabuffButton steamAccountId={user.steam_account_id} />
 *
 * // Always show the full button
 * <DotabuffButton steamAccountId={user.steam_account_id} responsive={false} />
 * ```
 */
const DotabuffButton = React.forwardRef<HTMLButtonElement, DotabuffButtonProps>(
  (
    {
      steamAccountId,
      label = 'Dotabuff',
      title = 'View Dotabuff profile',
      size = 'sm',
      responsive = true,
      className,
      ...props
    },
    ref,
  ) => {
    if (!steamAccountId) return null;
    const url = `https://www.dotabuff.com/players/${steamAccountId}`;
    const fullButton = (
      <SecondaryButton
        ref={ref}
        asChild
        size={size}
        className={
          responsive
            ? // hide on mobile, surface on sm+
              `hidden sm:inline-flex ${className ?? ''}`.trim()
            : className
        }
        {...props}
      >
        <a href={url} target="_blank" rel="noopener noreferrer" title={title}>
          <img
            src={DOTABUFF_LOGO}
            alt=""
            aria-hidden="true"
            className="w-4 h-4"
          />
          <span>{label}</span>
        </a>
      </SecondaryButton>
    );

    if (!responsive) return fullButton;

    return (
      <>
        <DotabuffIconButton
          steamAccountId={steamAccountId}
          title={title}
          className="sm:hidden"
        />
        {fullButton}
      </>
    );
  },
);

DotabuffButton.displayName = 'DotabuffButton';

export { DotabuffButton };
