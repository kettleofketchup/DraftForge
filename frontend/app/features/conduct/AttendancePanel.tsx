import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { EventState } from '~/components/events/schemas';
import { Alert, AlertDescription, AlertTitle } from '~/components/ui/alert';
import {
  DestructiveButton,
  PrimaryButton,
  SecondaryButton,
} from '~/components/ui/buttons';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import { Skeleton } from '~/components/ui/skeleton';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  toAttendanceTableRow,
  walkInTableRow,
  type AttendanceTableRow,
} from './attendanceColumns';
import {
  addWalkIn,
  draftChanges,
  draftOutcome,
  EMPTY_DRAFT,
  removeWalkIn,
  setOutcomes,
  type AttendanceDraft,
  type WalkIn,
} from './attendanceDraft';
import { AttendanceTable } from './AttendanceTable';
import { useAttendance, usePutAttendance } from './queries';
import { ReasonDialog } from './ReasonDialog';
import type { Outcome, StaffSettableOutcome } from './schemas';
import { WalkInPicker } from './WalkInPicker';

const log = getLogger('AttendancePanel');

const BULK_ACTIONS: {
  outcome: StaffSettableOutcome;
  label: string;
  testId: string;
}[] = [
  {
    outcome: 'no_show',
    label: 'Mark no-show',
    testId: 'attendance-bulk-no-show',
  },
  {
    outcome: 'attended',
    label: 'Mark attended',
    testId: 'attendance-bulk-attended',
  },
  {
    outcome: 'late_cancel',
    label: 'Late cancel',
    testId: 'attendance-bulk-late-cancel',
  },
  { outcome: 'excused', label: 'Excuse', testId: 'attendance-bulk-excused' },
];

export interface AttendancePanelProps {
  orgId: number;
  eventId: number;
  eventState: string;
  access: OrgFeatureAccess;
  enabled: boolean;
}

