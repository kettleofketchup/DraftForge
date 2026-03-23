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
  Building2,
  Loader2,
  Users,
  Clock,
  CheckCircle2,
  XCircle,
  Trash2,
  UserCheck,
  UserX,
  Pencil,
  ShieldAlert,
  ArrowDownToLine,
  Undo2,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '~/components/ui/badge';
import { EventStateBadge } from '~/components/events';
import { SubscriberList } from '~/components/events/SubscriberList';
import { EventState, GameType } from '~/components/events/schemas';
import { MmrApprovalModal } from '~/components/events/MmrApprovalModal';
import { DiscordLogSection } from '~/components/events/DiscordLogSection';
import { EditEventModal } from '~/components/events/EditEventModal';
import type { EventSignupType } from '~/components/events/schemas';
import { PrimaryButton, SecondaryButton, DestructiveButton, HighlightButton } from '~/components/ui/buttons';
import { BrandDropdownMenu, type BrandDropdownAction } from '~/components/ui/brand-dropdown-menu';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { UserEventStrip } from '~/components/user';
import type { DotaProfileData } from '~/components/user';
import {
  useEvent,
  useEventSignups,
  useEventSignupUsers,
  useRsvpMutation,
  useEventActionMutation,
  useSignupActionMutations,
} from '~/hooks/useEvent';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { useOrganization } from '~/components/organization';
import { useIsOrganizationStaff } from '~/hooks/usePermissions';
import { usePageNav } from '~/hooks/usePageNav';
import { useUserStore } from '~/store/userStore';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { EntityBreadcrumb, type BreadcrumbSegment } from '~/components/ui/entity-breadcrumb';

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
  const [showRsvpConfirm, setShowRsvpConfirm] = useState(false);
  const [showCancelRsvpConfirm, setShowCancelRsvpConfirm] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);

  // Permission check - fetch the specific org for this event
  const { organization: eventOrg } = useOrganization(event?.organization ?? undefined);
  const isAdmin = useIsOrganizationStaff(eventOrg);

  // Mutations
  const rsvpMutation = useRsvpMutation(id ?? 0);
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);

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
      { value: 'discord', label: 'Discord' },
    ],
    [activeSignups.length, waitlistedSignups.length, isAdmin],
  );

  usePageNav(event ? pageNavOptions : null, activeTab, handleTabChange);

  // Build admin actions for mobile dropdown — must be before early returns
  const adminActions = useMemo((): BrandDropdownAction[] => {
    if (!isAdmin || !event) return [];
    const items: BrandDropdownAction[] = [
      {
        key: 'edit',
        icon: <Pencil className="h-4 w-4 mr-1.5" />,
        label: 'Edit',
        onClick: () => setShowEditModal(true),
        variant: 'success',
        'data-testid': 'event-edit-btn',
      },
    ];

    if (event.state === EventState.UPCOMING) {
      items.push({
        key: 'open-signups',
        icon: <Users className="h-4 w-4 mr-1.5" />,
        label: 'Open Signups',
        onClick: () => actions.openSignups.mutate(),
        variant: 'primary',
        disabled: actions.openSignups.isPending,
        'data-testid': 'event-open-signups-btn',
      });
    }

    if (event.state === EventState.SIGNUPS_OPEN) {
      items.push({
        key: 'start-rollcall',
        icon: <Clock className="h-4 w-4 mr-1.5" />,
        label: 'Start Roll Call',
        onClick: () => setShowRollCallConfirm(true),
        variant: 'primary',
        disabled: actions.startRollCall.isPending,
        'data-testid': 'event-start-rollcall-btn',
      });
    }

    if (event.state === EventState.ROLL_CALL) {
      items.push({
        key: 'open-rollcall',
        icon: <CheckCircle2 className="h-4 w-4 mr-1.5" />,
        label: 'Open Roll Call',
        onClick: () => navigate(`/rollcall/${eventId}`),
        variant: 'primary',
        'data-testid': 'event-start-tournament-btn',
      });
    }

    if (event.state !== EventState.COMPLETED && event.state !== EventState.CANCELLED) {
      items.push({
        key: 'cancel',
        icon: <XCircle className="h-4 w-4 mr-1.5" />,
        label: 'Cancel',
        onClick: () => actions.cancelEvent.mutate(),
        variant: 'destructive',
        disabled: actions.cancelEvent.isPending,
        'data-testid': 'event-cancel-btn',
      });
    }

    items.push({
      key: 'delete',
      icon: <Trash2 className="h-4 w-4 mr-1.5" />,
      label: 'Delete',
      onClick: () => {
        if (window.confirm('Are you sure you want to permanently delete this event? This cannot be undone.')) {
          actions.deleteEvent.mutate(undefined, {
            onSuccess: () => navigate(`/organizations/${event.organization}/events`),
          });
        }
      },
      variant: 'destructive',
      disabled: actions.deleteEvent.isPending,
      'data-testid': 'event-delete-btn',
    });

    return items;
  }, [isAdmin, event?.state, event?.organization, actions, eventId, navigate]);

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
        {/* Row 1: Title (left) + Org (right on md+) */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h1 className="text-xl sm:text-2xl lg:text-4xl font-bold min-w-0">
            {event.name}
          </h1>
          {event.organization_name && (
            <HighlightButton
              size="sm"
              onClick={() => navigate(`/organizations/${event.organization}`)}
              avatarUrl={eventOrg?.logo || undefined}
              avatarAlt={event.organization_name}
              className="shrink-0"
            >
              {!eventOrg?.logo && <Building2 className="h-4 w-4 mr-1.5" />}
              {event.organization_name}
            </HighlightButton>
          )}
        </div>

        {/* Row 2: Status + Date */}
        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 text-muted-foreground">
          <EventStateBadge state={event.state} />
          <Badge variant="secondary" className="flex items-center gap-1 w-fit">
            <Clock className="h-3 w-3" />
            {formattedDate}
          </Badge>
        </div>

        {/* Row 3: Admin button group (left) + RSVP (right) */}
        {(isAdmin || (currentUser && event.state === EventState.SIGNUPS_OPEN && signups)) && (
          <div className="flex items-center justify-between gap-3">
            {/* Admin actions — left side */}
            {isAdmin ? (
              <>
                {/* Desktop: button group */}
                <div className="hidden md:inline-flex items-center rounded-lg overflow-hidden shadow-lg shadow-black/20 [&_[data-slot=button]]:rounded-none [&_[data-slot=button]]:shadow-none [&_[data-slot=button]]:border-b-0">
                  <SecondaryButton
                    color="emerald"
                    size="sm"
                    onClick={() => setShowEditModal(true)}
                    title="Edit settings"
                    data-testid="event-edit-btn"
                  >
                    <Pencil className="h-4 w-4 mr-1.5" />
                    Edit
                  </SecondaryButton>

                  {event.state === EventState.UPCOMING && (
                    <SecondaryButton
                      color="green"
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
                      onClick={() => setShowRollCallConfirm(true)}
                      disabled={actions.startRollCall.isPending}
                      data-testid="event-start-rollcall-btn"
                    >
                      Start Roll Call
                    </SecondaryButton>
                  )}

                  {event.state === EventState.ROLL_CALL && (
                    <PrimaryButton
                      size="sm"
                      onClick={() => navigate(`/rollcall/${eventId}`)}
                      data-testid="event-start-tournament-btn"
                    >
                      Open Roll Call
                    </PrimaryButton>
                  )}

                  {event.state !== EventState.COMPLETED &&
                    event.state !== EventState.CANCELLED && (
                      <DestructiveButton
                        size="sm"
                        onClick={() => actions.cancelEvent.mutate()}
                        loading={actions.cancelEvent.isPending}
                        depth={false}
                        className="bg-gradient-to-r from-red-700/80 to-violet-900/80 hover:from-red-600/80 hover:to-violet-800/80"
                        data-testid="event-cancel-btn"
                      >
                        <XCircle className="h-4 w-4 mr-1.5" />
                        Cancel
                      </DestructiveButton>
                    )}

                  <DestructiveButton
                    size="sm"
                    onClick={() => {
                      if (window.confirm('Are you sure you want to permanently delete this event? This cannot be undone.')) {
                        actions.deleteEvent.mutate(undefined, {
                          onSuccess: () => navigate(`/organizations/${event.organization}/events`),
                        });
                      }
                    }}
                    loading={actions.deleteEvent.isPending}
                    depth={false}
                    className="bg-gradient-to-r from-red-700/80 to-violet-900/80 hover:from-red-600/80 hover:to-violet-800/80"
                    data-testid="event-delete-btn"
                  >
                    <Trash2 className="h-4 w-4 mr-1.5" />
                    Delete
                  </DestructiveButton>
                </div>

                {/* Mobile: labeled dropdown */}
                <div className="md:hidden">
                  <BrandDropdownMenu
                    label="Admin"
                    icon={<ShieldAlert className="h-4 w-4 mr-1.5" />}
                    actions={adminActions}
                    variant="admin"
                    data-testid="event-admin-actions-mobile"
                  />
                </div>
              </>
            ) : (
              <div />
            )}

            {/* RSVP — right side, always inline */}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && !mySignup && !myCancelledSignup && (
              <PrimaryButton
                size="sm"
                onClick={() => setShowRsvpConfirm(true)}
                disabled={rsvpMutation.isPending}
                data-testid="event-rsvp-btn"
              >
                <Users className="h-4 w-4 mr-1.5" />
                RSVP
              </PrimaryButton>
            )}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && !mySignup && myCancelledSignup && (
              <SecondaryButton
                size="sm"
                onClick={() => signupActions.reinstate.mutate(myCancelledSignup.id)}
                disabled={signupActions.reinstate.isPending}
                data-testid="event-reinstate-btn"
              >
                <Undo2 className="h-4 w-4 mr-1.5" />
                Reinstate RSVP
              </SecondaryButton>
            )}
            {currentUser && event.state === EventState.SIGNUPS_OPEN && signups && mySignup && (
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
            <TabsTrigger value="waitlist" data-testid="event-tab-waitlist">
              Waitlist ({waitlistedSignups.length})
            </TabsTrigger>
            <TabsTrigger value="discord" data-testid="event-tab-discord">
              Discord
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
              gameType={event.game_type}
            />
          </TabsContent>

          <TabsContent value="waitlist">
            <SignupsTab
              signups={waitlistedSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              gameType={event.game_type}
            />
          </TabsContent>

          <TabsContent value="discord">
            <DiscordLogSection eventId={event.id} />
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

      {event.event_repeater && (
        <div className="md:col-span-2 lg:col-span-3">
          <SubscriberList repeaterId={event.event_repeater} />
        </div>
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
}: {
  signups: EventSignupType[];
  isAdmin: boolean;
  signupActions: ReturnType<typeof useSignupActionMutations>;
  gameType: number;
}) {
  const [approvalSignup, setApprovalSignup] = useState<EventSignupType | null>(null);

  const userPks = useMemo(() => signups.map((s) => s.user), [signups]);
  const resolvedUsers = useResolvedUsers(userPks);
  const userMap = useMemo(
    () => new Map(resolvedUsers.map((u) => [u.pk, u])),
    [resolvedUsers],
  );

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
        const user = userMap.get(signup.user);
        const position = signup.waitlist_position ?? index + 1;

        const adminActions = isAdmin ? (
          <div className="flex gap-1">
            {/* RSVP / Pending Approval → Approve or Reject */}
            {(signup.status === 'rsvp' || signup.status === 'pending_approval') && (
              <>
                <SecondaryButton
                  color="green"
                  size="sm"
                  onClick={() =>
                    gameType === GameType.DOTA2
                      ? setApprovalSignup(signup)
                      : signupActions.approve.mutate({ id: signup.id })
                  }
                  disabled={signupActions.approve.isPending}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline ml-1">Approve</span>
                </SecondaryButton>
                <DestructiveButton
                  size="sm"
                  onClick={() => signupActions.demote.mutate(signup.id)}
                  loading={signupActions.demote.isPending}
                  depth={false}
                >
                  <ArrowDownToLine className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline ml-1">Waitlist</span>
                </DestructiveButton>
              </>
            )}
            {/* Approved → Confirm or Demote to waitlist */}
            {signup.status === 'approved' && (
              <>
                <SecondaryButton
                  color="blue"
                  size="sm"
                  onClick={() => signupActions.confirm.mutate(signup.id)}
                  disabled={signupActions.confirm.isPending}
                >
                  <UserCheck className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline ml-1">Confirm</span>
                </SecondaryButton>
                <DestructiveButton
                  size="sm"
                  onClick={() => signupActions.demote.mutate(signup.id)}
                  loading={signupActions.demote.isPending}
                  depth={false}
                >
                  <ArrowDownToLine className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline ml-1">Waitlist</span>
                </DestructiveButton>
              </>
            )}
            {/* Confirmed → Unconfirm (back to approved) */}
            {signup.status === 'confirmed' && (
              <SecondaryButton
                color="orange"
                size="sm"
                onClick={() => signupActions.unconfirm.mutate(signup.id)}
                disabled={signupActions.unconfirm.isPending}
              >
                <Undo2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline ml-1">Unconfirm</span>
              </SecondaryButton>
            )}
            {/* Waitlisted → Approve (promote from waitlist) */}
            {signup.status === 'waitlisted' && (
              <SecondaryButton
                color="green"
                size="sm"
                onClick={() =>
                  gameType === GameType.DOTA2
                    ? setApprovalSignup(signup)
                    : signupActions.approve.mutate({ id: signup.id })
                }
                disabled={signupActions.approve.isPending}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline ml-1">Approve</span>
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

        if (user) {
          return (
            <UserEventStrip
              key={signup.id}
              user={user}
              dotaProfile={signup.dota_profile as DotaProfileData | null}
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
    </div>
  );
}
