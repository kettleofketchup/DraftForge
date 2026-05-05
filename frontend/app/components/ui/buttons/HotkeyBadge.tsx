import * as React from 'react';
import { Kbd } from '~/components/ui/kbd';
import { LazyTooltip } from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

export interface HotkeyBadgeProps {
  /** The key label to display (e.g. "1", "↵", "⌫"). */
  hotkey: string;
  /**
   * Optional override for the tooltip text. Defaults to
   * `Press <hotkey> for keyboard shortcut`. Pass `null` to disable.
   */
  tooltip?: React.ReactNode | null;
  className?: string;
}

/**
 * A small keycap badge anchored to the top-left of a relatively-positioned
 * parent. Brand buttons wire this through a `hotkey` prop so that callers can
 * surface page-level keyboard shortcuts without hand-rolling positioning each
 * time. The underlying element is the brand `<Kbd>` so the styling rules in
 * the brand review (see /brand → keyboard hints) still apply.
 *
 * Hovering the badge surfaces a `LazyTooltip` describing the shortcut. The
 * lazy variant is used because this badge can appear on many buttons across
 * dense lists; eager Tooltips would inflate render counts.
 */
export function HotkeyBadge({ hotkey, tooltip, className }: HotkeyBadgeProps) {
  // Plain-text key in the tooltip — the shadcn Kbd applies a tooltip-context
  // override (`text-background`) that renders the keycap nearly invisible
  // against the tooltip's own bg. A bold inline string keeps the shortcut
  // legible in the popover.
  const tooltipContent =
    tooltip === null
      ? null
      : tooltip ?? (
          <>Press <strong className="font-semibold">{hotkey}</strong> for keyboard shortcut</>
        );

  // The outer <span> owns positioning + pointer events (Kbd itself sets
  // `pointer-events-none`, which would block tooltip hover detection).
  // LazyTooltip uses asChild on TooltipTrigger, so its ref / handlers attach
  // to this span — the Kbd inside is purely visual.
  const badge = (
    <span
      className={cn(
        'absolute -top-1.5 -left-1.5 z-10 inline-flex cursor-help',
      )}
      aria-label={`Keyboard shortcut: ${hotkey}`}
    >
      <Kbd
        className={cn(
          'h-4 min-w-4 rounded px-1 text-[10px] font-semibold shadow-sm border border-border bg-base-300 text-foreground',
          className,
        )}
      >
        {hotkey}
      </Kbd>
    </span>
  );

  if (tooltipContent === null) return badge;
  return <LazyTooltip content={tooltipContent}>{badge}</LazyTooltip>;
}
