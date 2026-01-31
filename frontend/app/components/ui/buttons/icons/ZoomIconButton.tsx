import { Maximize, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

export type ZoomAction = 'in' | 'out' | 'fit' | 'reset';

export interface ZoomIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** The zoom action type */
  action: ZoomAction;
}

const actionConfig: Record<
  ZoomAction,
  { icon: React.ComponentType<{ className?: string }>; label: string }
> = {
  in: { icon: ZoomIn, label: 'Zoom in' },
  out: { icon: ZoomOut, label: 'Zoom out' },
  fit: { icon: Maximize, label: 'Fit to view' },
  reset: { icon: RotateCcw, label: 'Reset zoom' },
};

/**
 * A zoom control icon button with ghost styling.
 * Used for zoom controls in viewers and editors.
 *
 * @example
 * ```tsx
 * <ZoomIconButton action="in" onClick={zoomIn} />
 * <ZoomIconButton action="out" onClick={zoomOut} />
 * <ZoomIconButton action="fit" onClick={fitToView} />
 * <ZoomIconButton action="reset" onClick={resetZoom} />
 * ```
 */
const ZoomIconButton = React.forwardRef<HTMLButtonElement, ZoomIconButtonProps>(
  ({ action, className, ...props }, ref) => {
    const config = actionConfig[action];
    const Icon = config.icon;

    return (
      <Button
        ref={ref}
        variant="ghost"
        size="icon"
        className={cn(className)}
        {...props}
      >
        <Icon className="h-4 w-4" />
        <span className="sr-only">{config.label}</span>
      </Button>
    );
  }
);

ZoomIconButton.displayName = 'ZoomIconButton';

export { ZoomIconButton };
