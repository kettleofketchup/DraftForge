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

import { useState, useMemo } from 'react';
import { Loader2, Users, CheckCircle2, XCircle, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '~/components/ui/badge';
import { PrimaryButton, SecondaryButton, DestructiveButton } from '~/components/ui/buttons';
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
  useEventSignupUsers(signups);
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);

  const { organization: eventOrg } = useOrganization(event?.organization ?? undefined);
  const isAdmin = event?.user_can_manage ?? false;

  const [showStartConfirm, setShowStartConfirm] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);
  const [approvalSignup, setApprovalSignup] = useState<EventSignupType | null>(null);

  // Resolve all signup users from cache
  const userPks = useMemo(() => signups.map((s) => s.user), [signups]);
  const resolvedUsers = useResolvedUsers(userPks);
  const userMap = useMemo(
    () => new Map(resolvedUsers.map((u) => [u.pk, u])),
    [resolvedUsers],
  );

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
      <EntityBreadcrumb segments={[
        ...(eventOrg ? [{ type: 'organization' as const, label: eventOrg.name, href: `/organizations/${eventOrg.pk}` }] : []),
        { type: 'event' as const, label: event.name, href: `/events/${eventId}` },
      ]} />
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
              {approved.map((signup) => (
                <SignupStrip
                  key={signup.id}
                  signup={signup}
                  userMap={userMap}
                  isAdmin={isAdmin}
                  gameType={event.game_type}
                  signupActions={signupActions}
                  onRequestApproval={setApprovalSignup}
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
}: {
  signup: EventSignupType;
  userMap: Map<number, import('~/store/userCacheTypes').UserEntry>;
  isAdmin: boolean;
  gameType: number;
  signupActions: ReturnType<typeof useSignupActionMutations>;
  onRequestApproval: (signup: EventSignupType) => void;
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

  const actionSlot = isAdmin ? (
    <div className="flex gap-1">
      {signup.status === 'approved' && (
        <>
          <SecondaryButton
            color="green"
            size="sm"
            data-testid="rollcall-confirm-btn"
            onClick={() => signupActions.confirm.mutate(signup.id)}
            disabled={signupActions.confirm.isPending}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline ml-1">Confirm</span>
          </SecondaryButton>
          <DestructiveButton
            size="sm"
            onClick={() => signupActions.reject.mutate(signup.id)}
            loading={signupActions.reject.isPending}
          >
            <XCircle className="h-3.5 w-3.5" />
          </DestructiveButton>
        </>
      )}
      {signup.status === 'confirmed' && (
        <DestructiveButton
          size="sm"
          onClick={() => signupActions.cancel.mutate(signup.id)}
          loading={signupActions.cancel.isPending}
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
            onClick={() => signupActions.reject.mutate(signup.id)}
            loading={signupActions.reject.isPending}
          >
            <XCircle className="h-3.5 w-3.5" />
          </DestructiveButton>
        </>
      )}
    </div>
  ) : undefined;

  if (user) {
    return (
      <UserStrip
        user={user}
        compact
        showPositions
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
