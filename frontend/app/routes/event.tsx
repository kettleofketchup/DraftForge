import { generateMeta } from '~/lib/seo';
import { getEvent } from '~/components/api/api';
import { useParams, useNavigate } from 'react-router';
import type { Route } from './+types/event';
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
  const event = data?.event as EventSSR | null;

  if (event?.name) {
    const orgName = event.org_name ? ` by ${event.org_name}` : '';
    return generateMeta({
      title: event.name,
      description: `${event.name}${orgName} — Event details and signups on DraftForge`,
      url: `/events/${event.id}`,
    });
  }

  return generateMeta({
    title: 'Event',
    description: 'Event details and signups',
  });
}

import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Bell,
  BellOff,
  Building2,
  Loader2,
  Users,
  Clock,
  CheckCircle2,
  XCircle,
  UserCheck,
  UserX,
  HelpCircle,
  Repeat,
  ArrowDownToLine,
  Undo2,
  UserPlus,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '~/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import { EventStateBadge } from '~/components/events';
import { SubscriberList } from '~/components/events/SubscriberList';
import { EventState, GameType } from '~/components/events/schemas';
import { MmrApprovalModal } from '~/components/events/MmrApprovalModal';
import { DiscordLogSection } from '~/components/events/DiscordLogSection';
import { EditEventModal } from '~/components/events/EditEventModal';
import type { EventSignupType, EventType } from '~/components/events/schemas';
import { PrimaryButton, SecondaryButton, DestructiveButton, HighlightButton } from '~/components/ui/buttons';
import { EventAdminActions } from '~/components/events/EventAdminActions';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { UserEventStrip } from '~/components/user';
import type { DotaProfileData } from '~/components/user';
import {
  useEvent,
  useEventSignups,
  useEventSignupUsers,
  useRsvpMutation,
  useTentativeMutation,
  useEventActionMutation,
  useSignupActionMutations,
} from '~/hooks/useEvent';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminAddSignup, subscribeToRepeater, unsubscribeFromRepeater } from '~/components/api/api';
import { AddUserModal } from '~/components/user/AddUserModal';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { useOrganization } from '~/components/organization';
import { usePageNav } from '~/hooks/usePageNav';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { isUserEntry } from '~/store/userCacheTypes';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { EntityBreadcrumb, type BreadcrumbSegment } from '~/components/ui/entity-breadcrumb';
import api from '~/components/api/axios';
import { extractApiError } from '~/lib/apiError';

