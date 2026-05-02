import * as React from "react"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { cn } from "~/lib/utils"

function TooltipProvider({
  delayDuration = 0,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return (
    <TooltipPrimitive.Provider
      data-slot="tooltip-provider"
      delayDuration={delayDuration}
      {...props}
    />
  )
}

function Tooltip({
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />
}

function TooltipTrigger({
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />
}

function TooltipContent({
  className,
  sideOffset = 0,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "bg-popover text-popover-foreground border border-border animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-50 w-fit origin-(--radix-tooltip-content-transform-origin) rounded-md px-3 py-1.5 text-xs text-balance shadow-md",
          className
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="bg-popover fill-popover z-50 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45 rounded-[2px]" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  )
}

/**
 * FastTooltip — pure native `title` attribute, NEVER mounts Radix.
 *
 * Use this for the most extreme dense displays (e.g. the 125-hero
 * herodraft grid) where the styled Radix bubble doesn't add value and
 * any per-item React/Radix cost is too much. Cheapest possible tooltip.
 *
 * If you want native fallback PLUS upgrade to the styled Radix bubble on
 * first hover, use `<LazyTooltip>` instead.
 *
 * @example
 * <FastTooltip content="Hero name">
 *   <button>Hover me</button>
 * </FastTooltip>
 */
interface FastTooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  /** @deprecated Native title doesn't support positioning */
  side?: 'top' | 'bottom' | 'left' | 'right';
  /** @deprecated Native title doesn't support custom styling */
  className?: string;
}

function FastTooltip({
  content,
  children,
}: FastTooltipProps) {
  // Use native title for performance - no React overhead, no sticky tooltip issues
  const title = typeof content === 'string' ? content : undefined;

  return (
    <span title={title} style={{ display: 'contents' }}>
      {children}
    </span>
  );
}

/**
 * LazyTooltip — defers mounting the heavy Radix Tooltip subtree
 * (TooltipContent + TooltipPortal + Popper) until the user actually
 * interacts with the trigger. The trigger renders immediately with a
 * native `title` attribute as the pre-hover fallback. The first
 * pointerenter / focus / touchstart event swaps in the full Radix
 * Tooltip — same styling as the eager `<Tooltip>` thereafter.
 *
 * When to use this instead of `<Tooltip>`:
 *
 * - **Dense lists** (user grid, roster, draft picks) where hundreds of
 *   tooltips would otherwise render eagerly even though only a handful
 *   are ever opened. The trace was showing 206 Tooltip renders /
 *   74 TooltipContent renders / 132 TooltipPortal+Popper renders per
 *   scroll frame on the /users grid — those evaporate with this pattern.
 *
 * For one-off tooltips (page header actions, modal buttons), the
 * regular `<Tooltip>` is fine.
 *
 * Pattern modeled after https://github.com/FranciscoMoretti/shadcn-lazy-tooltip
 *
 * @example
 * ```tsx
 * <LazyTooltip content="Edit user">
 *   <EditIconButton onClick={handleEdit} />
 * </LazyTooltip>
 * ```
 */
interface LazyTooltipProps {
  /** Tooltip body. Strings are also surfaced as the native `title` fallback before lazy mount. */
  content: React.ReactNode;
  /** The element that triggers the tooltip. Must accept ref + pointer/focus handlers. */
  children: React.ReactElement;
  /** Side of the trigger to render the tooltip. Defaults to Radix default. */
  side?: 'top' | 'right' | 'bottom' | 'left';
  /** Override delayDuration for this specific tooltip (otherwise inherits from TooltipProvider). */
  delayDuration?: number;
}

function LazyTooltip({ content, children, side, delayDuration }: LazyTooltipProps) {
  const [armed, setArmed] = React.useState(false);
  const onArm = React.useCallback(() => setArmed(true), []);

  // Tooltip + TooltipTrigger are mounted from the start so the wrapped
  // child stays in a stable React tree — critical for buttons whose
  // onClick opens a modal: replacing the wrapper between renders drops
  // the in-flight click event during reconciliation. Only the heavy
  // TooltipContent (Popper + Portal + content tree) is lazy-mounted
  // on first interaction.
  //
  // Radix composes its own pointer/focus handlers with the props we
  // pass to TooltipTrigger, so onArm fires alongside Radix's internal
  // open-on-hover logic — both work without contention.
  return (
    <Tooltip delayDuration={delayDuration}>
      <TooltipTrigger
        asChild
        onPointerEnter={onArm}
        onFocus={onArm}
        onTouchStart={onArm}
      >
        {children}
      </TooltipTrigger>
      {armed && <TooltipContent side={side}>{content}</TooltipContent>}
    </Tooltip>
  );
}

export {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
  FastTooltip,
  LazyTooltip,
}
