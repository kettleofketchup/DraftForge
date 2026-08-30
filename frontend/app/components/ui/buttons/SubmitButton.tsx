import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandButtonVariants } from './styles';

export interface SubmitButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'type'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Text to display when loading (defaults to "Submitting...") */
  loadingText?: string;
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
}

/**
 * A submit button with brand gradient styling and a soft-shadow lift for form submissions.
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
          // min-h-11 keeps submit/approve actions the same 44px height as
          // ConfirmButton/CancelButton so dialog footers line up.
          'min-h-11',
          depth ? brandButtonVariants.success : 'bg-green-600 text-white hover:bg-green-500',
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