export default function EventPage() {
  const { eventId, tab } = useParams<{ eventId: string; tab?: string }>();
  const navigate = useNavigate();
  const id = eventId ? parseInt(eventId, 10) : null;

  const { data: event, isLoading, error } = useEvent(id);
  const { data: signups } = useEventSignups(id);
  useEventSignupUsers(signups);
  const currentUser = useUserStore((state) => state.currentUser);

  const [activeTab, setActiveTab] = useState(tab || 'details');
  const [showRollCallConfirm, setShowRollCallConfirm] = useState(false);
  const [showReopenConfirm, setShowReopenConfirm] = useState(false);
  const [showRsvpConfirm, setShowRsvpConfirm] = useState(false);
  const [showCancelRsvpConfirm, setShowCancelRsvpConfirm] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);

  // Fetch the specific org for this event (needed for org logo and discord server id)
  const { organization: eventOrg } = useOrganization(event?.organization ?? undefined);
  // Permission check uses backend-derived flag (covers org staff AND league staff).
  const isAdmin = event?.user_can_manage ?? false;

  // Populate the org users cache so signup rows can read per-org MMR via the
  // user entity adapter (UserEntry.orgData[orgId].mmr).
  useEffect(() => {
    if (event?.organization) {
      useOrgStore.getState().getOrgUsers(event.organization);
    }
  }, [event?.organization]);

  // Mutations
  const queryClient = useQueryClient();
  const rsvpMutation = useRsvpMutation(id ?? 0);
  const tentativeMutation = useTentativeMutation(id ?? 0);
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);

  // Repeater subscription state
  const repeaterId = event?.event_repeater;
  const { data: repeaterData } = useQuery({
    queryKey: ['repeater', repeaterId],
    queryFn: () => api.get(`/events/repeaters/${repeaterId}/`).then((r) => r.data),
    enabled: !!repeaterId && !!currentUser,
  });
  const isSubscribed = repeaterData?.is_subscribed ?? false;

  const subscribeMutation = useMutation({
    mutationFn: () => subscribeToRepeater(repeaterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repeater', repeaterId] });
      queryClient.invalidateQueries({ queryKey: ['repeater-subscribers', repeaterId] });
      toast.success('Subscribed to event series notifications');
    },
  });

  const unsubscribeMutation = useMutation({
    mutationFn: () => unsubscribeFromRepeater(repeaterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repeater', repeaterId] });
      queryClient.invalidateQueries({ queryKey: ['repeater-subscribers', repeaterId] });
      toast.success('Unsubscribed from event series notifications');
    },
  });

  const breadcrumbSegments = useMemo((): BreadcrumbSegment[] => {
    if (!event) return [];
    const segments: BreadcrumbSegment[] = [];

    if (event.organization_name && event.organization) {
      segments.push({
        type: 'organization',
        label: event.organization_name,
        href: `/organizations/${event.organization}`,
      });
    }

    if (event.event_repeater && event.event_repeater_name) {
      segments.push({
        type: 'event-series',
        label: event.event_repeater_name,
      });
    }

    segments.push({
      type: 'event',
      label: event.name,
    });

    return segments;
  }, [event]);

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

  // Check if user has a cancelled signup they can reinstate
  const myCancelledSignup = useMemo(
    () => {
      if (!signups || !currentUser?.pk) return undefined;
      return signups.find(
        (s) => Number(s.user) === Number(currentUser.pk) && s.status === 'cancelled'
      );
    },
    [signups, currentUser?.pk],
  );

  // Split signups into active and waitlisted
  const activeSignups = useMemo(
    () => (signups ?? []).filter((s) => !['waitlisted', 'tentative', 'cancelled', 'rejected'].includes(s.status)),
    [signups],
  );
  const tentativeSignups = useMemo(
    () => (signups ?? []).filter((s) => s.status === 'tentative'),
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
      ...(tentativeSignups.length > 0 ? [{ value: 'tentative', label: `${tentativeSignups.length} Tentative` }] : []),
      { value: 'waitlist', label: `${waitlistedSignups.length} Waitlist` },
      { value: 'discord', label: 'Discord' },
    ],
    [activeSignups.length, tentativeSignups.length, waitlistedSignups.length, isAdmin],
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
    <div className="max-w-7xl mx-auto py-4 md:py-8 px-4 md:px-6 space-y-5 md:space-y-8">
      {/* Breadcrumb */}
      {breadcrumbSegments.length > 1 && <EntityBreadcrumb segments={breadcrumbSegments} />}

      {/* Page Header */}
      <div className="space-y-4">
        {/* Row 1: Title (left) + Org/Series (right, lg+ only) */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
          <h1 className="text-xl sm:text-2xl lg:text-4xl font-bold min-w-0">
            {event.name}
          </h1>
          <div className="hidden lg:flex flex-wrap items-center gap-2 shrink-0">
            {event.organization_name && (
              <div className="flex flex-col items-center gap-0.5">
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Organization</span>
                <HighlightButton
                  size="sm"
                  onClick={() => navigate(`/organizations/${event.organization}`)}
                  avatarUrl={eventOrg?.logo || undefined}
                  avatarAlt={event.organization_name}
                >
                  {!eventOrg?.logo && <Building2 className="h-4 w-4 mr-1.5" />}
                  {event.organization_name}
                </HighlightButton>
              </div>
            )}
            {event.event_repeater && event.event_repeater_name && (
              <div className="flex flex-col items-center gap-0.5">
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Event Series</span>
                <HighlightButton
                  size="sm"
                  onClick={() => navigate(`/event-series/${event.event_repeater}`)}
                >
                  <Repeat className="h-4 w-4 mr-1.5" />
                  {event.event_repeater_name}
                </HighlightButton>
              </div>
            )}
          </div>
        </div>

        {/* Row 2: Status + Date */}
        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 text-muted-foreground">
          <EventStateBadge state={event.state} data-testid="event-state-badge" />
          <Badge variant="secondary" className="flex items-center gap-1 w-fit">
            <Clock className="h-3 w-3" />
            {formattedDate}
          </Badge>
        </div>

        {/* Row 3: Admin button group (left) + Subscribe/RSVP (right) */}
        {(isAdmin || (currentUser && event.state === EventState.SIGNUPS_OPEN && signups) || (currentUser && event.event_repeater)) && (
          <div className="flex items-center justify-between gap-3">
            {/* Admin actions — left side */}
            {isAdmin ? (
              <EventAdminActions
                event={event}
                actions={actions}
                onEditClick={() => setShowEditModal(true)}
                onStartRollCallClick={() => setShowRollCallConfirm(true)}
                onReopenSignupsClick={() => setShowReopenConfirm(true)}
                onOpenRollCallClick={() => navigate(`/rollcall/${eventId}`)}
                onDeleteConfirmed={() => {
                  actions.deleteEvent.mutate(undefined, { onSuccess: () => navigate('/events') });
                }}
              />
            ) : (
              <div />
            )}

            {/* Right side: Subscribe + RSVP */}
            <div className="flex items-center gap-2">
            {event.event_repeater && currentUser && (
              isSubscribed ? (
                <SecondaryButton
                  size="sm"
                  onClick={() => unsubscribeMutation.mutate()}
                  disabled={unsubscribeMutation.isPending}
                >
                  <BellOff className="h-4 w-4 mr-1" />
                  Unsubscribe
                </SecondaryButton>
              ) : (
                <PrimaryButton
                  size="sm"
                  onClick={() => subscribeMutation.mutate()}
                  disabled={subscribeMutation.isPending}
                >
                  <Bell className="h-4 w-4 mr-1" />
                  Subscribe
                </PrimaryButton>
              )
            )}
            {/* Not signed up — show Sign Up + Tentative */}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && !mySignup && !myCancelledSignup && (
              <>
                <PrimaryButton
                  size="sm"
                  onClick={() => setShowRsvpConfirm(true)}
                  disabled={rsvpMutation.isPending}
                  data-testid="event-rsvp-btn"
                >
                  <CheckCircle2 className="h-4 w-4 mr-1.5" />
                  Sign Up
                </PrimaryButton>
                <SecondaryButton
                  size="sm"
                  onClick={() => tentativeMutation.mutate()}
                  disabled={tentativeMutation.isPending}
                  data-testid="event-tentative-btn"
                >
                  <HelpCircle className="h-4 w-4 mr-1.5" />
                  <span className="hidden sm:inline">Tentative</span>
                </SecondaryButton>
              </>
            )}
            {/* Cancelled — can reinstate */}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && !mySignup && myCancelledSignup && (
              <>
                <SecondaryButton
                  size="sm"
                  onClick={() => signupActions.reinstate.mutate(myCancelledSignup.id)}
                  disabled={signupActions.reinstate.isPending}
                  data-testid="event-reinstate-btn"
                >
                  <Undo2 className="h-4 w-4 mr-1.5" />
                  Reinstate
                </SecondaryButton>
                <SecondaryButton
                  size="sm"
                  onClick={() => tentativeMutation.mutate()}
                  disabled={tentativeMutation.isPending}
                  data-testid="event-tentative-btn"
                >
                  <HelpCircle className="h-4 w-4 mr-1.5" />
                  <span className="hidden sm:inline">Tentative</span>
                </SecondaryButton>
              </>
            )}
            {/* Signed up (active) — show status + cancel */}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && mySignup && mySignup.status !== 'tentative' && (
              <DestructiveButton
                size="sm"
                onClick={() => setShowCancelRsvpConfirm(true)}
                loading={signupActions.cancel.isPending}
                depth={false}
                data-testid="event-cancel-rsvp-btn"
              >
                <XCircle className="h-4 w-4 mr-1.5" />
                Cancel RSVP
              </DestructiveButton>
            )}
            {/* Tentative — can upgrade to full signup or cancel */}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && mySignup && mySignup.status === 'tentative' && (
              <>
                <PrimaryButton
                  size="sm"
                  onClick={() => setShowRsvpConfirm(true)}
                  disabled={rsvpMutation.isPending}
                  data-testid="event-upgrade-rsvp-btn"
                >
                  <CheckCircle2 className="h-4 w-4 mr-1.5" />
                  Sign Up
                </PrimaryButton>
                <DestructiveButton
                  size="sm"
                  onClick={() => setShowCancelRsvpConfirm(true)}
                  loading={signupActions.cancel.isPending}
                  depth={false}
                  data-testid="event-cancel-tentative-btn"
                >
                  <XCircle className="h-4 w-4 mr-1.5" />
                  Cancel
                </DestructiveButton>
              </>
            )}
            </div>
          </div>
        )}
      </div>

      {/* Content Card — full width */}
      <div className="rounded-lg border border-border bg-base-200/50 p-4 md:p-8">
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList>
            <TabsTrigger value="details" data-testid="event-tab-details">
              Details
            </TabsTrigger>
            <TabsTrigger value="signups" data-testid="event-tab-signups">
              Signups ({activeSignups.length})
            </TabsTrigger>
            {tentativeSignups.length > 0 && (
              <TabsTrigger value="tentative" data-testid="event-tab-tentative">
                Tentative ({tentativeSignups.length})
              </TabsTrigger>
            )}
            <TabsTrigger value="waitlist" data-testid="event-tab-waitlist">
              Waitlist ({waitlistedSignups.length})
            </TabsTrigger>
            <TabsTrigger value="discord" data-testid="event-tab-discord">
              Discord
            </TabsTrigger>
          </TabsList>

          <TabsContent value="details">
            <DetailsTab event={event} />
            {isAdmin && event.event_repeater && (
              <div className="mt-4">
                <SubscriberList repeaterId={event.event_repeater} />
              </div>
            )}
          </TabsContent>

          <TabsContent value="signups">
            <SignupsTab
              signups={activeSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              gameType={event.game_type}
              eventId={event.id}
              orgId={event.organization}
              hasDiscordServer={!!eventOrg?.discord_server_id}
              state={event.state}
            />
          </TabsContent>

          <TabsContent value="tentative">
            <SignupsTab
              signups={tentativeSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              gameType={event.game_type}
              state={event.state}
            />
          </TabsContent>

          <TabsContent value="waitlist">
            <SignupsTab
              signups={waitlistedSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              gameType={event.game_type}
              state={event.state}
            />
          </TabsContent>

          <TabsContent value="discord">
            <DiscordLogSection eventId={event.id} isAdmin={isAdmin} eventTimezone={event.timezone} />
          </TabsContent>
        </Tabs>
      </div>

      <EditEventModal
        event={event}
        open={showEditModal}
        onOpenChange={setShowEditModal}
      />

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

      <ConfirmDialog
        open={showReopenConfirm}
        onOpenChange={setShowReopenConfirm}
        title="Reopen Signups"
        description={`Reopen signups for "${event.name}" and allow new RSVPs? Existing confirmations will be kept and no announcement will be sent.`}
        confirmLabel="Reopen Signups"
        variant="warning"
        isLoading={actions.reopenSignups.isPending}
        onConfirm={async () => {
          try {
            await actions.reopenSignups.mutateAsync();
            toast.success('Signups reopened');
          } catch (err: unknown) {
            const message = extractApiError(err);
            toast.error(message || 'Failed to reopen signups');
          }
        }}
      />
    </div>
  );
}

/** Details tab showing event configuration */
function DetailsTab({ event }: { event: NonNullable<ReturnType<typeof useEvent>['data']> }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
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
            <span className="capitalize">{event.tournament_type.replace(/_/g, ' ')}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Draft</span>
            <span className="capitalize">{event.draft_type}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Teams</span>
            <span>{event.number_of_teams} x {event.people_per_team}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Game</span>
            <span>{event.game_type === 1 ? 'Dota 2' : 'Deadlock'}</span>
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
        <Card className="md:col-span-2 lg:col-span-1">
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
  gameType,
  eventId,
  orgId,
  hasDiscordServer,
  state,
}: {
  signups: EventSignupType[];
  isAdmin: boolean;
  signupActions: ReturnType<typeof useSignupActionMutations>;
  gameType: number;
  eventId?: number;
  orgId?: number;
  hasDiscordServer?: boolean;
  state: EventType['state'];
}) {
  const [approvalSignup, setApprovalSignup] = useState<EventSignupType | null>(null);
  const [removeSignup, setRemoveSignup] = useState<{ signup: EventSignupType; name: string } | null>(null);
  const [addUserOpen, setAddUserOpen] = useState(false);
  const queryClient = useQueryClient();

  const userPks = useMemo(() => signups.map((s) => s.user), [signups]);
  const resolvedUsers = useResolvedUsers(userPks);
  const userMap = useMemo(
    () => new Map(resolvedUsers.map((u) => [u.pk, u])),
    [resolvedUsers],
  );

  const signupUserPks = useMemo(() => new Set(signups.map((s) => s.user)), [signups]);
  const entityContext = useMemo(() => ({ orgId }), [orgId]);
  const handleAddUser = useCallback(async (payload: { user_id: number }) => {
    const resp = await adminAddSignup(eventId!, payload.user_id);
    queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
    // Backend now adds the user as an OrgUser when admin signs them up; reset
    // the org-users cache so the org page reflects the new membership.
    if (orgId) useOrgStore.getState().clearOrgUsers();
    return resp;
  }, [eventId, orgId, queryClient]);
  const checkIsAdded = useCallback((user: { pk: number }) => signupUserPks.has(user.pk), [signupUserPks]);

  return (
    <div className="space-y-3">
      {isAdmin && eventId && (state === EventState.SIGNUPS_OPEN || state === EventState.ROLL_CALL) && (
        <div className="flex justify-end">
          <PrimaryButton
            size="sm"
            onClick={() => setAddUserOpen(true)}
            data-testid="admin-add-signup-btn"
          >
            <UserPlus className="h-4 w-4 mr-1" />
            Add User
          </PrimaryButton>
          {addUserOpen && (
            <AddUserModal
              open={addUserOpen}
              onOpenChange={setAddUserOpen}
              title="Add User to Event"
              entityContext={entityContext}
              onAdd={handleAddUser}
              isAdded={checkIsAdded}
              hasDiscordServer={!!hasDiscordServer}
            />
          )}
        </div>
      )}
      {signups.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <Users className="w-12 h-12 mb-3 opacity-50" />
          <p>No signups yet</p>
        </div>
      )}
      <div className="space-y-1.5">
      {signups.map((signup, index) => {
        const user = userMap.get(signup.user);
        const position = signup.waitlist_position ?? index + 1;

        const adminActions = isAdmin ? (
          <div className="flex gap-1">
            {(signup.status === 'rsvp' || signup.status === 'pending_approval') && (
              <>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton color="green" size="sm"
                      onClick={() => gameType === GameType.DOTA2 ? setApprovalSignup(signup) : signupActions.approve.mutate({ id: signup.id })}
                      disabled={signupActions.approve.isPending}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Approve</span>
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">Approve</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DestructiveButton size="sm" onClick={() => signupActions.demote.mutate(signup.id)} loading={signupActions.demote.isPending} depth={false}>
                      <ArrowDownToLine className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Waitlist</span>
                    </DestructiveButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">Waitlist</TooltipContent>
                </Tooltip>
              </>
            )}
            {signup.status === 'approved' && (
              <>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton color="blue" size="sm" onClick={() => signupActions.confirm.mutate(signup.id)} disabled={signupActions.confirm.isPending}>
                      <UserCheck className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Confirm</span>
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">Confirm</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DestructiveButton size="sm" onClick={() => signupActions.demote.mutate(signup.id)} loading={signupActions.demote.isPending} depth={false}>
                      <ArrowDownToLine className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Waitlist</span>
                    </DestructiveButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">Waitlist</TooltipContent>
                </Tooltip>
              </>
            )}
            {signup.status === 'confirmed' && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <SecondaryButton color="orange" size="sm" onClick={() => signupActions.unconfirm.mutate(signup.id)} disabled={signupActions.unconfirm.isPending}>
                    <Undo2 className="h-3.5 w-3.5" />
                    <span className="hidden lg:inline ml-1">Unconfirm</span>
                  </SecondaryButton>
                </TooltipTrigger>
                <TooltipContent className="lg:hidden">Unconfirm</TooltipContent>
              </Tooltip>
            )}
            {signup.status === 'waitlisted' && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <SecondaryButton color="green" size="sm"
                    onClick={() => gameType === GameType.DOTA2 ? setApprovalSignup(signup) : signupActions.approve.mutate({ id: signup.id })}
                    disabled={signupActions.approve.isPending}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span className="hidden lg:inline ml-1">Approve</span>
                  </SecondaryButton>
                </TooltipTrigger>
                <TooltipContent className="lg:hidden">Approve</TooltipContent>
              </Tooltip>
            )}
            {signup.status !== 'cancelled' && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <DestructiveButton size="sm" depth={false}
                    onClick={() => {
                      const name = user ? (user.nickname || user.username) : `User #${signup.user}`;
                      setRemoveSignup({ signup, name });
                    }}
                  >
                    <UserX className="h-3.5 w-3.5" />
                    <span className="hidden lg:inline ml-1">Remove</span>
                  </DestructiveButton>
                </TooltipTrigger>
                <TooltipContent className="lg:hidden">Remove user</TooltipContent>
              </Tooltip>
            )}
          </div>
        ) : undefined;

        const statusSlot = (
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">#{position}</span>
            <EventStateBadge state={signup.status} />
          </div>
        );

        if (user) {
          // Prefer the org-approved MMR via the user entity adapter
          // (UserEntry.orgData[orgId].mmr) over self-reported dota_profile.mmr.
          // Fall back to signup.org_user_mmr from the API if the cache is cold.
          const baseProfile = signup.dota_profile as DotaProfileData | null;
          const orgMmr =
            (orgId && isUserEntry(user) ? user.orgData[orgId]?.mmr : undefined) ??
            signup.org_user_mmr ??
            null;
          const stripProfile = baseProfile
            ? { ...baseProfile, mmr: orgMmr ?? baseProfile.mmr }
            : orgMmr != null
              ? ({
                  positions: { pos_1: false, pos_2: false, pos_3: false, pos_4: false, pos_5: false },
                  rank_status: 'never',
                  rank_medal: null,
                  mmr: orgMmr,
                  rank_screenshot: null,
                  battlecup_screenshot: null,
                  battle_cup_tier: null,
                } as DotaProfileData)
              : null;
          return (
            <UserEventStrip
              key={signup.id}
              user={user}
              dotaProfile={stripProfile}
              contextSlot={statusSlot}
              actionSlot={adminActions}
            />
          );
        }

        // Fallback for signups not yet in cache
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
      <MmrApprovalModal
        signup={approvalSignup}
        open={!!approvalSignup}
        onOpenChange={(open) => { if (!open) setApprovalSignup(null); }}
        onApprove={(signupId, mmr) => {
          const previousMmr = approvalSignup?.org_user_mmr ?? null;
          const playerName =
            approvalSignup?.user_data?.username ??
            approvalSignup?.username ??
            `User #${approvalSignup?.user ?? signupId}`;
          signupActions.approve.mutate({ id: signupId, mmr }, {
            onSuccess: () => {
              setApprovalSignup(null);
              if (orgId) useOrgStore.getState().clearOrgUsers();
              if (previousMmr != null && previousMmr !== mmr) {
                const delta = mmr - previousMmr;
                toast.success(
                  `Approved ${playerName} — MMR ${previousMmr.toLocaleString()} → ${mmr.toLocaleString()} (${delta > 0 ? '+' : ''}${delta.toLocaleString()})`,
                );
              } else if (previousMmr == null) {
                toast.success(`Approved ${playerName} at MMR ${mmr.toLocaleString()}`);
              } else {
                toast.success(`Approved ${playerName} (MMR unchanged at ${mmr.toLocaleString()})`);
              }
            },
          });
        }}
        isApproving={signupActions.approve.isPending}
        isRejecting={signupActions.reject.isPending}
        onReject={(signupId) => {
          const playerName =
            approvalSignup?.user_data?.username ??
            approvalSignup?.username ??
            `User #${approvalSignup?.user ?? signupId}`;
          signupActions.reject.mutate(signupId, {
            onSuccess: () => {
              setApprovalSignup(null);
              toast.success(`Rejected signup for ${playerName}`);
            },
            onError: () => toast.error(`Failed to reject ${playerName}`),
          });
        }}
      />
      <ConfirmDialog
        open={!!removeSignup}
        onOpenChange={(open) => { if (!open) setRemoveSignup(null); }}
        title="Remove User"
        description={`Remove ${removeSignup?.name ?? 'this user'} from the event? They will lose their signup position and need to re-sign up.`}
        confirmLabel="Remove"
        variant="destructive"
        isLoading={signupActions.cancel.isPending}
        onConfirm={() => {
          if (removeSignup) {
            signupActions.cancel.mutate(removeSignup.signup.id, {
              onSuccess: () => setRemoveSignup(null),
            });
          }
        }}
      />
    </div>
  );
}
