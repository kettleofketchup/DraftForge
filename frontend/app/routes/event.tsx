import { useNavigate, useParams } from 'react-router';
import { getEvent } from '~/components/api/api';
import { generateMeta } from '~/lib/seo';
import type { EventSSR } from '~/lib/ssr-types';
import type { Route } from './+types/event';

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

import {
  ArrowDownToLine,
  Bell,
  BellOff,
  Building2,
  CheckCircle2,
  Clock,
  Loader2,
  Repeat,
  RotateCcw,
  Undo2,
  UserCheck,
  UserPlus,
  Users,
  UserX,
} from 'lucide-react';
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { toast } from 'sonner';

import { useQueryClient } from '@tanstack/react-query';
import type { AddMemberPayload } from '~/components/api/api';
import { isStaffReasonRequiredError } from '~/components/api/overridesAPI';
import { EventStateBadge } from '~/components/events';
import { DiscordLogSection } from '~/components/events/DiscordLogSection';
import { EditEventModal } from '~/components/events/EditEventModal';
import { EventAdminActions } from '~/components/events/EventAdminActions';
import { EventOpsNoticesSlot } from '~/components/events/EventOpsNoticesSlot';
import { EventSignupModal } from '~/components/events/EventSignupModal';
import { evaluateSignupGap } from '~/components/events/EventSignupModal/evaluateSignupGap';
import { EventStaffSection } from '~/components/events/EventStaffCard';
import { MmrApprovalModal } from '~/components/events/MmrApprovalModal';
import { MySignupActions } from '~/components/events/MySignupActions';
import { OverrideWarningDialog } from '~/components/events/OverrideWarningDialog';
import { SignupHistorySection } from '~/components/events/SignupHistorySection';
import {
  historySubjectFor,
  SignupHistoryButton,
  SignupHistorySheet,
} from '~/components/events/SignupHistorySheet';
import { SignupInLineSince } from '~/components/events/SignupInLineSince';
import { StaffReasonDialog } from '~/components/events/StaffReasonDialog';
import { SubscriberList } from '~/components/events/SubscriberList';
import { canCompleteEvent } from '~/components/events/eventCompletion';
import {
  eventTabOptions,
  resolveEventTab,
} from '~/components/events/eventTabs';
import type {
  EventSignupType,
  EventType,
  HistorySubject,
  StaffReasonPolicy,
} from '~/components/events/schemas';
import { EventState, rollCallLabel } from '~/components/events/schemas';
import {
  canRestoreSignup,
  canVoidWithdrawal,
  isRemovedSignup,
  partitionSignups,
} from '~/components/events/signupPartitions';
import { signupRowMmr } from '~/components/events/signupRowMmr';
import { rollCallSummary } from '~/components/events/signupRules';
import { staffReasonMode } from '~/components/events/staffReasonPolicy';
import {
  signupHoldReason,
  signupSuccessMessage,
} from '~/components/events/unmetRequirements';
import { useSignupOverride } from '~/components/events/useSignupOverride';
import { useStaffAction } from '~/components/events/useStaffAction';
import {
  GAME_LABEL,
  isGameType,
  toGameType,
} from '~/components/game/constants';
import { EventLobbyPassword } from '~/components/lobby/EventLobbyPassword';
import { useOrganization } from '~/components/organization';
import {
  orgUsersQueryKey,
  useOrgUsersQuery,
} from '~/components/organization/hooks/useOrgUsersQuery';
import type { OrganizationType } from '~/components/organization/schemas';
import { Badge } from '~/components/ui/badge';
import {
  DestructiveButton,
  HighlightButton,
  PrimaryButton,
  SecondaryButton,
} from '~/components/ui/buttons';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { ConfirmDialog } from '~/components/ui/dialogs';
import {
  EntityBreadcrumb,
  type BreadcrumbSegment,
} from '~/components/ui/entity-breadcrumb';
import { PageHeader } from '~/components/ui/page-header';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import type { DotaProfileData } from '~/components/user';
import { UserEventStrip } from '~/components/user';
import { AddUserModal } from '~/components/user/AddUserModal';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';
import {
  ConductBadge,
  EventConductSection,
  useEventConduct,
  type ConductMemberLookup,
} from '~/features/conduct';
import {
  EventLeadershipBanner,
  EventLeadershipSection,
} from '~/features/leadership';
import {
  removeFeatureQueries,
  useOrgFeatureAccess,
} from '~/features/org-features';
import { canPromoteEvent, PromoteEventButton } from '~/features/promotion';
import {
  removeSignupHistoryQueries,
  useEvent,
  useEventActionMutation,
  useEventRepeater,
  useEventSignups,
  useEventSignupUsers,
  useRepeaterSubscriptionMutation,
  useSignupActionMutations,
  useSignupMutation,
} from '~/hooks/useEvent';
import { useContextGameType, useProvideGameType } from '~/hooks/useGameType';
import { useMemberAccess } from '~/hooks/useMemberAccess';
import { usePageNav } from '~/hooks/usePageNav';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { useUserDotaProfile } from '~/hooks/useUserProfile';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

