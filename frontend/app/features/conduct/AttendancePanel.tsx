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
  type AttendanceTableRow,
} from './attendanceColumns';
import { AttendanceTable } from './AttendanceTable';
import { useAttendance, usePutAttendance } from './queries';
import { ReasonDialog } from './ReasonDialog';
import type {
  AttendanceChange,
  AttendanceRow,
  Outcome,
  StaffSettableOutcome,
} from './schemas';
import { WalkInPicker, type WalkInCandidate } from './WalkInPicker';

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
  { outcome: 'excused', label: 'Excuse', testId: 'attendance-bulk-excused' },
];

function walkInRow(user: WalkInCandidate): AttendanceTableRow {
  return {
    member: {
      org_user_pk: null,
      user_pk: user.pk,
      username: user.username ?? '',
      nickname: user.nickname ?? null,
      discordNickname: user.discordNickname,
      guildNickname: user.guildNickname,
      avatarUrl: user.avatarUrl ?? null,
    },
    org_user_pk: null,
    signup_status: null,
    outcome: 'attended',
    source: 'staff',
    committed: false,
    virtual: false,
    finalized: false,
    voided: false,
    flag: null,
    set_by: null,
    reason: '',
    show_rate: 0,
    status: 'new',
    key: `walkin-${user.pk}`,
    provisional: true,
  };
}

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

  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [changes, setChanges] = useState<
    ReadonlyMap<number, StaffSettableOutcome>
  >(new Map());
  const [walkIns, setWalkIns] = useState<WalkInCandidate[]>([]);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [walkInOpen, setWalkInOpen] = useState(false);

  useEffect(() => {
    if (isError)
      log.error('attendance failed to load', { orgId, eventId, error });
  }, [isError, error, orgId, eventId]);

  const original = useMemo(() => {
    const byPk = new Map<number, AttendanceRow>();
    for (const r of data?.rows ?? []) {
      if (r.org_user_pk != null) byPk.set(r.org_user_pk, r);
    }
    return byPk;
  }, [data]);

  const rows = useMemo<AttendanceTableRow[]>(
    () => [
      ...(data?.rows ?? []).map(toAttendanceTableRow),
      ...walkIns.map(walkInRow),
    ],
    [data, walkIns],
  );

  const excludeUserPks = useMemo(
    () => new Set(rows.map((r) => r.member.user_pk)),
    [rows],
  );

  const applyChange = useCallback(
    (
      next: Map<number, StaffSettableOutcome>,
      pk: number,
      outcome: StaffSettableOutcome,
    ) => {
      const row = original.get(pk);
      if (row && !row.virtual && row.outcome === outcome) next.delete(pk);
      else next.set(pk, outcome);
    },
    [original],
  );

  const onOutcomeChange = useCallback(
    (pk: number, outcome: StaffSettableOutcome) =>
      setChanges((prev) => {
        const next = new Map(prev);
        applyChange(next, pk, outcome);
        return next;
      }),
    [applyChange],
  );

  const onBulk = (outcome: StaffSettableOutcome) =>
    setChanges((prev) => {
      const next = new Map(prev);
      for (const pk of selected) applyChange(next, pk, outcome);
      return next;
    });

  const onToggle = useCallback(
    (pk: number, checked: boolean) =>
      setSelected((prev) => {
        const next = new Set(prev);
        if (checked) next.add(pk);
        else next.delete(pk);
        return next;
      }),
    [],
  );

  const onToggleAll = useCallback(
    (checked: boolean) =>
      setSelected(checked ? new Set(original.keys()) : new Set()),
    [original],
  );

  const outcomeFor = useCallback(
    (row: AttendanceTableRow): Outcome =>
      row.provisional
        ? 'attended'
        : ((row.org_user_pk != null
            ? changes.get(row.org_user_pk)
            : undefined) ?? row.outcome),
    [changes],
  );

  const onRemoveWalkIn = useCallback(
    (userPk: number) =>
      setWalkIns((prev) => prev.filter((u) => u.pk !== userPk)),
    [],
  );

  const onPickWalkIn = (user: WalkInCandidate) => {
    setWalkIns((prev) => [...prev, user]);
    setWalkInOpen(false);
  };

  const reset = () => {
    setChanges(new Map());
    setSelected(new Set());
    setWalkIns([]);
  };

  const pendingChanges: AttendanceChange[] = [
    ...[...changes].map(([org_user_pk, outcome]) => ({ org_user_pk, outcome })),
    ...walkIns.map((u) => ({ user_pk: u.pk, outcome: 'attended' as const })),
  ];

  const onConfirm = (reason: string) => {
    put.mutate(
      { changes: pendingChanges, reason },
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
                  ? 'Reopen and complete the event to record attendance.'
                  : 'Attendance cannot be edited for this event.')}
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
          <div className="flex flex-wrap items-center gap-2">
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
          <div className="flex flex-wrap items-center justify-end gap-2">
            <SecondaryButton
              data-testid="attendance-discard"
              disabled={pendingChanges.length === 0 || put.isPending}
              onClick={reset}
              className="min-h-11 sm:min-h-9"
            >
              Discard
            </SecondaryButton>
            <PrimaryButton
              data-testid="attendance-save"
              disabled={pendingChanges.length === 0 || put.isPending}
              onClick={() => setReasonOpen(true)}
              className="min-h-11 sm:min-h-9"
            >
              Save
              {pendingChanges.length > 0 ? ` (${pendingChanges.length})` : ''}
            </PrimaryButton>
          </div>
        )}
      </CardContent>
      <ReasonDialog
        open={reasonOpen}
        onOpenChange={setReasonOpen}
        changeCount={pendingChanges.length}
        pending={put.isPending}
        onConfirm={onConfirm}
      />
      <WalkInPicker
        open={walkInOpen}
        onOpenChange={setWalkInOpen}
        orgId={orgId}
        access={access}
        excludeUserPks={excludeUserPks}
        onPick={onPickWalkIn}
      />
    </Card>
  );
}
