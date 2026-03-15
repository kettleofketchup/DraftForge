import { generateMeta } from '~/lib/seo';
import { getEvent } from '~/components/api/api';
import { useParams, useNavigate } from 'react-router';
import type { Route } from './+types/event';

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

  if (event?.name) {
    const orgName = event.organization_name ? ` by ${event.organization_name}` : '';
    return generateMeta({
      title: event.name,
      description: `${event.name}${orgName} - Event details and signups`,
      url: `/events/${event.id}`,
    });
  }

  return generateMeta({
    title: 'Event',
    description: 'Event details and signups',
  });
}

import { useState, useCallback, useMemo } from 'react';
import {
  CalendarDays,
  Building2,
  Loader2,
  Users,
  Clock,
  CheckCircle2,
  XCircle,
  UserCheck,
  UserX,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '~/components/ui/badge';
import { EventStateBadge } from '~/components/events';
import { EventState } from '~/components/events/schemas';
import type { EventSignupType } from '~/components/events/schemas';
import { PrimaryButton, SecondaryButton, DestructiveButton } from '~/components/ui/buttons';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { UserStrip } from '~/components/user';
import type { UserType } from '~/components/user/types';
import {
  useEvent,
  useEventSignups,
  useRsvpMutation,
  useEventActionMutation,
  useSignupActionMutations,
} from '~/hooks/useEvent';
import { useOrganizations } from '~/components/organization';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { usePageNav } from '~/hooks/usePageNav';
import { useUserStore } from '~/store/userStore';
import { ConfirmDialog } from '~/components/ui/dialogs';

export default function EventPage() {
  const { eventId, tab } = useParams<{ eventId: string; tab?: string }>();
  const navigate = useNavigate();
  const id = eventId ? parseInt(eventId, 10) : null;

  const { data: event, isLoading, error } = useEvent(id);
  const { data: signups } = useEventSignups(id);
  const currentUser = useUserStore((state) => state.currentUser);

  const [activeTab, setActiveTab] = useState(tab || 'details');
  const [showRollCallConfirm, setShowRollCallConfirm] = useState(false);
  const [showRsvpConfirm, setShowRsvpConfirm] = useState(false);
  const [showCancelRsvpConfirm, setShowCancelRsvpConfirm] = useState(false);

  // Permission check - find org for this event
  const { organizations } = useOrganizations();
  const eventOrg = useMemo(
    () => organizations.find((o) => o.pk === event?.organization) || null,
    [organizations, event?.organization],
  );
  const isAdmin = useIsOrganizationAdmin(eventOrg);

  // Mutations
  const rsvpMutation = useRsvpMutation(id ?? 0);
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);

  // Check if current user already has an active signup
  const mySignup = useMemo(
    () => {
      if (!signups || !currentUser?.pk) return undefined;
      return signups.find(
        (s) => Number(s.user) === Number(currentUser.pk) && s.status !== 'cancelled' && s.status !== 'rejected'
      );
    },
    [signups, currentUser?.pk],
  );

  // Split signups into active and waitlisted
  const activeSignups = useMemo(
    () => (signups ?? []).filter((s) => s.status !== 'waitlisted' && s.status !== 'cancelled' && s.status !== 'rejected'),
    [signups],
  );
  const waitlistedSignups = useMemo(
    () => (signups ?? []).filter((s) => s.status === 'waitlisted'),
    [signups],
  );

  const handleTabChange = useCallback(
    (newTab: string) => {
      setActiveTab(newTab);
      navigate(`/events/${eventId}/${newTab}`);
    },
    [eventId, navigate],
  );

  // Page nav for mobile
  const signupCount = signups?.length ?? 0;
  const pageNavOptions = useMemo(
    () => [
      { value: 'details', label: 'Details' },
      { value: 'signups', label: `${activeSignups.length} Signups` },
      { value: 'waitlist', label: `${waitlistedSignups.length} Waitlist` },
    ],
    [activeSignups.length, waitlistedSignups.length],
  );

  usePageNav(event ? pageNavOptions : null, activeTab, handleTabChange);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="text-center py-12 text-destructive">
        {error?.message || 'Event not found'}
      </div>
    );
  }

  const scheduledDate = new Date(event.scheduled_at);
  const formattedDate = scheduledDate.toLocaleDateString(undefined, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      <div className="flex flex-col gap-6 rounded-lg border border-border bg-base-200/50 p-4 md:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:justify-between gap-3">
          <div className="space-y-2 min-w-0">
            <div className="flex items-center gap-3">
              <CalendarDays className="h-7 w-7 md:h-8 md:w-8 text-primary shrink-0" />
              <h1 className="text-xl! md:text-3xl! font-bold truncate">{event.name}</h1>
              <EventStateBadge state={event.state} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
              {event.organization_name && (
                <Badge variant="outline" className="flex items-center gap-1">
                  <Building2 className="h-3 w-3" />
                  {event.organization_name}
                </Badge>
              )}
              <Badge variant="secondary" className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formattedDate}
              </Badge>
            </div>
          </div>

          {/* RSVP / Admin actions */}
          <div className="flex flex-wrap gap-2 shrink-0 w-full sm:w-auto">
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && !mySignup && (
              <PrimaryButton
                size="sm"
                onClick={() => setShowRsvpConfirm(true)}
                disabled={rsvpMutation.isPending}
                className="w-full sm:w-auto"
              >
                <Users className="h-4 w-4 mr-2" />
                RSVP
              </PrimaryButton>
            )}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && mySignup && (
              <DestructiveButton
                size="sm"
                onClick={() => setShowCancelRsvpConfirm(true)}
                loading={signupActions.cancel.isPending}
                depth={false}
                className="bg-gradient-to-r from-red-700 to-violet-900 hover:from-red-600 hover:to-violet-800 shadow-lg active:translate-y-0.5 w-full sm:w-auto"
              >
                <XCircle className="h-4 w-4 mr-2" />
                Cancel RSVP
              </DestructiveButton>
            )}

            {isAdmin && event.state === EventState.UPCOMING && (
              <SecondaryButton
                color="green"
                size="sm"
                onClick={() => actions.openSignups.mutate()}
                disabled={actions.openSignups.isPending}
                data-testid="event-open-signups-btn"
                className="w-full sm:w-auto"
              >
                Open Signups
              </SecondaryButton>
            )}

            {isAdmin && event.state === EventState.SIGNUPS_OPEN && (
              <SecondaryButton
                color="orange"
                size="sm"
                onClick={() => setShowRollCallConfirm(true)}
                disabled={actions.startRollCall.isPending}
                data-testid="event-start-rollcall-btn"
                className="w-full sm:w-auto"
              >
                Start Roll Call
              </SecondaryButton>
            )}

            {isAdmin && event.state === EventState.ROLL_CALL && (
              <PrimaryButton
                size="sm"
                onClick={() => navigate(`/rollcall/${eventId}`)}
                data-testid="event-start-tournament-btn"
                className="w-full sm:w-auto"
              >
                Open Roll Call
              </PrimaryButton>
            )}

            {isAdmin &&
              event.state !== EventState.COMPLETED &&
              event.state !== EventState.CANCELLED && (
                <DestructiveButton
                  size="sm"
                  onClick={() => actions.cancelEvent.mutate()}
                  loading={actions.cancelEvent.isPending}
                  depth={false}
                  data-testid="event-cancel-btn"
                  className="bg-gradient-to-r from-red-700 to-violet-900 hover:from-red-600 hover:to-violet-800 shadow-lg active:translate-y-0.5 w-full sm:w-auto"
                >
                  <XCircle className="h-4 w-4 mr-2" />
                  Cancel Event
                </DestructiveButton>
              )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList>
            <TabsTrigger value="details" data-testid="event-tab-details">
              Details
            </TabsTrigger>
            <TabsTrigger value="signups" data-testid="event-tab-signups">
              Signups ({activeSignups.length})
            </TabsTrigger>
            <TabsTrigger value="waitlist" data-testid="event-tab-waitlist">
              Waitlist ({waitlistedSignups.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="details">
            <DetailsTab event={event} />
          </TabsContent>

          <TabsContent value="signups">
            <SignupsTab
              signups={activeSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
            />
          </TabsContent>

          <TabsContent value="waitlist">
            <SignupsTab
              signups={waitlistedSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
            />
          </TabsContent>
        </Tabs>
      </div>

      <ConfirmDialog
        open={showRollCallConfirm}
        onOpenChange={setShowRollCallConfirm}
        title="Start Roll Call"
        description={`Freeze signups and begin roll call for "${event.name}"? Players will need to be confirmed before the tournament can start.`}
        confirmLabel="Start Roll Call"
        onConfirm={async () => {
          try {
            await actions.startRollCall.mutateAsync();
            toast.success('Roll call started');
            navigate(`/rollcall/${eventId}`);
          } catch {
            toast.error('Failed to start roll call');
          }
        }}
      />

      <ConfirmDialog
        open={showRsvpConfirm}
        onOpenChange={setShowRsvpConfirm}
        title="RSVP for Event"
        description={`Sign up for "${event.name}"? You'll be added to the signup list.`}
        confirmLabel="RSVP"
        onConfirm={async () => {
          try {
            await rsvpMutation.mutateAsync();
            toast.success('RSVP submitted!');
          } catch (err: unknown) {
            const message = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
            toast.error(message || 'Failed to RSVP');
          }
        }}
      />

      <ConfirmDialog
        open={showCancelRsvpConfirm}
        onOpenChange={setShowCancelRsvpConfirm}
        title="Cancel RSVP"
        description={`Remove your signup from "${event.name}"?`}
        confirmLabel="Cancel RSVP"
        variant="destructive"
        onConfirm={async () => {
          if (!mySignup) return;
          try {
            await signupActions.cancel.mutateAsync(mySignup.id);
            toast.success('RSVP cancelled');
          } catch {
            toast.error('Failed to cancel RSVP');
          }
        }}
      />
    </div>
  );
}

/** Details tab showing event configuration */
function DetailsTab({ event }: { event: NonNullable<ReturnType<typeof useEvent>['data']> }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <h3 className="font-semibold">Tournament Info</h3>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {event.tournament_name && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tournament</span>
              <span>{event.tournament_name}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-muted-foreground">Type</span>
            <span>{event.tournament_type}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Draft</span>
            <span>{event.draft_type}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Teams</span>
            <span>{event.number_of_teams} x {event.people_per_team}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h3 className="font-semibold">Signup Rules</h3>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Players</span>
            <span>
              {event.min_players ?? '?'} - {event.max_players ?? '?'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Auto Approve</span>
            <span>{event.auto_approve ? 'Yes' : 'No'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Auto Confirm</span>
            <span>{event.auto_confirm ? 'Yes' : 'No'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Roll Call</span>
            <span>{event.roll_call_enabled ? event.roll_call_mode : 'Disabled'}</span>
          </div>
        </CardContent>
      </Card>

      {event.description && (
        <Card className="md:col-span-2">
          <CardHeader>
            <h3 className="font-semibold">Description</h3>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {event.description}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** Signups tab showing participants and admin actions */
function SignupsTab({
  signups,
  isAdmin,
  signupActions,
}: {
  signups: EventSignupType[];
  isAdmin: boolean;
  signupActions: ReturnType<typeof useSignupActionMutations>;
}) {
  if (signups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Users className="w-12 h-12 mb-3 opacity-50" />
        <p>No signups yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {signups.map((signup, index) => {
        const userData = signup.user_data;
        const position = signup.waitlist_position ?? index + 1;

        const adminActions = isAdmin ? (
          <div className="flex gap-1">
            {(signup.status === 'rsvp' || signup.status === 'pending_approval') && (
              <>
                <SecondaryButton
                  color="green"
                  size="sm"
                  onClick={() => signupActions.approve.mutate(signup.id)}
                  disabled={signupActions.approve.isPending}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline ml-1">Approve</span>
                </SecondaryButton>
                <DestructiveButton
                  size="sm"
                  onClick={() => signupActions.reject.mutate(signup.id)}
                  loading={signupActions.reject.isPending}
                >
                  <UserX className="h-3.5 w-3.5" />
                </DestructiveButton>
              </>
            )}
            {signup.status === 'approved' && (
              <SecondaryButton
                color="blue"
                size="sm"
                onClick={() => signupActions.confirm.mutate(signup.id)}
                disabled={signupActions.confirm.isPending}
              >
                <UserCheck className="h-3.5 w-3.5" />
                <span className="hidden sm:inline ml-1">Confirm</span>
              </SecondaryButton>
            )}
          </div>
        ) : undefined;

        const statusSlot = (
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">#{position}</span>
            <EventStateBadge state={signup.status} />
          </div>
        );

        if (userData) {
          return (
            <UserStrip
              key={signup.id}
              user={userData as unknown as UserType}
              compact
              showPositions
              contextSlot={statusSlot}
              actionSlot={adminActions}
            />
          );
        }

        // Fallback for signups without full user data
        return (
          <div
            key={signup.id}
            className="flex items-center gap-3 rounded-lg p-2 border border-border/50 bg-muted/25"
          >
            <div className="w-9 h-9 rounded-full bg-muted shrink-0 flex items-center justify-center text-xs text-muted-foreground">
              {(signup.username ?? '?')[0]?.toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">
                {signup.username ?? `User #${signup.user}`}
              </p>
            </div>
            {statusSlot}
            {adminActions}
          </div>
        );
      })}
    </div>
  );
}