export function AttendancePanel({
  orgId,
  eventId,
  eventState,
  access,
  enabled,
}: AttendancePanelProps) {
  const { data, isPending, isError, error } = useAttendance(
    orgId,
    access,
    eventId,
    enabled,
  );
  const put = usePutAttendance(orgId, access, eventId);

  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [draft, setDraft] = useState<AttendanceDraft>(EMPTY_DRAFT);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [walkInOpen, setWalkInOpen] = useState(false);

  useEffect(() => {
    if (isError)
      log.error('attendance failed to load', { orgId, eventId, error });
  }, [isError, error, orgId, eventId]);

  const serverRows = useMemo(() => data?.rows ?? [], [data]);

  const rows = useMemo<AttendanceTableRow[]>(() => {
    const userPks = new Set(serverRows.map((r) => r.member.user_pk));
    return [
      ...serverRows.map(toAttendanceTableRow),
      ...draft.walkIns
        .filter((w) => !userPks.has(w.user_pk))
        .map(walkInTableRow),
    ];
  }, [serverRows, draft.walkIns]);

  const excludeUserPks = useMemo(
    () => new Set(rows.map((r) => r.member.user_pk)),
    [rows],
  );

  const changes = useMemo(
    () => draftChanges(draft, serverRows),
    [draft, serverRows],
  );

  const onOutcomeChange = useCallback(
    (key: string, outcome: StaffSettableOutcome) =>
      setDraft((prev) => setOutcomes(prev, serverRows, [key], outcome)),
    [serverRows],
  );

  const onToggle = useCallback(
    (key: string, checked: boolean) =>
      setSelected((prev) => {
        const next = new Set(prev);
        if (checked) next.add(key);
        else next.delete(key);
        return next;
      }),
    [],
  );

  const onToggleAll = useCallback(
    (checked: boolean) =>
      setSelected(
        checked
          ? new Set(rows.filter((r) => !r.provisional).map((r) => r.key))
          : new Set(),
      ),
    [rows],
  );

  const outcomeFor = useCallback(
    (row: AttendanceTableRow): Outcome =>
      row.provisional ? 'attended' : draftOutcome(draft, row),
    [draft],
  );

  const onRemoveWalkIn = useCallback(
    (userPk: number) => setDraft((prev) => removeWalkIn(prev, userPk)),
    [],
  );

  const onPickWalkIn = (walkIn: WalkIn) => {
    setDraft((prev) => addWalkIn(prev, walkIn));
    setWalkInOpen(false);
  };

  const onBulk = (outcome: StaffSettableOutcome) =>
    setDraft((prev) => setOutcomes(prev, serverRows, selected, outcome));

  const reset = () => {
    setDraft(EMPTY_DRAFT);
    setSelected(new Set());
  };

  const onConfirm = (reason: string) => {
    put.mutate(
      { changes, reason },
      {
        onSuccess: () => {
          reset();
          setReasonOpen(false);
          toast.success('Attendance saved');
        },
        onError: (err) => {
          log.error('attendance save failed', { orgId, eventId, error: err });
          toast.error(extractApiError(err) ?? 'Could not save attendance');
        },
      },
    );
  };

  const cancelled = (data?.state ?? eventState) === EventState.CANCELLED;
  const editable = data?.editable === true;

  return (
    <Card data-testid="attendance-panel">
      <CardHeader>
        <CardTitle>Attendance</CardTitle>
        <CardDescription>
          Expected members default to attended when the event completes. Mark
          anyone who did not show.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {isPending && enabled && <Skeleton className="h-32 w-full" />}
        {isError && (
          <p className="text-sm text-destructive">
            {extractApiError(error) ?? 'Failed to load attendance'}
          </p>
        )}
        {data && !editable && (
          <Alert data-testid="attendance-readonly">
            <AlertTitle>
              {cancelled ? 'Voided, event cancelled' : 'Read-only'}
            </AlertTitle>
            <AlertDescription>
              {data.editable_reason ??
                (cancelled
                  ? 'Attendance on a cancelled event does not count.'
                  : 'Attendance was not tracked for this event.')}
            </AlertDescription>
          </Alert>
        )}
        {data && editable && data.finalized_at && (
          <Alert data-testid="attendance-finalized">
            <AlertTitle>Finalized</AlertTitle>
            <AlertDescription>
              Edits are audited and count immediately.
            </AlertDescription>
          </Alert>
        )}
        {data && editable && (
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            {BULK_ACTIONS.map((action) => {
              const Button =
                action.outcome === 'no_show'
                  ? DestructiveButton
                  : SecondaryButton;
              return (
                <Button
                  key={action.outcome}
                  data-testid={action.testId}
                  disabled={selected.size === 0}
                  onClick={() => onBulk(action.outcome)}
                  className="min-h-11 sm:min-h-9"
                >
                  {action.label}
                </Button>
              );
            })}
            <SecondaryButton
              data-testid="attendance-add-walkin"
              onClick={() => setWalkInOpen(true)}
              className="min-h-11 sm:min-h-9"
            >
              Add walk-in
            </SecondaryButton>
          </div>
        )}
        {data && (
          <AttendanceTable
            rows={rows}
            editable={editable}
            selected={selected}
            onToggle={onToggle}
            onToggleAll={onToggleAll}
            outcomeFor={outcomeFor}
            onOutcomeChange={onOutcomeChange}
            onRemoveWalkIn={onRemoveWalkIn}
          />
        )}
        {data && editable && (
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <SecondaryButton
              data-testid="attendance-discard"
              disabled={changes.length === 0 || put.isPending}
              onClick={reset}
              className="min-h-11 sm:min-h-9"
            >
              Discard
            </SecondaryButton>
            <PrimaryButton
              data-testid="attendance-save"
              disabled={changes.length === 0 || put.isPending}
              onClick={() => setReasonOpen(true)}
              className="min-h-11 sm:min-h-9"
            >
              Save{changes.length > 0 ? ` (${changes.length})` : ''}
            </PrimaryButton>
          </div>
        )}
      </CardContent>
      <ReasonDialog
        open={reasonOpen}
        onOpenChange={setReasonOpen}
        changeCount={changes.length}
        pending={put.isPending}
        onConfirm={onConfirm}
      />
      <WalkInPicker
        open={walkInOpen}
        onOpenChange={setWalkInOpen}
        orgId={orgId}
        eventId={eventId}
        access={access}
        excludeUserPks={excludeUserPks}
        onPick={onPickWalkIn}
      />
    </Card>
  );
}
