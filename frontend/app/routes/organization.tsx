import { useQueryClient } from '@tanstack/react-query';
import {
  Building2,
  Calendar,
  CalendarDays,
  ClipboardList,
  ExternalLink,
  Megaphone,
  Plus,
  Repeat,
  Settings,
  Upload,
  Users,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ShouldRevalidateFunctionArgs } from 'react-router';
import { useParams } from 'react-router';
import type { AddMemberPayload } from '~/components/api/api';
import { addOrgMember, fetchOrganization } from '~/components/api/api';
import {
  CreateEventModal,
  EditEventModal,
  EditRepeaterModal,
  EventStrip,
  type EventListItem,
} from '~/components/events';
import { RepeatersList } from '~/components/events/RepeatersList';
import { CreateLeagueModal, LeagueCard, useLeagues } from '~/components/league';
import {
  ClaimsTab,
  DeleteOrganizationDangerZone,
  useOrganization,
} from '~/components/organization';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { useOrgSettingsParam } from '~/components/organization/hooks/useOrgSettingsParam';
import { orgUsersQueryKey } from '~/components/organization/hooks/useOrgUsersQuery';
import { OrganizationHeaderTitle } from '~/components/organization/OrganizationHeaderTitle';
import { buildOrgPageNavOptions } from '~/components/organization/orgPageNavOptions';
import { OrgSettingsDialog } from '~/components/organization/OrgSettingsDialog';
import { useOrgSettingsAccess } from '~/components/organization/tabs/orgSettings/useOrgSettingsAccess';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import {
  EntityBreadcrumb,
  type BreadcrumbSegment,
} from '~/components/ui/entity-breadcrumb';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  useUrlTabs,
} from '~/components/ui/tabs';
import { UserList } from '~/components/user';
import { AddUserModal } from '~/components/user/AddUserModal';
import { CSVImportModal } from '~/components/user/CSVImportModal';
import type { UserType } from '~/components/user/types';
import { PendingClaimsBadge, usePendingClaimsCount } from '~/features/claims';
import {
  useDiscordBotStatus,
  useDiscordConnectResult,
} from '~/features/discord-connect';
import {
  LockedFeaturesPanel,
  removeFeatureQueries,
  useOrgFeatureAccess,
} from '~/features/org-features';
import { PromotionTab } from '~/features/promotion';
import {
  isStandingTabValue,
  TrackTab,
  visibleStandingTabs,
} from '~/features/standing';
import {
  useEvent,
  useEventRepeater,
  useEventRepeaters,
  useEvents,
} from '~/hooks/useEvent';
import { useMemberAccess } from '~/hooks/useMemberAccess';
import { useOrgUsers } from '~/hooks/useOrgUsers';
import { usePageNav } from '~/hooks/usePageNav';
import {
  useIsOrganizationAdmin,
  useIsOrganizationOwner,
  useIsOrganizationStaff,
} from '~/hooks/usePermissions';
import { memberCountDisplay } from '~/lib/memberCountDisplay';
import { generateMeta } from '~/lib/seo';
import type { OrganizationSSR } from '~/lib/ssr-types';
import { queryClient } from '~/root';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import type { Route } from './+types/organization';

export async function loader({ params }: Route.LoaderArgs) {
  const { fetchSSR } = await import('~/lib/ssr.server');
  const organization = await fetchSSR<OrganizationSSR>(
    `/organizations/${params.organizationId}/ssr/`,
  );
  return { organization };
}

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
  const pk = params.organizationId ? parseInt(params.organizationId, 10) : null;
  if (!pk) return { organization: null };

  try {
    const organization = await fetchOrganization(pk);
    // Seed TanStack Query cache so useOrganization() doesn't re-fetch
    queryClient.setQueryData(['organization', pk], organization);
    return { organization };
  } catch {
    return { organization: null };
  }
}

// Tabs live in ?tab=; switching them must not refetch the org through clientLoader.
export function shouldRevalidate({
  currentUrl,
  nextUrl,
  formMethod,
  defaultShouldRevalidate,
}: ShouldRevalidateFunctionArgs) {
  if (!formMethod && currentUrl.pathname === nextUrl.pathname) return false;
  return defaultShouldRevalidate;
}

export function meta({ data }: Route.MetaArgs) {
  const org = data?.organization as OrganizationSSR | null;

  if (org?.name) {
    const desc = org.description
      ? org.description.slice(0, 150)
      : `${org.name} — Dota 2 tournament organization on DraftForge`;
    return generateMeta({
      title: org.name,
      description: desc,
      image: org.logo || undefined,
      url: `/organizations/${org.pk}`,
    });
  }

  return generateMeta({
    title: 'Organization',
    description: 'Organization profile and events',
  });
}

const DiscordIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
  >
    <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
  </svg>
);

function EventsList({
  events,
  loading,
  onEdit,
  onEditSeries,
}: {
  events: EventListItem[];
  loading: boolean;
  onEdit?: (event: EventListItem) => void;
  onEditSeries?: (repeaterId: number) => void;
}) {
  if (loading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Loading events...
      </div>
    );
  }
  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No events found
      </div>
    );
  }
  return (
    <div>
      <h3 className="text-lg font-semibold mb-3 hidden lg:block">
        <CalendarDays className="inline h-4 w-4 mr-1.5 align-text-bottom" />
        Events ({events.length})
      </h3>
      <div className="grid gap-2">
        {events.map((event) => (
          <EventStrip
            key={event.id}
            event={event}
            onEdit={onEdit}
            onEditSeries={onEditSeries}
          />
        ))}
      </div>
    </div>
  );
}

export default function OrganizationDetailPage() {
  const { organizationId } = useParams();
  const pk = organizationId ? parseInt(organizationId, 10) : undefined;
  const queryClient = useQueryClient();
  const { organization, isLoading: orgLoading, refetch } = useOrganization(pk);
  const { leagues, isLoading: leaguesLoading } = useLeagues(pk);
  const currentUser = useUserStore((state) => state.currentUser);
  const [createLeagueOpen, setCreateLeagueOpen] = useState(false);
  const [createEventOpen, setCreateEventOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState<EventListItem | null>(null);
  const [editingRepeaterId, setEditingRepeaterId] = useState<number | null>(
    null,
  );
  const { data: editingRepeater } = useEventRepeater(editingRepeaterId);
  const [showAddUser, setShowAddUser] = useState(false);
  const [showCSVImport, setShowCSVImport] = useState(false);
  const [urlTab, setActiveTab] = useUrlTabs('leagues');
  // Legacy ?tab=settings is rewritten to ?settings= by useOrgSettingsParam.
  const activeTab = urlTab === 'settings' ? 'leagues' : urlTab;

  const { data: events = [], isLoading: eventsLoading } = useEvents(
    { organization: pk },
    { enabled: !!pk },
  );
  // The list rows are slim; the edit form needs every event field.
  const { data: fullEditingEvent } = useEvent(editingEvent?.id ?? null);
  const { data: repeaters = [], isLoading: repeatersLoading } =
    useEventRepeaters({ organization: pk }, { enabled: !!pk });

  const currentOrg = useOrgStore((s) => s.currentOrg);

  const onMemberViewerChange = useCallback(() => {
    if (pk) {
      // Remove, not reset: this runs before useQuery applies enabled=false, so a
      // reset would refetch the members list as the new (possibly anonymous) viewer.
      queryClient.removeQueries({ queryKey: orgUsersQueryKey(pk) });
      useUserCacheStore.getState().dropScoped({ orgId: pk });
      removeFeatureQueries(queryClient, pk);
    }
    refetch();
  }, [pk, queryClient, refetch]);
  const { canView: canViewMembers, settled: memberAccessSettled } =
    useMemberAccess(organization, onMemberViewerChange);

  const orgUsersEnabled =
    activeTab === 'users' && memberAccessSettled && !!canViewMembers;
  const {
    users: orgUsers,
    pks: orgUserPks,
    isLoading: orgUsersLoading,
    isLoaded: orgUsersLoaded,
  } = useOrgUsers(pk ?? 0, { enabled: orgUsersEnabled });

  useEffect(() => {
    if (memberAccessSettled && !canViewMembers && activeTab === 'users') {
      setActiveTab('leagues');
    }
  }, [memberAccessSettled, canViewMembers, activeTab, setActiveTab]);

  const featureAccess = useOrgFeatureAccess(organization ?? undefined);
  const standingTabs = useMemo(
    () => visibleStandingTabs(featureAccess.standingTracks),
    [featureAccess.standingTracks],
  );
  useEffect(() => {
    if (
      featureAccess.settled &&
      isStandingTabValue(activeTab) &&
      !standingTabs.some((t) => t.value === activeTab)
    ) {
      setActiveTab('leagues');
    }
  }, [featureAccess.settled, standingTabs, activeTab, setActiveTab]);
  const canUsePromotion = featureAccess.canUsePromotion;
  useEffect(() => {
    if (
      featureAccess.settled &&
      !canUsePromotion &&
      activeTab === 'promotion'
    ) {
      setActiveTab('leagues');
    }
  }, [featureAccess.settled, canUsePromotion, activeTab, setActiveTab]);

  const settingsAccess = useOrgSettingsAccess(organization ?? undefined);
  const settingsParam = useOrgSettingsParam(settingsAccess);

  const isOwner = useIsOrganizationOwner(organization);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isOrgStaff = useIsOrganizationStaff(organization);
  const canEditEvents = isOrgStaff;
  const canAddMembers = isOrgStaff;
  const canViewClaims = isOrgStaff;
  const pendingClaimsCount = usePendingClaimsCount(pk, !!canViewClaims);

  // AddUserModal callbacks
  const handleAddMember = useCallback(
    async (payload: AddMemberPayload) => {
      if (!pk) throw new Error('No organization');
      const user = await addOrgMember(pk, payload);
      useUserCacheStore.getState().upsert(user, { orgId: pk });
      const addedPk = user.pk;
      if (addedPk != null) {
        queryClient.setQueryData<number[]>(orgUsersQueryKey(pk), (old) =>
          old && !old.includes(addedPk) ? [...old, addedPk] : old,
        );
      }
      void queryClient.invalidateQueries({
        queryKey: organizationQueryKey(pk),
      });
      return user;
    },
    [pk, queryClient],
  );

  const addedPkSet = useMemo(() => new Set(orgUserPks), [orgUserPks]);
  const isUserAdded = useCallback(
    (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
    [addedPkSet],
  );

  const hasDiscordServer = Boolean(organization?.discord_server_id);

  const { data: botStatus } = useDiscordBotStatus(
    pk,
    !!organization && !!currentUser && !!isOrgAdmin,
  );
  const hasBotAccess = botStatus?.has_bot ?? null;
  useDiscordConnectResult(pk);

  // Page nav options for mobile navbar dropdown
  const userCountDisplay = memberCountDisplay({
    entityId: pk,
    loadedForId: orgUsersEnabled && orgUsersLoaded ? pk : null,
    loading: orgUsersLoading,
    loadedCount: orgUserPks.length,
    fallbackCount: organization?.users_count,
  });
  const pageNavOptions = useMemo(
    () =>
      buildOrgPageNavOptions({
        leaguesCount: leagues.length,
        eventsCount: events.length,
        userCountDisplay,
        canViewMembers,
        standingTabs,
        canUsePromotion,
        canViewClaims,
        pendingClaimsCount,
      }),
    [
      leagues.length,
      events.length,
      userCountDisplay,
      canViewMembers,
      standingTabs,
      canUsePromotion,
      canViewClaims,
      pendingClaimsCount,
    ],
  );

  usePageNav(organization ? pageNavOptions : null, activeTab, setActiveTab);

  const breadcrumbSegments = useMemo((): BreadcrumbSegment[] => {
    if (!organization) return [];
    return [{ type: 'organization' as const, label: organization.name }];
  }, [organization]);

  if (orgLoading) {
    return (
      <div className="container mx-auto p-4 text-center">
        Loading organization...
      </div>
    );
  }

  if (!organization) {
    return (
      <div className="container mx-auto p-4 text-center">
        Organization not found
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <EntityBreadcrumb segments={breadcrumbSegments} />
      {/* Organization Header */}
      <div className="bg-base-200 shadow-lg mb-8 p-8">
        <div className="flex flex-col gap-2 p-6">
          <div className="flex flex-col md:flex-row gap-6">
            {/* Organization Logo */}
            <div className="flex-shrink-0">
              {organization.logo ? (
                <img
                  src={organization.logo}
                  alt={organization.name}
                  className="w-32 h-32 rounded-xl object-cover shadow-md"
                />
              ) : (
                <div className="w-32 h-32 rounded-xl bg-base-300 flex items-center justify-center shadow-md">
                  <Building2 className="w-16 h-16 text-muted-foreground" />
                </div>
              )}
            </div>

            {/* Organization Info */}
            <div className="flex-1">
              <OrganizationHeaderTitle
                name={organization.name}
                action={
                  settingsAccess.canOpen && (
                    <SecondaryButton
                      size="sm"
                      data-testid="org-settings-button"
                      onClick={() => settingsParam.openSettings()}
                    >
                      <Settings className="h-4 w-4" />
                      Org Settings
                    </SecondaryButton>
                  )
                }
              />

              {/* Discord Link + Bot Status */}
              <div className="flex flex-wrap items-center gap-3 mb-4">
                {organization.discord_link && (
                  <a
                    href={organization.discord_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-discord hover:text-discord/80 transition-colors"
                  >
                    <DiscordIcon className="w-5 h-5" />
                    <span>Join our Discord</span>
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}
                {isOrgAdmin && hasBotAccess === false && (
                  <SecondaryButton
                    size="sm"
                    onClick={() => settingsParam.openSettings('discord')}
                    data-testid="org-connect-discord-button"
                  >
                    <DiscordIcon className="h-4 w-4" />
                    {hasDiscordServer ? 'Add Discord bot' : 'Connect Discord'}
                  </SecondaryButton>
                )}
              </div>

              {/* Description */}
              {organization.description && (
                <div className="max-w-none">
                  <p className="text-base-content/80 whitespace-pre-wrap">
                    {organization.description}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs Section */}
      <div className="rounded-lg border border-border bg-base-200/50 p-4 md:p-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="hidden md:flex mb-4">
            <TabsTrigger value="leagues" data-testid="org-tab-leagues">
              Leagues ({leagues.length})
            </TabsTrigger>
            <TabsTrigger value="events" data-testid="org-tab-events">
              <Calendar className="w-4 h-4 mr-2" />
              Events ({events.length})
            </TabsTrigger>
            {canViewMembers && (
              <TabsTrigger value="users" data-testid="org-tab-users">
                <Users className="w-4 h-4 mr-2" />
                Users ({userCountDisplay})
              </TabsTrigger>
            )}
            {standingTabs.map(({ value, label, icon: Icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                data-testid={`org-tab-${value}`}
              >
                <Icon className="w-4 h-4 mr-2" />
                {label}
              </TabsTrigger>
            ))}
            {canUsePromotion && (
              <TabsTrigger value="promotion" data-testid="org-tab-promotion">
                <Megaphone className="w-4 h-4 mr-2" />
                Promotion
              </TabsTrigger>
            )}
            {canViewClaims && (
              <TabsTrigger value="claims" data-testid="org-tab-claims">
                <ClipboardList className="w-4 h-4 mr-2" />
                Claims
                <PendingClaimsBadge
                  count={pendingClaimsCount}
                  testId="org-tab-claims-pending-count"
                />
              </TabsTrigger>
            )}
          </TabsList>

          {/* Leagues Tab */}
          <TabsContent value="leagues">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Leagues</h2>
              {isOrgStaff && (
                <PrimaryButton
                  onClick={() => setCreateLeagueOpen(true)}
                  data-testid="create-league-button"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Create League
                </PrimaryButton>
              )}
            </div>

            {leaguesLoading ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading leagues...
              </div>
            ) : leagues.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No leagues found
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {leagues.map((league) => (
                  <LeagueCard key={league.pk} league={league} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Events Tab */}
          <TabsContent value="events">
            <div className="flex items-center justify-between mb-4">
              <h2
                className="text-xl font-semibold"
                data-testid="org-events-heading"
              >
                Events
              </h2>
              <div className="flex items-center gap-2">
                {isOrgStaff && (
                  <PrimaryButton
                    data-testid="create-event-btn"
                    onClick={() => setCreateEventOpen(true)}
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Create Event
                  </PrimaryButton>
                )}
              </div>
            </div>

            {/* Desktop: side-by-side columns */}
            <div className="hidden lg:grid lg:grid-cols-2 lg:gap-6">
              <EventsList
                events={events}
                loading={eventsLoading}
                onEdit={canEditEvents ? setEditingEvent : undefined}
                onEditSeries={canEditEvents ? setEditingRepeaterId : undefined}
              />
              <RepeatersList
                repeaters={repeaters}
                loading={repeatersLoading}
                onEdit={
                  canEditEvents ? (r) => setEditingRepeaterId(r.id) : undefined
                }
              />
            </div>

            {/* Mobile: sub-tabs */}
            <div className="lg:hidden">
              <Tabs defaultValue="upcoming">
                <TabsList className="w-full mb-4">
                  <TabsTrigger value="upcoming" className="flex-1 gap-1.5">
                    <CalendarDays className="h-3.5 w-3.5" />
                    Events ({events.length})
                  </TabsTrigger>
                  <TabsTrigger value="repeaters" className="flex-1 gap-1.5">
                    <Repeat className="h-3.5 w-3.5" />
                    Repeating ({repeaters.length})
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="upcoming">
                  <EventsList
                    events={events}
                    loading={eventsLoading}
                    onEdit={canEditEvents ? setEditingEvent : undefined}
                    onEditSeries={
                      canEditEvents ? setEditingRepeaterId : undefined
                    }
                  />
                </TabsContent>
                <TabsContent value="repeaters">
                  <RepeatersList
                    repeaters={repeaters}
                    loading={repeatersLoading}
                    onEdit={
                      canEditEvents
                        ? (r) => setEditingRepeaterId(r.id)
                        : undefined
                    }
                  />
                </TabsContent>
              </Tabs>
            </div>
          </TabsContent>

          {canViewMembers && (
            <TabsContent value="users">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold">Organization Members</h2>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">
                    {orgUsers.length}{' '}
                    {orgUsers.length === 1 ? 'member' : 'members'}
                  </span>
                  {canAddMembers && (
                    <>
                      <PrimaryButton
                        size="sm"
                        onClick={() => setShowCSVImport(true)}
                        data-testid="org-csv-import-btn"
                      >
                        <Upload className="w-4 h-4 mr-2" />
                        Import CSV
                      </PrimaryButton>
                      <PrimaryButton
                        size="sm"
                        onClick={() => setShowAddUser(true)}
                        data-testid="org-add-member-btn"
                      >
                        <Plus className="w-4 h-4 mr-2" />
                        Add Member
                      </PrimaryButton>
                    </>
                  )}
                </div>
              </div>

              <UserList
                users={orgUsers}
                isLoading={orgUsersLoading}
                showSearch={orgUsers.length > 5}
                searchPlaceholder="Search members..."
                emptyMessage="No members in this organization"
                organizationId={pk}
              />
            </TabsContent>
          )}

          {pk &&
            standingTabs.map((t) => (
              <TabsContent key={t.value} value={t.value}>
                <TrackTab
                  key={pk}
                  orgId={pk}
                  track={t.track}
                  timeZone={organization.timezone}
                  membersPrivate={organization.members_private ?? false}
                  access={featureAccess}
                />
              </TabsContent>
            ))}

          {canUsePromotion && pk && (
            <TabsContent value="promotion">
              <PromotionTab
                key={pk}
                orgId={pk}
                org={{
                  name: organization.name,
                  discord_link: organization.discord_link,
                }}
                sender={currentUser}
                access={featureAccess}
              />
            </TabsContent>
          )}

          {/* Claims Tab (Staff+) */}
          {canViewClaims && pk && (
            <TabsContent value="claims">
              <ClaimsTab organizationId={pk} />
            </TabsContent>
          )}
        </Tabs>
      </div>

      {organization && isOwner && (
        <DeleteOrganizationDangerZone organization={organization} />
      )}

      {pk && <LockedFeaturesPanel orgId={pk} />}

      {pk && (
        <CreateLeagueModal
          open={createLeagueOpen}
          onOpenChange={setCreateLeagueOpen}
          organizationId={pk}
        />
      )}

      {isOrgStaff && pk && (
        <CreateEventModal
          open={createEventOpen}
          onOpenChange={setCreateEventOpen}
          organizationId={pk}
        />
      )}

      {editingEvent && fullEditingEvent?.id === editingEvent.id && (
        <EditEventModal
          event={fullEditingEvent}
          open={true}
          onOpenChange={(open) => {
            if (!open) setEditingEvent(null);
          }}
        />
      )}

      <EditRepeaterModal
        repeater={editingRepeater ?? null}
        open={editingRepeaterId !== null && editingRepeater !== undefined}
        onOpenChange={(open) => {
          if (!open) setEditingRepeaterId(null);
        }}
      />

      {canAddMembers && pk && (
        <CSVImportModal
          open={showCSVImport}
          onOpenChange={setShowCSVImport}
          entityContext={{ orgId: pk }}
          onComplete={() => {
            void queryClient.invalidateQueries({
              queryKey: organizationQueryKey(pk),
            });
          }}
        />
      )}

      {canAddMembers && pk && (
        <AddUserModal
          open={showAddUser}
          onOpenChange={setShowAddUser}
          title={`Add Member to ${organization?.name || 'Organization'}`}
          entityContext={{ orgId: pk }}
          onAdd={handleAddMember}
          isAdded={isUserAdded}
          hasDiscordServer={hasDiscordServer}
        />
      )}

      {settingsParam.open && pk && (
        <OrgSettingsDialog
          organization={organization}
          open
          section={settingsParam.section}
          onSectionChange={settingsParam.setSection}
          onOpenChange={(open) => {
            if (!open) settingsParam.close();
          }}
        />
      )}
    </div>
  );
}
