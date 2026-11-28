import { useNavigate, useParams } from 'react-router';
import { getEvent } from '~/components/api/api';
import { generateMeta } from '~/lib/seo';
import type { EventSSR } from '~/lib/ssr-types';
import type { Route } from './+types/rollcall';

export async function loader({ params }: Route.LoaderArgs) {
  const { fetchSSR } = await import('~/lib/ssr.server');
  const event = await fetchSSR<EventSSR>(`/events/${params.eventId}/ssr/`);
  return { event };
}

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
  const id = params.eventId ? parseInt(params.eventId, 10) : null;
  if (!id) return { event: null };
  try {
    const event = await getEvent(id);
    return { event };
  } catch {
    return { event: null };
  }
}

export function meta({ data }: Route.MetaArgs) {
  const event = data?.event;
  return generateMeta({
    title: event?.name ? `Roll Call - ${event.name}` : 'Roll Call',
    description: 'Confirm player attendance before starting the tournament',
  });
}

import { useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  RotateCcw,
  Undo2,
  Users,
  XCircle,
} from 'lucide-react';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { EventStateBadge, MmrApprovalModal } from '~/components/events';
import { OverrideWarningDialog } from '~/components/events/OverrideWarningDialog';
import {
  isApprovableSignup,
  moveRollCallFocus,
  resolveRollCallFocus,
  rollCallFocusAfterAction,
  rollCallRowActions,
  splitRollCallRows,
} from '~/components/events/rollCallNavigation';
import type { EventSignupType } from '~/components/events/schemas';
import { EventState, SignupStatus } from '~/components/events/schemas';
import { SignupInLineSince } from '~/components/events/SignupInLineSince';
import {
  canRestoreSignup,
  canVoidWithdrawal,
} from '~/components/events/signupPartitions';
import { StaffReasonDialog } from '~/components/events/StaffReasonDialog';
import {
  staffReasonMode,
  type StaffSignupAction,
} from '~/components/events/staffReasonPolicy';
import { startTournamentErrorMessage } from '~/components/events/startTournamentError';
import { useSignupOverride } from '~/components/events/useSignupOverride';
import { useStaffAction } from '~/components/events/useStaffAction';
import { toGameType } from '~/components/game/constants';
import { useOrganization } from '~/components/organization';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import {
  brandDialogPanel,
  DestructiveButton,
  PrimaryButton,
  SecondaryButton,
} from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { EntityBreadcrumb } from '~/components/ui/entity-breadcrumb';
import { Kbd } from '~/components/ui/kbd';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { UserStrip } from '~/components/user';
import { DisplayName } from '~/components/user/avatar';
import {
  ConductBadge,
  useEventConduct,
  type ForecastMember,
} from '~/features/conduct';
import {
  removeFeatureQueries,
  useOrgFeatureAccess,
} from '~/features/org-features';
import {
  useEvent,
  useEventActionMutation,
  useEventSignupUsers,
  useOptimisticEventSignups,
  useSignupActionMutations,
} from '~/hooks/useEvent';
import { useProvideGameType } from '~/hooks/useGameType';
import { useMemberAccess } from '~/hooks/useMemberAccess';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';

