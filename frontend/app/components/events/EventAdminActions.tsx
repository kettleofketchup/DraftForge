import { CheckCircle2, Clock, Pencil, ShieldAlert, Trash2, Undo2, Users, XCircle } from 'lucide-react';
import { useState } from 'react';

import { ConfirmDialog } from '~/components/ui/dialogs/ConfirmDialog';
import {
  DestructiveButton,
  EditButton,
  PrimaryButton,
  SecondaryButton,
  WarningButton,
} from '~/components/ui/buttons';
import { BrandDropdownMenu, type BrandDropdownAction } from '~/components/ui/brand-dropdown-menu';
import { EventState } from '~/components/events/schemas';
import type { EventType } from '~/components/events/schemas';
import type { useEventActionMutation } from '~/hooks/useEvent';

type EventActions = Pick<
  ReturnType<typeof useEventActionMutation>,
  'openSignups' | 'startRollCall' | 'reopenSignups' | 'cancelEvent' | 'deleteEvent'
>;

interface EventAdminActionsProps {
  event: EventType;
  actions: EventActions;
  onEditClick: () => void;
  onStartRollCallClick: () => void;
  onReopenSignupsClick: () => void;
  onOpenRollCallClick: () => void;
  onDeleteConfirmed: () => void;
}

export function EventAdminActions({
  event,
  actions,
  onEditClick,
  onStartRollCallClick,
  onReopenSignupsClick,
  onOpenRollCallClick,
  onDeleteConfirmed,
}: EventAdminActionsProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const isCancellable = event.state !== EventState.COMPLETED && event.state !== EventState.CANCELLED;

  // Mobile dropdown actions — NO data-testid here (would collide with desktop).
  // Tests reach mobile actions via the parent `event-admin-actions-mobile`.
  const dropdownActions: BrandDropdownAction[] = [
    {
      key: 'edit',
      icon: <Pencil className="h-4 w-4 mr-1.5" />,
      label: 'Edit',
      onClick: onEditClick,
      variant: 'edit',
    },
  ];

  if (event.state === EventState.UPCOMING) {
    dropdownActions.push({
      key: 'open-signups',
      icon: <Users className="h-4 w-4 mr-1.5" />,
      label: 'Open Signups',
      onClick: () => actions.openSignups.mutate(),
      variant: 'primary',
      disabled: actions.openSignups.isPending,
    });
  }

  if (event.state === EventState.SIGNUPS_OPEN) {
    dropdownActions.push({
      key: 'start-rollcall',
      icon: <Clock className="h-4 w-4 mr-1.5" />,
      label: 'Start Roll Call',
      onClick: onStartRollCallClick,
      variant: 'primary',
      disabled: actions.startRollCall.isPending,
    });
  }

  if (event.state === EventState.ROLL_CALL) {
    dropdownActions.push({
      key: 'reopen-signups',
      icon: <Undo2 className="h-4 w-4 mr-1.5" />,
      label: 'Reopen Signups',
      onClick: onReopenSignupsClick,
      // BrandDropdownAction.variant doesn't currently include 'warning' — actual
      // union is 'default' | 'primary' | 'success' | 'destructive'. Use 'destructive'
      // as the closest semantic match; desktop WarningButton carries the on-brand
      // orange treatment.
      variant: 'destructive',
      disabled: actions.reopenSignups.isPending,
    });
    dropdownActions.push({
      key: 'open-rollcall',
      icon: <CheckCircle2 className="h-4 w-4 mr-1.5" />,
      label: 'Open Roll Call',
      onClick: onOpenRollCallClick,
      variant: 'primary',
    });
  }

  if (isCancellable) {
    dropdownActions.push({
      key: 'cancel',
      icon: <XCircle className="h-4 w-4 mr-1.5" />,
      label: 'Cancel',
      onClick: () => actions.cancelEvent.mutate(),
      variant: 'destructive',
      disabled: actions.cancelEvent.isPending,
    });
  }

  dropdownActions.push({
    key: 'delete',
    icon: <Trash2 className="h-4 w-4 mr-1.5" />,
    label: 'Delete',
    onClick: () => setShowDeleteConfirm(true),
    variant: 'destructive',
    disabled: actions.deleteEvent.isPending,
  });

  return (
    <>
      {/* Desktop: button group — owns the canonical testids */}
      <div className="hidden md:flex items-center gap-2">
        <EditButton
          size="sm"
          onClick={onEditClick}
          title="Edit settings"
          aria-label="Edit event settings"
          data-testid="event-edit-btn"
        >
          <Pencil className="h-4 w-4 mr-1.5" />
          Edit
        </EditButton>

        {event.state === EventState.UPCOMING && (
          <SecondaryButton
            color="emerald"
            size="sm"
            onClick={() => actions.openSignups.mutate()}
            disabled={actions.openSignups.isPending}
            data-testid="event-open-signups-btn"
          >
            Open Signups
          </SecondaryButton>
        )}

        {event.state === EventState.SIGNUPS_OPEN && (
          <SecondaryButton
            color="orange"
            size="sm"
            onClick={onStartRollCallClick}
            disabled={actions.startRollCall.isPending}
            data-testid="event-start-rollcall-btn"
          >
            Start Roll Call
          </SecondaryButton>
        )}

        {event.state === EventState.ROLL_CALL && (
          <>
            {/* Reopen is the corrective/secondary action — `depth={false}` flattens it
                so PrimaryButton "Open Roll Call" wins visual primacy per THEMING-GUIDE
                "Button Policy: one primary action per view/section". */}
            <WarningButton
              size="sm"
              depth={false}
              onClick={onReopenSignupsClick}
              loading={actions.reopenSignups.isPending}
              aria-label="Reopen signups for this event"
              data-testid="event-reopen-signups-btn"
            >
              <Undo2 className="h-4 w-4 mr-1.5" />
              Reopen Signups
            </WarningButton>
            <PrimaryButton size="sm" onClick={onOpenRollCallClick} data-testid="event-start-tournament-btn">
              Open Roll Call
            </PrimaryButton>
          </>
        )}

        {isCancellable && (
          <DestructiveButton
            size="sm"
            onClick={() => actions.cancelEvent.mutate()}
            loading={actions.cancelEvent.isPending}
            data-testid="event-cancel-btn"
          >
            <XCircle className="h-4 w-4 mr-1.5" />
            Cancel
          </DestructiveButton>
        )}

        <DestructiveButton
          size="sm"
          onClick={() => setShowDeleteConfirm(true)}
          loading={actions.deleteEvent.isPending}
          data-testid="event-delete-btn"
        >
          <Trash2 className="h-4 w-4 mr-1.5" />
          Delete
        </DestructiveButton>
      </div>

      {/* Mobile: labeled dropdown — testid lives on the wrapper, not on items */}
      <div className="md:hidden">
        <BrandDropdownMenu
          label="Admin"
          icon={<ShieldAlert className="h-4 w-4 mr-1.5" />}
          actions={dropdownActions}
          variant="admin"
          data-testid="event-admin-actions-mobile"
        />
      </div>

      {/* On-brand delete confirmation (replaces window.confirm) */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Event"
        description={`Permanently delete "${event.name}"? This cannot be undone.`}
        confirmLabel="Delete Event"
        variant="destructive"
        onConfirm={onDeleteConfirmed}
      />
    </>
  );
}