const log = getLogger('EventPage');

export default function EventPage() {
  const { eventId, tab } = useParams<{ eventId: string; tab?: string }>();
  const navigate = useNavigate();
  const id = eventId ? parseInt(eventId, 10) : null;

  const { data: event, isLoading, error } = useEvent(id);
  const { data: signups } = useEventSignups(id);
  useEventSignupUsers(signups, undefined, toGameType(event?.game_type));
  const currentUser = useUserStore((state) => state.currentUser);

  const [activeTab, setActiveTab] = useState(tab || 'details');
  const [showRollCallConfirm, setShowRollCallConfirm] = useState(false);
  const [showReopenConfirm, setShowReopenConfirm] = useState(false);
  const [showCancelRsvpConfirm, setShowCancelRsvpConfirm] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [signupModal, setSignupModal] = useState<{
    open: boolean;
    intent: 'rsvp' | 'tentative';
  }>({
    open: false,
    intent: 'rsvp',
  });

  // Fetch the specific org for this event (needed for org logo and discord server id)
  const { organization: eventOrg, refetch: refetchEventOrg } = useOrganization(
    event?.organization ?? undefined,
  );
  // Permission check uses backend-derived flag (covers org staff AND league staff).
  const isAdmin = event?.user_can_manage ?? false;
  const eventOrgAccess = useOrgFeatureAccess(eventOrg ?? undefined);
  const canComplete = canCompleteEvent(event, eventOrgAccess);
  const { memberFor: conductMemberFor } = useEventConduct(
    event,
    eventOrg,
    eventOrgAccess,
  );
  const showCompletePointsNote =
    eventOrgAccess.canViewContributions ||
    eventOrgAccess.canManageContributions;

  useProvideGameType(event ? toGameType(event.game_type) : null);

  // Mutations
  const queryClient = useQueryClient();

  // Populate the org users cache so signup rows read per-org MMR via
  // selectOrgMmr; viewers without member access fall back to signup.org_user_mmr.
  const eventOrgPk = event?.organization ?? null;
  const onMemberViewerChange = useCallback(() => {
    if (id) removeSignupHistoryQueries(queryClient, id);
    if (!eventOrgPk) return;
    // Remove, not reset: this runs before useQuery applies enabled=false, so a
    // reset would refetch the members list as the new (possibly anonymous) viewer.
    queryClient.removeQueries({ queryKey: orgUsersQueryKey(eventOrgPk) });
    useUserCacheStore.getState().dropScoped({ orgId: eventOrgPk });
    removeFeatureQueries(queryClient, eventOrgPk);
    queryClient.invalidateQueries({ queryKey: ['event', id] });
    queryClient.invalidateQueries({ queryKey: ['event-signups', id] });
    refetchEventOrg();
  }, [eventOrgPk, id, queryClient, refetchEventOrg]);
  const { canView: canViewOrgMembers, settled: orgMemberAccessSettled } =
    useMemberAccess(eventOrg, onMemberViewerChange);
  useOrgUsersQuery(eventOrgPk, {
    enabled: orgMemberAccessSettled && !!canViewOrgMembers,
  });
  const signupMutation = useSignupMutation(id ?? 0);
  const actions = useEventActionMutation(id ?? 0);
  const signupActions = useSignupActionMutations(id ?? 0);

  // Fresh dota profile for the skip-the-form fast path. Profiles are org-scoped
  // (PlayerDotaProfile hangs off OrgUser), so the hook needs the event's org.
  // Backed by GET /api/organizations/<orgId>/my-dota-profile/. The signup
  // mutation invalidates this query on success so the next read is fresh.
  // Disabled until the event loads; the hook returns isPending until then,
  // which we use below for trigger gating.
  const profileQuery = useUserDotaProfile(currentUser?.pk, event?.organization);
  const profile = profileQuery.data;
  const profileLoaded =
    profileQuery.status === 'success' || profileQuery.status === 'error';

  // Signup trigger: fast-path mutate when the cached profile satisfies the
  // event's requirements; otherwise open the modal. On fast-path failure,
  // refetch the profile and re-evaluate — if the server now sees a gap, open
  // the modal; otherwise surface the error as a toast.
  const trySignup = useCallback(
    async (intent: 'rsvp' | 'tentative') => {
      if (!event) return;
      const steamGate = { steamAccountId: currentUser?.steam_account_id };
      const gap = evaluateSignupGap(event, profile, steamGate);
      const errorMsg =
        intent === 'rsvp' ? 'Failed to sign up' : 'Failed to mark tentative';
      if (gap === 'complete') {
        try {
          const created = await signupMutation.mutateAsync({
            intent,
            profile: {},
          });
          toast.success(signupSuccessMessage(intent, created?.status));
        } catch (err) {
          const refreshed = await profileQuery.refetch();
          const newGap = event
            ? evaluateSignupGap(event, refreshed.data, steamGate)
            : 'complete';
          if (newGap !== 'complete') {
            setSignupModal({ open: true, intent });
          } else {
            toast.error(extractApiError(err) || errorMsg);
          }
        }
      } else {
        setSignupModal({ open: true, intent });
      }
    },
    [
      event,
      profile,
      profileQuery,
      signupMutation,
      currentUser?.steam_account_id,
    ],
  );

  // Repeater subscription state
  const repeaterId = event?.event_repeater;
  const { data: repeaterData } = useEventRepeater(
    repeaterId && currentUser ? repeaterId : null,
  );
  const isSubscribed = repeaterData?.is_subscribed ?? false;

  const { subscribe: subscribeMutation, unsubscribe: unsubscribeMutation } =
    useRepeaterSubscriptionMutation();

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

  const mySignup = useMemo(() => {
    if (!signups || !currentUser?.pk) return undefined;
    return signups.find(
      (s) =>
        Number(s.user) === Number(currentUser.pk) &&
        s.status !== 'cancelled' &&
        s.status !== 'rejected',
    );
  }, [signups, currentUser?.pk]);

  const {
    active: activeSignups,
    tentative: tentativeSignups,
    waitlisted: waitlistedSignups,
    removed: removedSignups,
  } = useMemo(() => partitionSignups(signups ?? []), [signups]);

  const handleTabChange = useCallback(
    (newTab: string) => {
      setActiveTab(newTab);
      navigate(`/events/${eventId}/${newTab}`);
    },
    [eventId, navigate],
  );

  // Mobile tab nav goes through usePageNav → centered navbar dropdown.
  const pageNavOptions = useMemo(
    () =>
      eventTabOptions(isAdmin, {
        active: activeSignups.length,
        tentative: tentativeSignups.length,
        waitlisted: waitlistedSignups.length,
        removed: removedSignups.length,
      }),
    [
      isAdmin,
      activeSignups.length,
      tentativeSignups.length,
      waitlistedSignups.length,
      removedSignups.length,
    ],
  );
  const shownTab = event ? resolveEventTab(activeTab, isAdmin) : activeTab;
  usePageNav(event ? pageNavOptions : null, shownTab, handleTabChange);

  const [historyFor, setHistoryFor] = useState<HistorySubject | null>(null);
  const historyMemberOptions = useMemo(() => {
    const byUser = new Map<number, EventSignupType>();
    for (const s of signups ?? []) byUser.set(s.user, s);
    return [...byUser.values()].map((s) => ({
      user_id: s.user,
      user: historySubjectFor(s),
    }));
  }, [signups]);

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
  // Compact format so the date pill fits next to the state badge at 375px.
  const shortDate = scheduledDate.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
  const endDate = event.ends_at ? new Date(event.ends_at) : null;
  const endSameDay =
    endDate !== null && endDate.toDateString() === scheduledDate.toDateString();
  const formattedEnd = endDate
    ? endDate.toLocaleString(
        undefined,
        endSameDay
          ? { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }
          : {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
              timeZoneName: 'short',
            },
      )
    : null;

  return (
    <div className="max-w-7xl mx-auto py-4 md:py-8 px-4 md:px-6 space-y-5 md:space-y-8">
      {/* Breadcrumb */}
      {breadcrumbSegments.length > 1 && (
        <EntityBreadcrumb segments={breadcrumbSegments} />
      )}

      {/* Page Header — compact on mobile, lg+ adds an Org/Series side rail */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <PageHeader
          title={event.name}
          badge={
            <EventStateBadge
              state={event.state}
              data-testid="event-state-badge"
            />
          }
          subtitle={
            <Badge
              variant="secondary"
              className="flex items-center gap-1 w-fit text-xs sm:text-sm"
            >
              <Clock className="h-3 w-3" />
              <span className="sm:hidden">{shortDate}</span>
              <span className="hidden sm:inline">{formattedDate}</span>
              {formattedEnd && (
                <span
                  data-testid="event-end-time"
                  className={endSameDay ? undefined : 'hidden sm:inline'}
                >
                  – {formattedEnd}
                </span>
              )}
            </Badge>
          }
          className="lg:min-w-0 flex-1"
          data-testid="event-title"
        />
        <div className="hidden lg:flex flex-wrap items-center gap-2 shrink-0">
          {event.organization_name && (
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                Organization
              </span>
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
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                Event Series
              </span>
              <HighlightButton
                size="sm"
                onClick={() =>
                  navigate(`/event-series/${event.event_repeater}`)
                }
              >
                <Repeat className="h-4 w-4 mr-1.5" />
                {event.event_repeater_name}
              </HighlightButton>
            </div>
          )}
        </div>
      </div>
      <div className="space-y-2 sm:space-y-4">
        {/* Row 3: Admin button group (left) + Subscribe/RSVP (right) */}
        {(isAdmin ||
          canPromoteEvent(event, eventOrgAccess) ||
          (currentUser && event.state === EventState.SIGNUPS_OPEN && signups) ||
          (currentUser && event.event_repeater)) && (
          <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3">
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
                  actions.deleteEvent.mutate(undefined, {
                    onSuccess: () => navigate('/events'),
                  });
                }}
                canComplete={canComplete}
                showCompletePointsNote={showCompletePointsNote}
                onCompleteConfirmed={async () => {
                  try {
                    await actions.completeEvent.mutateAsync();
                    toast.success('Event completed');
                  } catch (err: unknown) {
                    const status = (err as { response?: { status?: number } })
                      ?.response?.status;
                    const context = {
                      eventId: event.id,
                      status,
                      error: extractApiError(err),
                    };
                    if (status != null && status >= 400 && status < 500) {
                      log.warn('event_complete_failed', context);
                    } else {
                      log.error('event_complete_failed', context);
                    }
                    toast.error(
                      extractApiError(err) || 'Failed to complete event',
                    );
                  }
                }}
              />
            ) : (
              <div />
            )}

            {/* Right side: Subscribe + RSVP */}
            <div className="flex flex-wrap items-center gap-2">
              <PromoteEventButton event={event} access={eventOrgAccess} />
              {event.event_repeater &&
                currentUser &&
                (isSubscribed ? (
                  <SecondaryButton
                    size="sm"
                    onClick={() =>
                      unsubscribeMutation.mutate(event.event_repeater!, {
                        onSuccess: () =>
                          toast.success(
                            'Unsubscribed from event series notifications',
                          ),
                      })
                    }
                    disabled={unsubscribeMutation.isPending}
                  >
                    <BellOff className="h-4 w-4 mr-1" />
                    Unsubscribe
                  </SecondaryButton>
                ) : (
                  <PrimaryButton
                    size="sm"
                    onClick={() =>
                      subscribeMutation.mutate(event.event_repeater!, {
                        onSuccess: () =>
                          toast.success(
                            'Subscribed to event series notifications',
                          ),
                      })
                    }
                    disabled={subscribeMutation.isPending}
                  >
                    <Bell className="h-4 w-4 mr-1" />
                    Subscribe
                  </PrimaryButton>
                ))}
              {currentUser && signups && (
                <MySignupActions
                  mySignup={mySignup}
                  signupsOpen={event.state === EventState.SIGNUPS_OPEN}
                  allowUserSignups={event.allow_user_signups}
                  signupDisabled={!profileLoaded || signupMutation.isPending}
                  cancelPending={signupActions.cancel.isPending}
                  onSignup={trySignup}
                  onCancel={() => setShowCancelRsvpConfirm(true)}
                />
              )}
            </div>
          </div>
        )}
      </div>

      <EventLeadershipBanner event={event} access={eventOrgAccess} />

      <div>
        <Tabs value={shownTab} onValueChange={handleTabChange}>
          {/* Below md the PageNavBar dropdown drives tab switching. */}
          <TabsList className="hidden md:inline-flex flex-wrap">
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
            {removedSignups.length > 0 && (
              <TabsTrigger value="removed" data-testid="event-tab-removed">
                Removed ({removedSignups.length})
              </TabsTrigger>
            )}
            {isAdmin && (
              <TabsTrigger value="discord" data-testid="event-tab-discord">
                Discord
              </TabsTrigger>
            )}
            {isAdmin && (
              <TabsTrigger value="history" data-testid="event-tab-history">
                History
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="details">
            <EventOpsNoticesSlot event={event} />
            <EventConductSection
              event={event}
              org={eventOrg ?? undefined}
              access={eventOrgAccess}
            />
            <EventLeadershipSection event={event} access={eventOrgAccess} />
            <DetailsTab
              event={event}
              signedIn={!!currentUser?.pk}
              staff={
                <EventStaffSection
                  event={event}
                  access={eventOrgAccess}
                  hasDiscordServer={!!eventOrg?.discord_server_id}
                />
              }
            />
            {isAdmin && event.event_repeater && (
              <div className="mt-4">
                <SubscriberList repeaterId={event.event_repeater} />
              </div>
            )}
          </TabsContent>

          <TabsContent value="signups">
            <SignupsTab
              signups={activeSignups}
              autoApprove={event.auto_approve}
              isAdmin={isAdmin}
              signupActions={signupActions}
              organization={eventOrg}
              currentUserId={currentUser?.pk}
              staffReasonPolicy={event.staff_reason_policy}
              conductMemberFor={conductMemberFor}
              eventId={event.id}
              orgId={event.organization}
              hasDiscordServer={!!eventOrg?.discord_server_id}
              state={event.state}
              eventTimezone={event.timezone}
              onShowHistory={setHistoryFor}
            />
          </TabsContent>

          <TabsContent value="tentative">
            <SignupsTab
              signups={tentativeSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              organization={eventOrg}
              currentUserId={currentUser?.pk}
              staffReasonPolicy={event.staff_reason_policy}
              conductMemberFor={conductMemberFor}
              state={event.state}
              eventTimezone={event.timezone}
              onShowHistory={setHistoryFor}
            />
          </TabsContent>

          <TabsContent value="waitlist">
            <SignupsTab
              signups={waitlistedSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              organization={eventOrg}
              currentUserId={currentUser?.pk}
              staffReasonPolicy={event.staff_reason_policy}
              conductMemberFor={conductMemberFor}
              state={event.state}
              eventTimezone={event.timezone}
              onShowHistory={setHistoryFor}
            />
          </TabsContent>

          <TabsContent value="removed">
            <SignupsTab
              signups={removedSignups}
              isAdmin={isAdmin}
              signupActions={signupActions}
              organization={eventOrg}
              currentUserId={currentUser?.pk}
              staffReasonPolicy={event.staff_reason_policy}
              conductMemberFor={conductMemberFor}
              state={event.state}
              eventTimezone={event.timezone}
              onShowHistory={setHistoryFor}
            />
          </TabsContent>

          {isAdmin && (
            <TabsContent value="discord">
              <DiscordLogSection
                eventId={event.id}
                guildId={eventOrg?.discord_server_id ?? null}
                canCheckPermissions={isAdmin && Boolean(eventOrg)}
                isAdmin={isAdmin}
                eventTimezone={event.timezone}
              />
            </TabsContent>
          )}

          {isAdmin && currentUser && (
            <TabsContent value="history">
              <SignupHistorySection
                eventId={event.id}
                isAdmin={isAdmin}
                eventTimezone={event.timezone}
                memberOptions={historyMemberOptions}
              />
            </TabsContent>
          )}
        </Tabs>
      </div>

      <SignupHistorySheet
        eventId={event.id}
        eventTimezone={event.timezone}
        isAdmin={isAdmin && !!currentUser}
        user={historyFor}
        onOpenChange={(open) => {
          if (!open) setHistoryFor(null);
        }}
      />

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
        confirmTestId="event-rollcall-dialog-confirm"
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
            await signupActions.cancel.mutateAsync({ id: mySignup.id });
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

      {event && (
        <EventSignupModal
          event={event}
          intent={signupModal.intent}
          profile={profile}
          steamAccountId={currentUser?.steam_account_id}
          open={signupModal.open}
          onOpenChange={(open) => setSignupModal((s) => ({ ...s, open }))}
        />
      )}
    </div>
  );
}

/** Stat row inside a card: tiny uppercase label above bold value. */
function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-1.5 border-b border-border/40 last:border-b-0">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
        {label}
      </span>
      <span className="text-sm font-semibold text-foreground">{value}</span>
    </div>
  );
}

