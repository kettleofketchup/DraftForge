import { generateMeta } from '~/lib/seo';
import { getEvent } from '~/components/api/api';
import { useParams, useNavigate } from 'react-router';
import type { Route } from './+types/rollcall';
import type { EventSSR } from '~/lib/ssr-types';

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

import { useState, useMemo, useEffect, useCallback } from 'react';
import { Loader2, Users, CheckCircle2, XCircle, ArrowLeft, Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '~/components/ui/badge';
import { PrimaryButton, SecondaryButton, DestructiveButton, brandDialogPanel } from '~/components/ui/buttons';
import { Button } from '~/components/ui/button';
import { EventStateBadge, MmrApprovalModal } from '~/components/events';
import { EventState, SignupStatus } from '~/components/events/schemas';
import type { EventSignupType } from '~/components/events/schemas';
import { UserStrip } from '~/components/user';
import {
  useEvent,
  useEventSignups,
  useEventSignupUsers,
  useEventActionMutation,
  useSignupActionMutations,
} from '~/hooks/useEvent';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { useOrganization } from '~/components/organization';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { EntityBreadcrumb } from '~/components/ui/entity-breadcrumb';

export default function RollCallPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const navigate = useNavigate();
  const id = eventId ? parseInt(eventId, 10) : null;

  const { data: event, isLoading } = useEvent(id);
  const { data: signups = [] } = useEventSignups(id);
  useEventSignupUsers(signups, event?.organization ?? null);
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);

  const { organization: eventOrg } = useOrganization(event?.organization ?? undefined);
  const isAdmin = event?.user_can_manage ?? false;

  const [showStartConfirm, setShowStartConfirm] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);
  const [approvalSignup, setApprovalSignup] = useState<EventSignupType | null>(null);
  const [confirmSignup, setConfirmSignup] = useState<EventSignupType | null>(null);
  const [rejectSignup, setRejectSignup] = useState<EventSignupType | null>(null);
  const [cancelSignup, setCancelSignup] = useState<EventSignupType | null>(null);

  // Resolve all signup users from cache
  const userPks = useMemo(() => signups.map((s) => s.user), [signups]);
  const resolvedUsers = useResolvedUsers(userPks);
  const userMap = useMemo(
    () => new Map(resolvedUsers.map((u) => [u.pk, u])),
    [resolvedUsers],
  );

  // Restore is non-destructive — fire the mutation directly. The backend
  // moves REJECTED/CANCELLED back to APPROVED during ROLL_CALL.
  const handleRestore = useCallback(
    (signup: EventSignupType) => {
      signupActions.reinstate.mutate(signup.id, {
        onSuccess: () => toast.success(`Restored ${signup.username ?? `User #${signup.user}`}`),
        onError: () => toast.error('Failed to restore signup'),
      });
    },
    [signupActions.reinstate],
  );

  // Hotkeys: 1 / 2 act on the first signup awaiting confirmation. They mirror
  // the buttons (and their <Kbd> hints) shown next to that first row.
  const firstAwaiting = useMemo(
    () => signups.find((s) => s.status === SignupStatus.APPROVED) ?? null,
    [signups],
  );
  useEffect(() => {
    if (!isAdmin) return;
    const handler = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) return;
      // Ignore while another dialog is open — those have their own Enter/Backspace bindings.
      if (approvalSignup || confirmSignup || rejectSignup || cancelSignup || showStartConfirm) return;
      if (!firstAwaiting) return;
      if (e.key === '1') {
        e.preventDefault();
        setConfirmSignup(firstAwaiting);
      } else if (e.key === '2') {
        e.preventDefault();
        setRejectSignup(firstAwaiting);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isAdmin, firstAwaiting, approvalSignup, confirmSignup, rejectSignup, cancelSignup, showStartConfirm]);

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
          <p data-testid="rollcall-not-active" className="text-muted-foreground mb-4">
            This event is not in roll call mode.
          </p>
          <Button data-testid="rollcall-back-btn" variant="outline" onClick={() => navigate(`/events/${eventId}`)}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Event
          </Button>
        </div>
      </div>
    );
  }

  // Separate signups by status
  const confirmed = signups.filter((s) => s.status === 'confirmed');
  const approved = signups.filter((s) => s.status === 'approved');
  const others = signups.filter((s) => !['confirmed', 'approved'].includes(s.status));

  const totalReady = confirmed.length;
  const minPlayers = event.min_players;
  const maxPlayers = event.max_players;
  const hasEnough = !minPlayers || totalReady >= minPlayers;

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      <EntityBreadcrumb
        segments={[
          ...(eventOrg ? [{ type: 'organization' as const, label: eventOrg.name, href: `/organizations/${eventOrg.pk}` }] : []),
          { type: 'event' as const, label: event.name, href: `/events/${eventId}` },
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
              <h1 data-testid="rollcall-heading" className="text-xl md:text-2xl font-bold">Roll Call</h1>
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
                disabled={!hasEnough || actions.startTournament.isPending}
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

        {/* Confirmed players */}
        {confirmed.length > 0 && (
          <div>
            <h3 data-testid="rollcall-confirmed-section" className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
              Confirmed ({confirmed.length})
            </h3>
            <div className="space-y-1.5">
              {confirmed.map((signup) => (
                <SignupStrip
                  key={signup.id}
                  signup={signup}
                  userMap={userMap}
                  isAdmin={isAdmin}
                  gameType={event.game_type}
                  signupActions={signupActions}
                  onRequestApproval={setApprovalSignup}
                  onRequestConfirm={setConfirmSignup}
                  onRequestReject={setRejectSignup}
                  onRequestCancel={setCancelSignup}
                  onRequestRestore={handleRestore}
                />
              ))}
            </div>
          </div>
        )}

        {/* Approved but not confirmed */}
        {approved.length > 0 && (
          <div>
            <h3 data-testid="rollcall-awaiting-section" className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
              Awaiting Confirmation ({approved.length})
            </h3>
            <div className="space-y-1.5">
              {approved.map((signup, idx) => (
                <SignupStrip
                  key={signup.id}
                  signup={signup}
                  userMap={userMap}
                  isAdmin={isAdmin}
                  gameType={event.game_type}
                  signupActions={signupActions}
                  onRequestApproval={setApprovalSignup}
                  onRequestConfirm={setConfirmSignup}
                  onRequestReject={setRejectSignup}
                  onRequestCancel={setCancelSignup}
                  onRequestRestore={handleRestore}
                  showAwaitingHotkeys={idx === 0 && isAdmin}
                />
              ))}
            </div>
          </div>
        )}

        {/* Other statuses */}
        {others.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
              Other ({others.length})
            </h3>
            <div className="space-y-1.5">
              {others.map((signup) => (
                <SignupStrip
                  key={signup.id}
                  signup={signup}
                  userMap={userMap}
                  isAdmin={isAdmin}
                  gameType={event.game_type}
                  signupActions={signupActions}
                  onRequestApproval={setApprovalSignup}
                  onRequestConfirm={setConfirmSignup}
                  onRequestReject={setRejectSignup}
                  onRequestCancel={setCancelSignup}
                  onRequestRestore={handleRestore}
                />
              ))}
            </div>
          </div>
        )}

        {signups.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Users className="w-12 h-12 mb-3 opacity-50" />
            <p>No signups to review</p>
          </div>
        )}
      </div>

      {/* MMR approval modal — opens for Dota2 events so previously-approved MMR is shown */}
      <MmrApprovalModal
        signup={approvalSignup}
        open={!!approvalSignup}
        onOpenChange={(open) => { if (!open) setApprovalSignup(null); }}
        onApprove={(signupId, mmr) => {
          signupActions.approve.mutate({ id: signupId, mmr }, {
            onSuccess: () => setApprovalSignup(null),
          });
        }}
        isApproving={signupActions.approve.isPending}
      />

      {/* Per-row Confirm (approved → confirmed) */}
      <ConfirmDialog
        open={!!confirmSignup}
        onOpenChange={(open) => { if (!open) setConfirmSignup(null); }}
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
                <span className="font-medium">{event?.name ?? 'the event'}</span>?
                They&apos;ll be locked into the roster.
              </p>
            </div>
          ) : ''
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        isLoading={signupActions.confirm.isPending}
        onConfirm={() => {
          if (!confirmSignup) return;
          signupActions.confirm.mutate(confirmSignup.id, {
            onSuccess: () => setConfirmSignup(null),
          });
        }}
        confirmTestId="rollcall-confirm-dialog-confirm"
        cancelTestId="rollcall-confirm-dialog-cancel"
      />

      {/* Per-row Reject (approved → rejected) */}
      <ConfirmDialog
        open={!!rejectSignup}
        onOpenChange={(open) => { if (!open) setRejectSignup(null); }}
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
                Reject this signup? They&apos;ll be removed from the active roster.
                You can restore them from the Other section without leaving this screen.
              </p>
            </div>
          ) : ''
        }
        confirmLabel="Reject"
        cancelLabel="Cancel"
        variant="destructive"
        isLoading={signupActions.reject.isPending}
        onConfirm={() => {
          if (!rejectSignup) return;
          signupActions.reject.mutate(rejectSignup.id, {
            onSuccess: () => setRejectSignup(null),
            onError: () => toast.error('Failed to reject signup'),
          });
        }}
        confirmTestId="rollcall-reject-dialog-confirm"
        cancelTestId="rollcall-reject-dialog-cancel"
      />

      {/* Per-row Cancel (confirmed → cancelled) */}
      <ConfirmDialog
        open={!!cancelSignup}
        onOpenChange={(open) => { if (!open) setCancelSignup(null); }}
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
                Remove this player from the confirmed roster? You can restore them from
                the Other section without leaving this screen.
              </p>
            </div>
          ) : ''
        }
        confirmLabel="Remove"
        cancelLabel="Cancel"
        variant="destructive"
        isLoading={signupActions.cancel.isPending}
        onConfirm={() => {
          if (!cancelSignup) return;
          signupActions.cancel.mutate(cancelSignup.id, {
            onSuccess: () => setCancelSignup(null),
            onError: () => toast.error('Failed to remove player'),
          });
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
            // Navigate to the tournament page if available, otherwise back to event
            const tournamentPk = result?.tournament;
            if (tournamentPk) {
              navigate(`/tournament/${tournamentPk}/teams/draft`);
            } else {
              navigate(`/events/${eventId}`);
            }
          } catch {
            setIsNavigating(false);
            toast.error('Failed to start tournament');
          }
        }}
      />
    </div>
  );
}

