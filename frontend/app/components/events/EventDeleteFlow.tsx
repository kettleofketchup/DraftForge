import { XCircle } from 'lucide-react';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { toast } from 'sonner';

import {
  EventSignupRecordsConflict,
  type DeleteEventOptions,
} from '~/components/api/eventsAPI';
import type { EventType } from '~/components/events/schemas';
import { EventState } from '~/components/events/schemas';
import { WarningButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs/ConfirmDialog';
import { DeleteDialog } from '~/components/ui/dialogs/DeleteDialog';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

const log = getLogger('EventDeleteFlow');

const CANCELLABLE_STATES: ReadonlySet<string> = new Set([
  EventState.UPCOMING,
  EventState.SIGNUPS_OPEN,
  EventState.ROLL_CALL,
]);

export function isEventCancellable(event: Pick<EventType, 'state'>): boolean {
  return CANCELLABLE_STATES.has(event.state);
}

export interface EventDeleteFlowProps {
  event: EventType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isOrganizationAdmin: boolean;
  isPending: boolean;
  onDelete: (options?: DeleteEventOptions) => Promise<void>;
  onCancel: () => Promise<void>;
  onDeleted: () => void;
}

function statusOf(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status;
}

// Keep this composed cancellation action's Enter activation local.
function keepEnterLocal(e: KeyboardEvent<HTMLButtonElement>) {
  if (e.key === 'Enter') e.stopPropagation();
}

export function EventDeleteFlow({
  event,
  open,
  onOpenChange,
  isOrganizationAdmin,
  isPending,
  onDelete,
  onCancel,
  onDeleted,
}: EventDeleteFlowProps) {
  const [recordCount, setRecordCount] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const pendingConflict = useRef<number | null>(null);
  const inFlight = useRef(false);
  const generation = useRef(0);
  const displayedEventId = useRef(event.id);
  const busy = isPending || cancelling || deleting;
  const cancellable = isEventCancellable(event);

  useEffect(() => {
    if (displayedEventId.current !== event.id) {
      displayedEventId.current = event.id;
      onOpenChange(false);
    }
  }, [event.id, onOpenChange]);

  useEffect(() => {
    generation.current += 1;
    inFlight.current = false;
    pendingConflict.current = null;
    setRecordCount(null);
    setDeleting(false);
    setCancelling(false);
    return () => {
      generation.current += 1;
    };
  }, [event.id]);

  // One lifecycle request at a time; a result for a previous event is dropped.
  const run = async (
    setBusy: (value: boolean) => void,
    request: (isCurrent: () => boolean) => Promise<void>,
  ) => {
    if (inFlight.current || isPending) return;
    inFlight.current = true;
    const started = generation.current;
    const isCurrent = () => generation.current === started;
    setBusy(true);
    try {
      await request(isCurrent);
    } finally {
      if (isCurrent()) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  };

  const reportFailure = (action: string, err: unknown) => {
    const status = statusOf(err);
    const context = { eventId: event.id, status };
    if (status != null && status >= 400 && status < 500) {
      log.warn(action, context);
    } else {
      log.error(action, context);
    }
    toast.error(
      extractApiError(err) ??
        (status === 403
          ? 'You no longer have permission to delete this event.'
          : 'Could not complete that action. Please try again.'),
    );
  };

  const closeAll = () => {
    if (displayedEventId.current !== event.id) return;
    pendingConflict.current = null;
    setRecordCount(null);
    onOpenChange(false);
  };

  const handleFirstOpenChange = (next: boolean) => {
    if (displayedEventId.current !== event.id) return;
    onOpenChange(next);
    if (!next && pendingConflict.current !== null) {
      setRecordCount(pendingConflict.current);
      pendingConflict.current = null;
    }
  };

  const deleteUnconfirmed = () =>
    run(setDeleting, async (isCurrent) => {
      try {
        await onDelete();
        if (isCurrent()) onDeleted();
      } catch (err) {
        if (!isCurrent()) return;
        if (err instanceof EventSignupRecordsConflict) {
          pendingConflict.current = err.count;
          return;
        }
        reportFailure('event_delete_failed', err);
      }
    });

  const deleteConfirmed = () =>
    run(setDeleting, async (isCurrent) => {
      try {
        await onDelete({ confirm: true });
        if (!isCurrent()) return;
        setRecordCount(null);
        onDeleted();
      } catch (err) {
        if (isCurrent()) reportFailure('event_delete_confirmed_failed', err);
      }
    });

  const cancelInstead = () =>
    run(setCancelling, async (isCurrent) => {
      try {
        await onCancel();
        if (!isCurrent()) return;
        toast.success('Event cancelled');
        closeAll();
      } catch (err) {
        if (isCurrent()) reportFailure('event_cancel_failed', err);
      }
    });

  const cancelAlternative = cancellable ? (
    <WarningButton
      type="button"
      size="sm"
      depth={false}
      onClick={() => void cancelInstead()}
      onKeyDown={keepEnterLocal}
      disabled={busy}
      loading={cancelling}
      data-testid="event-delete-cancel-instead"
    >
      <XCircle className="h-4 w-4 mr-1.5" />
      Cancel event instead
    </WarningButton>
  ) : null;

  const recordText =
    recordCount === null ? null : (
      <div className="space-y-2" data-testid="event-delete-record-warning">
        <div>
          This event has{' '}
          <strong data-testid="event-delete-record-count">{recordCount}</strong>{' '}
          historical signup {recordCount === 1 ? 'record' : 'records'}.
        </div>
        <div>
          {isOrganizationAdmin
            ? 'Cancel to keep the event and its sign-ups, or permanently delete its live event and sign-ups. Historical records will remain.'
            : 'Only an organization administrator can permanently delete it. Historical records are kept either way.'}
        </div>
        {cancelAlternative}
      </div>
    );

  return (
    <>
      {recordCount === null && (
        <ConfirmDialog
          open={open && recordCount === null}
          onOpenChange={handleFirstOpenChange}
          title="Delete Event"
          description={
            <div className="space-y-2">
              <div>Permanently delete “{event.name}”?</div>
              <div>
                Active sign-ups: {event.signup_count}. Historical signup records
                are retained.
              </div>
              {cancellable && (
                <div>
                  Cancel the event instead to keep its sign-ups and event page.
                </div>
              )}
            </div>
          }
          bodyContent={cancelAlternative ?? undefined}
          confirmLabel="Delete event"
          cancelLabel="Keep event"
          variant="destructive"
          isLoading={busy}
          onConfirm={deleteUnconfirmed}
          contentTestId="event-delete-dialog"
          confirmTestId="event-delete-initial-confirm"
          cancelTestId="event-delete-keep"
        />
      )}

      {recordCount !== null && isOrganizationAdmin && (
        <DeleteDialog
          open
          onOpenChange={(next) => {
            if (!next) closeAll();
          }}
          entityKind="Event"
          entityName={event.name}
          description={recordText}
          isLoading={busy}
          onConfirm={deleteConfirmed}
          contentTestId="event-delete-record-dialog"
          inputTestId="event-delete-confirm-input"
          confirmTestId="event-delete-record-confirm"
          cancelTestId="event-delete-record-keep"
        />
      )}

      {recordCount !== null && !isOrganizationAdmin && (
        <ConfirmDialog
          open
          onOpenChange={(next) => {
            if (!next) closeAll();
          }}
          title="This event has signup records"
          description={recordText}
          confirmLabel="Keep event"
          cancelLabel="Close"
          variant="warning"
          isLoading={busy}
          onConfirm={() => undefined}
          contentTestId="event-delete-record-dialog"
          confirmTestId="event-delete-record-keep"
          cancelTestId="event-delete-record-close"
        />
      )}
    </>
  );
}