/** Details tab — Tournament Info + Signup Rules + optional Description cards. */
function DetailsTab({
  event,
  signedIn,
  staff,
}: {
  event: NonNullable<ReturnType<typeof useEvent>['data']>;
  signedIn: boolean;
  staff: ReactNode;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <EventLobbyPassword
        eventId={event.id}
        lobbiesEnabled={
          event.game_type === 1 && event.dota_lobby_mode !== 'off'
        }
        signedIn={signedIn}
      />
      <Card>
        <CardHeader>
          <h3 className="font-semibold">Tournament Info</h3>
        </CardHeader>
        <CardContent className="space-y-0">
          {event.tournament_name && (
            <Stat label="Tournament" value={event.tournament_name} />
          )}
          <Stat
            label="Type"
            value={
              <span className="capitalize">
                {event.tournament_type.replace(/_/g, ' ')}
              </span>
            }
          />
          <Stat
            label="Draft"
            value={<span className="capitalize">{event.draft_type}</span>}
          />
          <Stat
            label="Teams"
            value={`${event.number_of_teams ?? 'No limit'} × ${event.people_per_team}`}
          />
          <Stat
            label="Game"
            value={
              isGameType(event.game_type)
                ? GAME_LABEL[event.game_type]
                : 'Unknown'
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h3 className="font-semibold">Signup Rules</h3>
        </CardHeader>
        <CardContent className="space-y-0">
          <Stat
            label="Players"
            value={`${event.min_players ?? '?'} – ${event.max_players ?? '?'}`}
          />
          <Stat
            label="Auto Approve"
            value={event.auto_approve ? 'Yes' : 'No'}
          />
          <Stat
            label="Auto Confirm"
            value={event.auto_confirm ? 'Yes' : 'No'}
          />
          <Stat
            label="Roll call"
            value={
              event.roll_call_enabled && event.state !== EventState.ROLL_CALL
                ? `${rollCallSummary(event)} (${rollCallLabel(true, event.roll_call_mode)})`
                : rollCallSummary(event)
            }
          />
        </CardContent>
      </Card>

      {staff}

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
  eventId,
  orgId,
  hasDiscordServer,
  state,
  autoApprove = true,
  conductMemberFor,
  onShowHistory,
  eventTimezone,
  currentUserId,
  staffReasonPolicy,
  organization,
}: {
  organization?: OrganizationType | null;
  currentUserId: number | undefined;
  staffReasonPolicy: StaffReasonPolicy | undefined;
  conductMemberFor?: ConductMemberLookup;
  onShowHistory?: (user: HistorySubject) => void;
  eventTimezone?: string;
  signups: EventSignupType[];
  autoApprove?: boolean;
  isAdmin: boolean;
  signupActions: ReturnType<typeof useSignupActionMutations>;
  eventId?: number;
  orgId?: number;
  hasDiscordServer?: boolean;
  state: EventType['state'];
}) {
  const [approvalSignup, setApprovalSignup] = useState<EventSignupType | null>(
    null,
  );
  const liveApprovalSignup = approvalSignup
    ? (signups.find((s) => s.id === approvalSignup.id) ?? approvalSignup)
    : null;
  const [removeSignup, setRemoveSignup] = useState<{
    signup: EventSignupType;
    name: string;
  } | null>(null);
  const [addUserOpen, setAddUserOpen] = useState(false);
  const { run, collect, dialogProps } = useStaffAction({
    policy: staffReasonPolicy,
    currentUserId,
  });
  const signupOverride = useSignupOverride(signupActions);
  const reasonMode = (
    action: Parameters<typeof staffReasonMode>[1],
    signup: EventSignupType | null,
  ) =>
    staffReasonMode(staffReasonPolicy, action, {
      fromStatus: signup?.status,
      isSelf: signup?.user === currentUserId,
    });
  const queryClient = useQueryClient();
  const gameType = useContextGameType();

  const userPks = useMemo(() => signups.map((s) => s.user), [signups]);
  const resolvedUsers = useResolvedUsers(userPks);
  const userMap = useMemo(
    () => new Map(resolvedUsers.map((u) => [u.pk, u])),
    [resolvedUsers],
  );

  const signupUserPks = useMemo(
    () => new Set(signups.map((s) => s.user)),
    [signups],
  );
  const entityContext = useMemo(() => ({ orgId }), [orgId]);
  const { mutateAsync: adminAdd } = signupActions.adminAdd;
  const handleAddUser = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      // The modal's Discord tab can hand back a discord_id with no user_id, and
      // adminAddSignup takes a site-user pk only; the throw surfaces as a toast.
      if (payload.user_id == null) {
        throw new Error(
          'Select a site user — adding a Discord member directly is not supported here yet.',
        );
      }
      const userId = payload.user_id;
      const collectReason = async (forceRequired = false) => {
        const reason = await collect('admin_add', {
          userId,
          forceRequired,
          title: 'Add user to event',
        });
        if (reason === null)
          throw new Error('Not added: a reason is required.');
        return reason;
      };
      let reason: string | undefined;
      if (
        staffReasonMode(staffReasonPolicy, 'admin_add', {
          isSelf: userId === currentUserId,
        }) === 'required'
      ) {
        reason = await collectReason();
      }
      const add = () =>
        adminAdd({ userId, ...(reason === undefined ? {} : { reason }) });
      let resp;
      try {
        resp = await add();
      } catch (error) {
        if (!isStaffReasonRequiredError(error)) throw error;
        reason = await collectReason(true);
        resp = await add();
      }
      // AddUserModal reads `.pk` off this to track optimistic adds — the signup
      // itself has no pk, so hand back the user it embeds.
      const added = resp.user_data;
      return added
        ? {
            ...added,
            // The signup serializer nulls these; UserType models them as optional.
            positions: added.positions ?? undefined,
            avatarUrl: added.avatarUrl ?? undefined,
          }
        : { pk: payload.user_id, username: null };
    },
    [adminAdd, collect, staffReasonPolicy, currentUserId],
  );
  const checkIsAdded = useCallback(
    (user: UserType) => (user.pk != null ? signupUserPks.has(user.pk) : false),
    [signupUserPks],
  );

  return (
    <div className="space-y-3">
      {isAdmin &&
        eventId &&
        (state === EventState.SIGNUPS_OPEN ||
          state === EventState.ROLL_CALL) && (
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
          // "Waitlist" fires the server's `demote` mutation
          // (approved/rsvp → waitlisted); named so the label/mutation gap is explicit.
          const handleWaitlist = () =>
            void run('demote', signup, (reason) =>
              signupActions.demote.mutateAsync({
                id: signup.id,
                ...(reason === undefined ? {} : { reason }),
              }),
            );

          const adminActions = isAdmin ? (
            <div className="flex gap-1 [&_button]:min-h-11 sm:[&_button]:min-h-8">
              {(signup.status === 'rsvp' ||
                signup.status === 'pending_approval') && (
                <>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SecondaryButton
                        color="green"
                        size="sm"
                        data-testid={`approve-signup-${signup.id}`}
                        onClick={() => setApprovalSignup(signup)}
                        disabled={signupActions.approve.isPending}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span className="hidden lg:inline ml-1">Approve</span>
                      </SecondaryButton>
                    </TooltipTrigger>
                    <TooltipContent className="lg:hidden">
                      Approve
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <DestructiveButton
                        size="sm"
                        data-testid={`waitlist-signup-${signup.id}`}
                        onClick={handleWaitlist}
                        loading={signupActions.demote.isPending}
                        depth={false}
                      >
                        <ArrowDownToLine className="h-3.5 w-3.5" />
                        <span className="hidden lg:inline ml-1">Waitlist</span>
                      </DestructiveButton>
                    </TooltipTrigger>
                    <TooltipContent className="lg:hidden">
                      Waitlist
                    </TooltipContent>
                  </Tooltip>
                </>
              )}
              {signup.status === 'approved' && (
                <>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SecondaryButton
                        color="blue"
                        size="sm"
                        onClick={() =>
                          void run('confirm', signup, (reason) =>
                            signupActions.confirm.mutateAsync({
                              id: signup.id,
                              ...(reason === undefined ? {} : { reason }),
                            }),
                          )
                        }
                        disabled={signupActions.confirm.isPending}
                      >
                        <UserCheck className="h-3.5 w-3.5" />
                        <span className="hidden lg:inline ml-1">Confirm</span>
                      </SecondaryButton>
                    </TooltipTrigger>
                    <TooltipContent className="lg:hidden">
                      Confirm
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <DestructiveButton
                        size="sm"
                        data-testid={`waitlist-signup-${signup.id}`}
                        onClick={handleWaitlist}
                        loading={signupActions.demote.isPending}
                        depth={false}
                      >
                        <ArrowDownToLine className="h-3.5 w-3.5" />
                        <span className="hidden lg:inline ml-1">Waitlist</span>
                      </DestructiveButton>
                    </TooltipTrigger>
                    <TooltipContent className="lg:hidden">
                      Waitlist
                    </TooltipContent>
                  </Tooltip>
                </>
              )}
              {signup.status === 'confirmed' && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton
                      color="orange"
                      size="sm"
                      onClick={() =>
                        void run('unconfirm', signup, (reason) =>
                          signupActions.unconfirm.mutateAsync({
                            id: signup.id,
                            ...(reason === undefined ? {} : { reason }),
                          }),
                        )
                      }
                      disabled={signupActions.unconfirm.isPending}
                    >
                      <Undo2 className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Unconfirm</span>
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">
                    Unconfirm
                  </TooltipContent>
                </Tooltip>
              )}
              {signup.status === 'waitlisted' && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton
                      color="green"
                      size="sm"
                      data-testid={`approve-signup-${signup.id}`}
                      onClick={() => setApprovalSignup(signup)}
                      disabled={signupActions.approve.isPending}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Approve</span>
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">Approve</TooltipContent>
                </Tooltip>
              )}
              {canRestoreSignup(signup.status) && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton
                      size="sm"
                      data-testid="event-restore-btn"
                      onClick={() =>
                        void run(
                          'reinstate',
                          signup,
                          signupOverride.fire(
                            'reinstate',
                            signup.id,
                            DisplayName(signup),
                          ),
                        )
                      }
                      disabled={signupActions.reinstate.isPending}
                    >
                      <Undo2 className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Restore</span>
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">
                    Restore signup
                  </TooltipContent>
                </Tooltip>
              )}
              {canVoidWithdrawal(signup.status) && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton
                      size="sm"
                      aria-label="Void withdrawal"
                      data-testid="event-void-withdrawal-btn"
                      onClick={() =>
                        void run(
                          'void_withdrawal',
                          signup,
                          signupOverride.fire(
                            'void_withdrawal',
                            signup.id,
                            DisplayName(signup),
                          ),
                          {
                            title: 'Void withdrawal',
                            actionLabel: 'Void withdrawal',
                            errorLabel: 'void withdrawal',
                          },
                        )
                      }
                      disabled={signupActions.voidWithdrawal.isPending}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">
                        Void withdrawal
                      </span>
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent>
                    Restore exact place, class and commitment
                  </TooltipContent>
                </Tooltip>
              )}
              {onShowHistory && (
                <SignupHistoryButton
                  user={historySubjectFor(signup, user)}
                  onClick={() => onShowHistory(historySubjectFor(signup, user))}
                />
              )}
              {!isRemovedSignup(signup.status) && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DestructiveButton
                      size="sm"
                      depth={false}
                      onClick={() => {
                        const name = DisplayName(user ?? signup);
                        setRemoveSignup({ signup, name });
                      }}
                    >
                      <UserX className="h-3.5 w-3.5" />
                      <span className="hidden lg:inline ml-1">Remove</span>
                    </DestructiveButton>
                  </TooltipTrigger>
                  <TooltipContent className="lg:hidden">
                    Remove user
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
          ) : undefined;

          const holdReason = isAdmin
            ? signupHoldReason(signup, autoApprove)
            : null;
          const statusSlot = (
            <div
              className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1"
              data-testid={`event-signup-status-${signup.id}`}
            >
              <span className="inline-flex items-center gap-2">
                <span className="text-xs font-mono text-muted-foreground">
                  #{position}
                </span>
                <EventStateBadge state={signup.status} />
              </span>
              <SignupInLineSince
                signup={signup}
                eventTimezone={eventTimezone}
              />
              <ConductBadge member={conductMemberFor?.(signup.user)} />
              {holdReason && (
                <span
                  className="text-xs text-muted-foreground"
                  data-testid={`signup-hold-reason-${signup.id}`}
                >
                  At last check: {holdReason}
                </span>
              )}
            </div>
          );

          if (user) {
            const baseProfile = signup.dota_profile as DotaProfileData | null;
            const orgMmr = signupRowMmr(user, signup, orgId, gameType);
            const stripProfile = baseProfile
              ? { ...baseProfile, mmr: orgMmr }
              : orgMmr != null
                ? ({
                    positions: {
                      pos_1: false,
                      pos_2: false,
                      pos_3: false,
                      pos_4: false,
                      pos_5: false,
                    },
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
                data-testid={`event-signup-row-${signup.id}`}
                user={user}
                dotaProfile={stripProfile}
                selfReportedRank={signup.self_reported_rank}
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
                  {DisplayName(signup)}
                </p>
              </div>
              {statusSlot}
              {adminActions}
            </div>
          );
        })}
      </div>
      <MmrApprovalModal
        signup={liveApprovalSignup}
        open={!!approvalSignup}
        onOpenChange={(open) => {
          if (!open) setApprovalSignup(null);
        }}
        reasonMode={reasonMode('approve', liveApprovalSignup)}
        onApprove={async (signupId, mmr, reason) => {
          if (!liveApprovalSignup) return false;
          const previousMmr = liveApprovalSignup.org_user_mmr ?? null;
          const playerName = DisplayName(liveApprovalSignup);
          const success = await run(
            'approve',
            liveApprovalSignup,
            (r) =>
              signupActions.approve.mutateAsync({
                id: signupId,
                mmr,
                reason: r,
              }),
            { reason },
          );
          if (!success) return false;
          setApprovalSignup(null);
          if (orgId) {
            void queryClient.invalidateQueries({
              queryKey: orgUsersQueryKey(orgId),
            });
          }
          if (previousMmr != null && previousMmr !== mmr) {
            const delta = mmr - previousMmr;
            toast.success(
              `Approved ${playerName} — MMR ${previousMmr.toLocaleString()} → ${mmr.toLocaleString()} (${delta > 0 ? '+' : ''}${delta.toLocaleString()})`,
            );
          } else if (previousMmr == null) {
            toast.success(
              `Approved ${playerName} at MMR ${mmr.toLocaleString()}`,
            );
          } else {
            toast.success(
              `Approved ${playerName} (MMR unchanged at ${mmr.toLocaleString()})`,
            );
          }
          return true;
        }}
        isApproving={signupActions.approve.isPending}
        isRejecting={signupActions.reject.isPending}
        onReject={async (signupId) => {
          if (!liveApprovalSignup) return;
          const playerName = DisplayName(liveApprovalSignup);
          if (
            await run('reject', liveApprovalSignup, (reason) =>
              signupActions.reject.mutateAsync({
                id: signupId,
                ...(reason === undefined ? {} : { reason }),
              }),
            )
          ) {
            setApprovalSignup(null);
            toast.success(`Rejected signup for ${playerName}`);
          }
        }}
      />
      <StaffReasonDialog
        key={removeSignup?.signup.id ?? 'remove'}
        open={!!removeSignup}
        onOpenChange={(open) => {
          if (!open) setRemoveSignup(null);
        }}
        title="Remove User"
        description={`Remove ${removeSignup?.name ?? 'this user'} from the event? They will lose their signup position and need to re-sign up.`}
        actionLabel="Remove"
        destructive
        required={
          reasonMode('cancel', removeSignup?.signup ?? null) === 'required'
        }
        submitting={signupActions.cancel.isPending}
        onConfirm={async (reason) => {
          if (!removeSignup) return false;
          const success = await run(
            'cancel',
            removeSignup.signup,
            (r) =>
              signupActions.cancel.mutateAsync({
                id: removeSignup.signup.id,
                reason: r,
              }),
            { reason },
          );
          if (success) setRemoveSignup(null);
          return success;
        }}
      />
      <StaffReasonDialog {...dialogProps} />
      <OverrideWarningDialog
        {...signupOverride.dialogProps}
        organization={organization ?? null}
      />
    </div>
  );
}