export default function RollCallPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const navigate = useNavigate();
  const id = eventId ? parseInt(eventId, 10) : null;

  const { data: event, isLoading } = useEvent(id);
  const {
    data: serverSignups,
    signups,
    pendingIds,
  } = useOptimisticEventSignups(id, event?.state);
  useEventSignupUsers(
    serverSignups,
    event?.organization ?? null,
    toGameType(event?.game_type),
  );
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);
  const { fire, dialogProps: overrideDialogProps } =
    useSignupOverride(signupActions);
  const currentUserId = useUserStore((state) => state.currentUser?.pk);
  const {
    dispatch,
    dialogProps,
    isOpen: staffActionIsOpen,
  } = useStaffAction({
    policy: event?.staff_reason_policy,
    currentUserId,
  });
  const reasonMode = (
    action: StaffSignupAction,
    signup: EventSignupType | null,
  ) =>
    staffReasonMode(event?.staff_reason_policy, action, {
      fromStatus: signup?.status,
      isSelf: signup?.user === currentUserId,
    });

  const { organization: eventOrg, refetch: refetchEventOrg } = useOrganization(
    event?.organization ?? undefined,
  );
  const queryClient = useQueryClient();
  const eventOrgPk = event?.organization ?? null;
  const onMemberViewerChange = useCallback(() => {
    if (!eventOrgPk) return;
    removeFeatureQueries(queryClient, eventOrgPk);
    refetchEventOrg();
  }, [eventOrgPk, queryClient, refetchEventOrg]);
  useMemberAccess(eventOrg, onMemberViewerChange);
  const isAdmin = event?.user_can_manage ?? false;
  const eventOrgAccess = useOrgFeatureAccess(eventOrg ?? undefined);
  const { memberFor: conductMemberFor } = useEventConduct(
    event,
    eventOrg,
    eventOrgAccess,
  );

  useProvideGameType(event ? toGameType(event.game_type) : null);

  const [showStartConfirm, setShowStartConfirm] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);
  const [approvalSignup, setApprovalSignup] = useState<EventSignupType | null>(
    null,
  );
  const [confirmSignup, setConfirmSignup] = useState<EventSignupType | null>(
    null,
  );
  const [rejectSignup, setRejectSignup] = useState<EventSignupType | null>(
    null,
  );
  const [cancelSignup, setCancelSignup] = useState<EventSignupType | null>(
    null,
  );

  const userPks = useMemo(() => signups.map((s) => s.user), [signups]);
  const resolvedUsers = useResolvedUsers(userPks);
  const userMap = useMemo(
    () => new Map(resolvedUsers.map((u) => [u.pk, u])),
    [resolvedUsers],
  );

  const rows = useMemo(() => splitRollCallRows(signups), [signups]);
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const activeId = resolveRollCallFocus(rows, focusedId);
  const scrollOnFocus = useRef(false);

  // Read through a ref so row callbacks keep one identity and memoised
  // rows only re-render when their own signup changes.
  const rowsRef = useRef(rows);
  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);
  const nextFocusFrom = useCallback(
    (signup: EventSignupType) =>
      rollCallFocusAfterAction(rowsRef.current, signup.id),
    [],
  );

  const handleRestore = useCallback(
    async (signup: EventSignupType) => {
      const next = nextFocusFrom(signup);
      if (
        await dispatch(
          'reinstate',
          signup,
          fire('reinstate', signup.id, DisplayName(signup)),
          {
            errorLabel: `restore ${DisplayName(signup)}`,
          },
        )
      ) {
        setFocusedId(next);
      }
    },
    [dispatch, fire, nextFocusFrom],
  );
  const handleVoid = useCallback(
    async (signup: EventSignupType) => {
      const next = nextFocusFrom(signup);
      if (
        await dispatch(
          'void_withdrawal',
          signup,
          fire('void_withdrawal', signup.id, DisplayName(signup)),
          {
            title: 'Void withdrawal',
            actionLabel: 'Void withdrawal',
            errorLabel: `void withdrawal for ${DisplayName(signup)}`,
          },
        )
      ) {
        setFocusedId(next);
      }
    },
    [dispatch, fire, nextFocusFrom],
  );

  const minPlayers = event?.min_players;
  const canStart =
    isAdmin &&
    (!minPlayers || rows.confirmed.length >= minPlayers) &&
    !actions.startTournament.isPending;

  // ↑/↓ (or j/k) select a row; 1 runs its primary action, 2 removes it;
  // S opens Start Tournament. Dialogs keep their own Enter/Backspace keys.
  useEffect(() => {
    if (!isAdmin) return;
    const handler = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        target?.isContentEditable
      )
        return;
      if (
        approvalSignup ||
        confirmSignup ||
        rejectSignup ||
        cancelSignup ||
        staffActionIsOpen ||
        overrideDialogProps.open ||
        showStartConfirm
      )
        return;

      const move = (next: number | null) => {
        e.preventDefault();
        scrollOnFocus.current = true;
        setFocusedId(next);
      };
      const active = rows.ordered.find((s) => s.id === activeId) ?? null;

      switch (e.key) {
        case 'ArrowDown':
        case 'j':
          return move(moveRollCallFocus(rows, activeId, 1));
        case 'ArrowUp':
        case 'k':
          return move(moveRollCallFocus(rows, activeId, -1));
        case 'Home':
          return move(rows.ordered[0]?.id ?? null);
        case 'End':
          return move(rows.ordered.at(-1)?.id ?? null);
        case 's':
        case 'S':
          if (!canStart) return;
          e.preventDefault();
          setShowStartConfirm(true);
          return;
      }

      if (!active || pendingIds.has(active.id)) return;
      const { primary, remove } = rollCallRowActions(active.status);
      if (e.key === '1' && primary) {
        e.preventDefault();
        if (primary === 'confirm') setConfirmSignup(active);
        else if (primary === 'approve') setApprovalSignup(active);
        else handleRestore(active);
      } else if (e.key === '2' && remove) {
        e.preventDefault();
        if (remove === 'reject') setRejectSignup(active);
        else setCancelSignup(active);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [
    isAdmin,
    rows,
    activeId,
    canStart,
    pendingIds,
    handleRestore,
    approvalSignup,
    confirmSignup,
    rejectSignup,
    cancelSignup,
    staffActionIsOpen,
    overrideDialogProps.open,
    showStartConfirm,
  ]);

  useEffect(() => {
    if (!scrollOnFocus.current || activeId === null) return;
    scrollOnFocus.current = false;
    document
      .querySelector(`[data-rollcall-row="${activeId}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [activeId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="text-center py-12 text-destructive">Event not found</div>
    );
  }

  if (event.state !== EventState.ROLL_CALL && !isNavigating) {
    return (
      <div className="container mx-auto py-6 px-4">
        <div className="text-center py-12">
          <p
            data-testid="rollcall-not-active"
            className="text-muted-foreground mb-4"
          >
            This event is not in roll call mode.
          </p>
          <Button
            data-testid="rollcall-back-btn"
            variant="outline"
            onClick={() => navigate(`/events/${eventId}`)}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Event
          </Button>
        </div>
      </div>
    );
  }

  const { confirmed, awaiting: approved, others } = rows;
  const totalReady = confirmed.length;

  const renderStrip = (signup: EventSignupType) => (
    <SignupStrip
      key={signup.id}
      signup={signup}
      userMap={userMap}
      isAdmin={isAdmin}
      conductMember={conductMemberFor(signup.user)}
      leaguePk={event.tournament_league ?? null}
      eventTimezone={event.timezone}
      pending={pendingIds.has(signup.id)}
      focused={isAdmin && signup.id === activeId}
      onSelect={setFocusedId}
      onRequestApproval={setApprovalSignup}
      onRequestConfirm={setConfirmSignup}
      onRequestReject={setRejectSignup}
      onRequestCancel={setCancelSignup}
      onRequestRestore={handleRestore}
      onRequestVoid={handleVoid}
    />
  );

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      <EntityBreadcrumb
        segments={[
          ...(eventOrg
            ? [
                {
                  type: 'organization' as const,
                  label: eventOrg.name,
                  href: `/organizations/${eventOrg.pk}`,
                },
              ]
            : []),
          {
            type: 'event' as const,
            label: event.name,
            href: `/events/${eventId}`,
          },
        ]}
        currentLabel="Roll Call"
      />
      <div className="flex flex-col gap-6 rounded-lg border border-border bg-base-200/50 p-4 md:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:justify-between gap-3">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => navigate(`/events/${eventId}`)}
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <h1
                data-testid="rollcall-heading"
                className="text-xl md:text-2xl font-bold"
              >
                Roll Call
              </h1>
              <EventStateBadge state={event.state} />
            </div>
            <p className="text-sm text-muted-foreground ml-11">{event.name}</p>
          </div>

          {/* Summary + Start Tournament */}
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-sm">
                <Users className="h-3.5 w-3.5 mr-1" />
                {totalReady} confirmed
                {minPlayers && ` / ${minPlayers} needed`}
              </Badge>
              {approved.length > 0 && (
                <Badge variant="secondary" className="text-sm">
                  {approved.length} awaiting
                </Badge>
              )}
            </div>
            {isAdmin && (
              <PrimaryButton
                size="sm"
                disabled={!canStart}
                onClick={() => setShowStartConfirm(true)}
                data-testid="rollcall-start-btn"
              >
                {actions.startTournament.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                )}
                Start Tournament ({totalReady} players)
              </PrimaryButton>
            )}
          </div>
        </div>

        {isAdmin && signups.length > 0 && (
          <p
            data-testid="rollcall-keyboard-legend"
            className="hidden sm:flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"
          >
            <span>
              <Kbd>↑</Kbd> <Kbd>↓</Kbd> select
            </span>
            <span>
              <Kbd>1</Kbd> confirm / approve / restore
            </span>
            <span>
              <Kbd>2</Kbd> remove
            </span>
            <span>
              <Kbd>↵</Kbd> accept dialog
            </span>
            <span>
              <Kbd>S</Kbd> start tournament
            </span>
          </p>
        )}

        {/* Confirmed players */}
        {confirmed.length > 0 && (
          <div>
            <h3
              data-testid="rollcall-confirmed-section"
              className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider"
            >
              Confirmed ({confirmed.length})
            </h3>
            <div className="space-y-1.5">{confirmed.map(renderStrip)}</div>
          </div>
        )}

        {/* Approved but not confirmed */}
        {approved.length > 0 && (
          <div>
            <h3
              data-testid="rollcall-awaiting-section"
              className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider"
            >
              Awaiting Confirmation ({approved.length})
            </h3>
            <div className="space-y-1.5">{approved.map(renderStrip)}</div>
          </div>
        )}

        {/* Other statuses */}
        {others.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
              Other ({others.length})
            </h3>
            <div className="space-y-1.5">{others.map(renderStrip)}</div>
          </div>
        )}

        {signups.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Users className="w-12 h-12 mb-3 opacity-50" />
            <p>No signups to review</p>
          </div>
        )}
      </div>

      <MmrApprovalModal
        signup={approvalSignup}
        reasonMode={reasonMode('approve', approvalSignup)}
        open={!!approvalSignup}
        onOpenChange={(open) => {
          if (!open) setApprovalSignup(null);
        }}
        onApprove={async (signupId, mmr, reason) => {
          const target = approvalSignup;
          if (!target) return false;
          const next = nextFocusFrom(target);
          const success = await dispatch(
            'approve',
            target,
            (r) =>
              signupActions.approve.mutateAsync({
                id: signupId,
                mmr,
                reason: r,
              }),
            { reason },
          );
          if (success) {
            setFocusedId(next);
            setApprovalSignup(null);
          }
          return success;
        }}
      />

      <StaffReasonDialog {...dialogProps} />
      <OverrideWarningDialog
        {...overrideDialogProps}
        organization={eventOrg ?? null}
      />

      {/* Per-row Confirm (approved → confirmed) */}
      <StaffReasonDialog
        key={`confirm-${confirmSignup?.id}`}
        required={reasonMode('confirm', confirmSignup) === 'required'}
        submitting={false}
        contentTestId="rollcall-confirm-dialog"
        open={!!confirmSignup}
        onOpenChange={(open) => {
          if (!open) setConfirmSignup(null);
        }}
        title="Confirm attendance"
        description={
          confirmSignup ? (
            <div className="flex flex-col gap-3">
              {(() => {
                const stripUser = userMap.get(confirmSignup.user);
                return stripUser ? (
                  <UserStrip
                    user={stripUser}
                    showBorder={false}
                    organizationId={event?.organization ?? undefined}
                    className={brandDialogPanel}
                    data-testid="rollcall-confirm-user-strip"
                  />
                ) : null;
              })()}
              <p data-testid="rollcall-confirm-summary">
                Mark this player as present for{' '}
                <span className="font-medium">
                  {event?.name ?? 'the event'}
                </span>
                ? They&apos;ll be locked into the roster.
              </p>
            </div>
          ) : (
            ''
          )
        }
        actionLabel="Confirm"
        onConfirm={async (reason) => {
          const target = confirmSignup;
          if (!target) return false;
          const next = nextFocusFrom(target);
          const success = await dispatch(
            'confirm',
            target,
            (r) =>
              signupActions.confirm.mutateAsync({
                id: target.id,
                ...(r ? { reason: r } : {}),
              }),
            { reason, errorLabel: `confirm ${DisplayName(target)}` },
          );
          if (success) setFocusedId(next);
          return success;
        }}
        confirmTestId="rollcall-confirm-dialog-confirm"
        cancelTestId="rollcall-confirm-dialog-cancel"
      />

      {/* Per-row Reject (approved → rejected) */}
      <StaffReasonDialog
        key={`reject-${rejectSignup?.id}`}
        required={reasonMode('reject', rejectSignup) === 'required'}
        submitting={false}
        contentTestId="rollcall-reject-dialog"
        open={!!rejectSignup}
        onOpenChange={(open) => {
          if (!open) setRejectSignup(null);
        }}
        title="Reject signup"
        description={
          rejectSignup ? (
            <div className="flex flex-col gap-3">
              {(() => {
                const stripUser = userMap.get(rejectSignup.user);
                return stripUser ? (
                  <UserStrip
                    user={stripUser}
                    showBorder={false}
                    organizationId={event?.organization ?? undefined}
                    className={brandDialogPanel}
                    data-testid="rollcall-reject-user-strip"
                  />
                ) : null;
              })()}
              <p data-testid="rollcall-reject-summary">
                Reject this signup? They&apos;ll be removed from the active
                roster. You can restore them from the Other section without
                leaving this screen.
              </p>
            </div>
          ) : (
            ''
          )
        }
        actionLabel="Reject"
        destructive
        onConfirm={async (reason) => {
          const target = rejectSignup;
          if (!target) return false;
          const next = nextFocusFrom(target);
          const success = await dispatch(
            'reject',
            target,
            (r) =>
              signupActions.reject.mutateAsync({
                id: target.id,
                ...(r ? { reason: r } : {}),
              }),
            { reason, errorLabel: `remove ${DisplayName(target)}` },
          );
          if (success) setFocusedId(next);
          return success;
        }}
        confirmTestId="rollcall-reject-dialog-confirm"
        cancelTestId="rollcall-reject-dialog-cancel"
      />

      {/* Per-row Cancel (confirmed → cancelled) */}
      <StaffReasonDialog
        key={`cancel-${cancelSignup?.id}`}
        required={reasonMode('cancel', cancelSignup) === 'required'}
        submitting={false}
        contentTestId="rollcall-cancel-dialog"
        open={!!cancelSignup}
        onOpenChange={(open) => {
          if (!open) setCancelSignup(null);
        }}
        title="Remove confirmed player"
        description={
          cancelSignup ? (
            <div className="flex flex-col gap-3">
              {(() => {
                const stripUser = userMap.get(cancelSignup.user);
                return stripUser ? (
                  <UserStrip
                    user={stripUser}
                    showBorder={false}
                    organizationId={event?.organization ?? undefined}
                    className={brandDialogPanel}
                    data-testid="rollcall-cancel-user-strip"
                  />
                ) : null;
              })()}
              <p data-testid="rollcall-cancel-summary">
                Remove this player from the confirmed roster? You can restore
                them from the Other section without leaving this screen.
              </p>
            </div>
          ) : (
            ''
          )
        }
        actionLabel="Remove"
        destructive
        onConfirm={async (reason) => {
          const target = cancelSignup;
          if (!target) return false;
          const next = nextFocusFrom(target);
          const success = await dispatch(
            'cancel',
            target,
            (r) =>
              signupActions.cancel.mutateAsync({
                id: target.id,
                ...(r ? { reason: r } : {}),
              }),
            { reason, errorLabel: `remove ${DisplayName(target)}` },
          );
          if (success) setFocusedId(next);
          return success;
        }}
        confirmTestId="rollcall-cancel-dialog-confirm"
        cancelTestId="rollcall-cancel-dialog-cancel"
      />

      {/* Start Tournament Confirmation */}
      <ConfirmDialog
        open={showStartConfirm}
        onOpenChange={setShowStartConfirm}
        title="Start Tournament"
        description={`Start the tournament with ${totalReady} confirmed player${totalReady !== 1 ? 's' : ''}? This will finalize the roster and begin the draft/bracket.`}
        confirmLabel="Start Tournament"
        onConfirm={async () => {
          try {
            setIsNavigating(true);
            const result = await actions.startTournament.mutateAsync();
            toast.success('Tournament started!');
            // Land on the tournament overview rather than jumping straight into the
            // draft view so the organizer can pick the draft type from there (#267).
            const tournamentPk = result?.tournament;
            if (tournamentPk) {
              navigate(`/tournament/${tournamentPk}`);
            } else {
              navigate(`/events/${eventId}`);
            }
          } catch (err) {
            setIsNavigating(false);
            toast.error(startTournamentErrorMessage(err));
          }
        }}
        confirmTestId="rollcall-start-dialog-confirm"
      />
    </div>
  );
}

/** Individual signup strip with confirm/reject actions */
const SignupStrip = memo(function SignupStrip({
  signup,
  userMap,
  isAdmin,
  leaguePk,
  eventTimezone,
  pending,
  focused,
  onSelect,
  onRequestApproval,
  onRequestConfirm,
  onRequestReject,
  onRequestCancel,
  onRequestRestore,
  onRequestVoid,
  conductMember,
}: {
  conductMember?: ForecastMember;
  signup: EventSignupType;
  userMap: Map<number, import('~/store/userCacheTypes').UserEntry>;
  isAdmin: boolean;
  leaguePk: number | null;
  eventTimezone?: string;
  pending: boolean;
  focused: boolean;
  onSelect: (id: number) => void;
  onRequestApproval: (signup: EventSignupType) => void;
  onRequestConfirm: (signup: EventSignupType) => void;
  onRequestReject: (signup: EventSignupType) => void;
  onRequestCancel: (signup: EventSignupType) => void;
  onRequestRestore: (signup: EventSignupType) => void;
  onRequestVoid: (signup: EventSignupType) => void;
}) {
  const user = userMap.get(signup.user);
  const isApprovable = isApprovableSignup(signup.status);
  const canRestore = canRestoreSignup(signup.status);
  const primaryKey = focused ? '1' : undefined;
  const removeKey = focused ? '2' : undefined;

  const statusBadge = (
    <span
      className="inline-flex flex-wrap items-center justify-end gap-1"
      data-testid={`rollcall-row-status-${signup.id}`}
    >
      <span className="inline-flex items-center gap-1">
        {pending && (
          <Loader2
            className="h-3.5 w-3.5 animate-spin text-muted-foreground"
            data-testid="rollcall-row-pending"
            aria-label="Saving"
          />
        )}
        <EventStateBadge state={signup.status} />
      </span>
      <SignupInLineSince signup={signup} eventTimezone={eventTimezone} />
      <ConductBadge member={conductMember} />
    </span>
  );

  const actionSlot = isAdmin ? (
    <div className="flex gap-1">
      {signup.status === SignupStatus.APPROVED && (
        <>
          <SecondaryButton
            color="green"
            size="sm"
            data-testid="rollcall-confirm-btn"
            hotkey={primaryKey}
            onClick={() => onRequestConfirm(signup)}
            disabled={pending}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Confirm</span>
          </SecondaryButton>
          <DestructiveButton
            size="sm"
            data-testid="rollcall-reject-btn"
            hotkey={removeKey}
            onClick={() => onRequestReject(signup)}
            disabled={pending}
          >
            <XCircle className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Remove</span>
          </DestructiveButton>
        </>
      )}
      {signup.status === SignupStatus.CONFIRMED && (
        <DestructiveButton
          size="sm"
          data-testid={`rollcall-cancel-btn-${signup.id}`}
          hotkey={removeKey}
          onClick={() => onRequestCancel(signup)}
          disabled={pending}
        >
          <XCircle className="h-3.5 w-3.5" />
          <span className="hidden sm:inline ml-1">Remove</span>
        </DestructiveButton>
      )}
      {isApprovable && (
        <>
          {/* Always open the MMR modal so the admin can confirm/edit the prior approved MMR. */}
          <SecondaryButton
            color="green"
            size="sm"
            data-testid="rollcall-approve-btn"
            hotkey={primaryKey}
            onClick={() => onRequestApproval(signup)}
            disabled={pending}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Approve</span>
          </SecondaryButton>
          <DestructiveButton
            size="sm"
            data-testid="rollcall-reject-btn"
            hotkey={removeKey}
            onClick={() => onRequestReject(signup)}
            disabled={pending}
          >
            <XCircle className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Remove</span>
          </DestructiveButton>
        </>
      )}
      {canRestore && (
        <SecondaryButton
          size="sm"
          data-testid="rollcall-restore-btn"
          hotkey={primaryKey}
          onClick={() => onRequestRestore(signup)}
          disabled={pending}
        >
          <Undo2 className="h-3.5 w-3.5" />
          <span className="hidden sm:inline ml-1">Restore</span>
        </SecondaryButton>
      )}
      {canVoidWithdrawal(signup.status) && (
        <Tooltip>
          <TooltipTrigger asChild>
            <SecondaryButton
              size="sm"
              aria-label="Void withdrawal"
              data-testid="rollcall-void-withdrawal-btn"
              onClick={() => onRequestVoid(signup)}
              disabled={pending}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span className="hidden sm:inline ml-1">Void</span>
            </SecondaryButton>
          </TooltipTrigger>
          <TooltipContent>
            Restore exact place, class and commitment
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  ) : undefined;

  return (
    <div
      data-rollcall-row={signup.id}
      data-testid={`rollcall-row-${signup.id}`}
      data-focused={focused || undefined}
      aria-current={focused || undefined}
      onPointerDown={isAdmin ? () => onSelect(signup.id) : undefined}
      className={cn(
        'rounded-lg transition-shadow',
        focused && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
      )}
    >
      {user ? (
        <UserStrip
          user={user}
          compact
          showPositions
          organizationId={signup.organization ?? undefined}
          statsLeagueId={leaguePk}
          statsBreakpoint="wide"
          contextSlot={statusBadge}
          actionSlot={actionSlot}
        />
      ) : (
        // Fallback for signups not yet in cache
        <div className="flex items-center gap-3 rounded-lg p-2 border border-border/50 bg-muted/25">
          <div className="w-9 h-9 rounded-full bg-muted shrink-0 flex items-center justify-center text-xs text-muted-foreground">
            {(signup.username ?? '?')[0]?.toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium truncate">
              {DisplayName(signup)}
            </p>
          </div>
          {statusBadge}
          {actionSlot}
        </div>
      )}
    </div>
  );
});
