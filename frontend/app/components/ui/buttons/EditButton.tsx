import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export interface EditButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** When true, shows "Done Editing" text; when false, shows children or "Edit" */
  editMode?: boolean;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

/**
 * An edit button with purple theme styling and 3D depth effects.
 * Can toggle between "Edit" and "Done Editing" states.
 *
 * @example
 * ```tsx
 * <EditButton editMode={isEditing} onClick={toggleEditMode}>
 *   Edit Settings
 * </EditButton>
 * ```
 */
const EditButton = React.forwardRef<HTMLButtonElement, EditButtonProps>(
  ({ editMode, children, className, depth = true, ...props }, ref) => {
    return (
      <Button
        ref={ref}
        className={cn(
          depth ? button3DVariants.edit : 'bg-purple-700 text-white hover:bg-purple-600',
          className
        )}
        {...props}
      >
        {editMode !== undefined
          ? editMode
            ? 'Done Editing'
            : children || 'Edit'
          : children}
      </Button>
    );
  }
);

EditButton.displayName = 'EditButton';

export { EditButton };
