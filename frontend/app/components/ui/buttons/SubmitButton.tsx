import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export interface SubmitButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'type'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Text to display when loading (defaults to "Submitting...") */
  loadingText?: string;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

/**
 * A submit button with green theme styling and 3D depth effects for form submissions.
 * Automatically sets type="submit" and handles loading states.
 *
 * @example
 * ```tsx
 * <SubmitButton loading={isSubmitting} loadingText="Saving...">
 *   Save Changes
 * </SubmitButton>
 * ```
 */
const SubmitButton = React.forwardRef<HTMLButtonElement, SubmitButtonProps>(
  (
    {
      loading = false,
      loadingText = 'Submitting...',
      disabled,
      children,
      className,
      depth = true,
      ...props
    },
    ref
  ) => {
    return (
      <Button
        ref={ref}
        type="submit"
        disabled={disabled || loading}
        className={cn(
          depth ? button3DVariants.success : 'bg-green-600 text-white hover:bg-green-500',
          className
        )}
        {...props}
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            {loadingText}
          </>
        ) : (
          children
        )}
      </Button>
    );
  }
);

SubmitButton.displayName = 'SubmitButton';

export { SubmitButton };