/** Individual signup strip with confirm/reject actions */
function SignupStrip({
  signup,
  userMap,
  isAdmin,
  gameType,
  signupActions,
  onRequestApproval,
  onRequestConfirm,
  onRequestReject,
  onRequestCancel,
  onRequestRestore,
  showAwaitingHotkeys = false,
}: {
  signup: EventSignupType;
  userMap: Map<number, import('~/store/userCacheTypes').UserEntry>;
  isAdmin: boolean;
  gameType: number;
  signupActions: ReturnType<typeof useSignupActionMutations>;
  onRequestApproval: (signup: EventSignupType) => void;
  onRequestConfirm: (signup: EventSignupType) => void;
  onRequestReject: (signup: EventSignupType) => void;
  onRequestCancel: (signup: EventSignupType) => void;
  onRequestRestore: (signup: EventSignupType) => void;
  showAwaitingHotkeys?: boolean;
}) {
  const user = userMap.get(signup.user);

  const isApprovable =
    signup.status === SignupStatus.RSVP ||
    signup.status === SignupStatus.PENDING_APPROVAL ||
    signup.status === SignupStatus.WAITLISTED;

  const handleApprove = () => {
    // All games have an MMR concept — always open the approval modal so the
    // admin can confirm/edit the prior approved MMR. Game-specific UI inside
    // the modal (medal/range helper for Dota) gates itself via useGameType.
    onRequestApproval(signup);
  };

  const isRemoved =
    signup.status === SignupStatus.REJECTED || signup.status === SignupStatus.CANCELLED;

  const actionSlot = isAdmin ? (
    <div className="flex gap-1">
      {signup.status === 'approved' && (
        <>
          <SecondaryButton
            color="green"
            size="sm"
            data-testid="rollcall-confirm-btn"
            hotkey={showAwaitingHotkeys ? '1' : undefined}
            onClick={() => onRequestConfirm(signup)}
            disabled={signupActions.confirm.isPending}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Confirm</span>
          </SecondaryButton>
          <DestructiveButton
            size="sm"
            data-testid="rollcall-reject-btn"
            hotkey={showAwaitingHotkeys ? '2' : undefined}
            onClick={() => onRequestReject(signup)}
            disabled={signupActions.reject.isPending}
          >
            <XCircle className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Remove</span>
          </DestructiveButton>
        </>
      )}
      {signup.status === 'confirmed' && (
        <DestructiveButton
          size="sm"
          data-testid="rollcall-cancel-btn"
          onClick={() => onRequestCancel(signup)}
          disabled={signupActions.cancel.isPending}
        >
          <XCircle className="h-3.5 w-3.5" />
          <span className="hidden sm:inline ml-1">Remove</span>
        </DestructiveButton>
      )}
      {isApprovable && (
        <>
          <SecondaryButton
            color="green"
            size="sm"
            data-testid="rollcall-approve-btn"
            onClick={handleApprove}
            disabled={signupActions.approve.isPending}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Approve</span>
          </SecondaryButton>
          <DestructiveButton
            size="sm"
            data-testid="rollcall-reject-btn"
            onClick={() => onRequestReject(signup)}
            disabled={signupActions.reject.isPending}
          >
            <XCircle className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Remove</span>
          </DestructiveButton>
        </>
      )}
      {isRemoved && (
        <SecondaryButton
          size="sm"
          data-testid="rollcall-restore-btn"
          onClick={() => onRequestRestore(signup)}
          disabled={signupActions.reinstate.isPending}
        >
          <Undo2 className="h-3.5 w-3.5" />
          <span className="hidden sm:inline ml-1">Restore</span>
        </SecondaryButton>
      )}
    </div>
  ) : undefined;

  if (user) {
    return (
      <UserStrip
        user={user}
        compact
        showPositions
        organizationId={signup.organization ?? undefined}
        contextSlot={<EventStateBadge state={signup.status} />}
        actionSlot={actionSlot}
      />
    );
  }

  // Fallback for signups not yet in cache
  return (
    <div className="flex items-center gap-3 rounded-lg p-2 border border-border/50 bg-muted/25">
      <div className="w-9 h-9 rounded-full bg-muted shrink-0 flex items-center justify-center text-xs text-muted-foreground">
        {(signup.username ?? '?')[0]?.toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">
          {signup.username ?? `User #${signup.user}`}
        </p>
      </div>
      <EventStateBadge state={signup.status} />
      {actionSlot}
    </div>
  );
}
