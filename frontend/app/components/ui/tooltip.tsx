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
 * Lazy tooltip - only mounts the full Radix tooltip structure on hover.
 * Use this for performance-critical lists where many tooltips are rendered.
 *
 * On initial render, only renders the children with a title attribute as fallback.
 * On hover, mounts the full Radix tooltip for nice styling.
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

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider, FastTooltip }
