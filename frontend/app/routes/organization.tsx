import { generateMeta } from '~/lib/seo';
import { fetchOrganization } from '~/components/api/api';
import { queryClient } from '~/root';
import { Building2, Calendar, ClipboardList, ExternalLink, Mail, MailCheck, Pencil, Plus, Settings, Upload, Users } from 'lucide-react';
import type { Route } from './+types/organization';

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

export function meta({ data }: Route.MetaArgs) {
  const org = data?.organization;

  if (org?.name) {
    const desc = org.description
      ? org.description.slice(0, 150)
      : `${org.name} - Dota 2 tournament organization`;
    return generateMeta({
      title: org.name,
      description: desc,
      url: `/organizations/${org.pk}`,
    });
  }

  return generateMeta({
    title: 'Organization',
    description: 'Organization profile and events',
  });
}
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { addOrgMember, checkDiscordBotStatus } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';
import { CreateEventModal, EditEventModal, EditOrgDefaultsModal, EditRepeaterModal, EventStrip, type EventType } from '~/components/events';
import type { EventRepeaterType } from '~/components/api/api';
import { useEvents, useEventRepeaters, useRepeaterSubscriptionMutation } from '~/hooks/useEvent';
import { Repeat, CalendarDays } from 'lucide-react';
import { CreateLeagueModal, LeagueCard, useLeagues } from '~/components/league';
import { ClaimsTab, EditOrganizationModal, useOrganization } from '~/components/organization';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { AddDiscordBotButton, PrimaryButton } from '~/components/ui/buttons';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import { Tabs, TabsContent, TabsList, TabsTrigger, useUrlTabs } from '~/components/ui/tabs';
import { UserList } from '~/components/user';
import { AddUserModal } from '~/components/user/AddUserModal';
import { CSVImportModal } from '~/components/user/CSVImportModal';
import type { UserType } from '~/components/user/types';
import { useOrgUsers } from '~/hooks/useOrgUsers';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { usePageNav } from '~/hooks/usePageNav';
import { cn } from '~/lib/utils';
import { toast } from 'sonner';
import { EntityBreadcrumb, type BreadcrumbSegment } from '~/components/ui/entity-breadcrumb';

// Discord icon component
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

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const FREQUENCY_LABELS: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  every_two_weeks: 'Every 2 weeks',
  monthly: 'Monthly',
};

function EventsList({ events, loading, onEdit, onEditSeries }: { events: EventType[]; loading: boolean; onEdit?: (event: EventType) => void; onEditSeries?: (repeaterId: number) => void }) {
  if (loading) {
    return <div className="text-center py-8 text-muted-foreground">Loading events...</div>;
  }
  if (events.length === 0) {
    return <div className="text-center py-8 text-muted-foreground">No events found</div>;
  }
  return (
    <div>
      <h3 className="text-lg font-semibold mb-3 hidden lg:block">
        <CalendarDays className="inline h-4 w-4 mr-1.5 align-text-bottom" />
        Events ({events.length})
      </h3>
      <div className="grid gap-2">
        {events.map((event) => (
          <EventStrip key={event.id} event={event} onEdit={onEdit} onEditSeries={onEditSeries} />
        ))}
      </div>
    </div>
  );
}

function RepeatersList({ repeaters, loading, onEdit }: { repeaters: EventRepeaterType[]; loading: boolean; onEdit?: (repeater: EventRepeaterType) => void }) {
  const currentUser = useUserStore((state) => state.currentUser);
  const { subscribe, unsubscribe } = useRepeaterSubscriptionMutation();
  const isPending = subscribe.isPending || unsubscribe.isPending;

  if (loading) {
    return <div className="text-center py-8 text-muted-foreground">Loading repeating events...</div>;
  }
  if (repeaters.length === 0) {
    return <div className="text-center py-8 text-muted-foreground">No repeating events found</div>;
  }
  return (
    <div>
      <h3 className="text-lg font-semibold mb-3 hidden lg:block">
        <Repeat className="inline h-4 w-4 mr-1.5 align-text-bottom" />
        Repeating Events ({repeaters.length})
      </h3>
      <div className="grid gap-3">
        {repeaters.map((r) => (
          <div key={r.id} className="rounded-lg border border-border p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium truncate">{r.name}</p>
                <p className="text-sm text-muted-foreground">
                  {FREQUENCY_LABELS[r.frequency] ?? r.frequency}
                  {r.day_of_week != null && ` on ${DAY_LABELS[r.day_of_week]}`}
                  {' at '}
                  {r.time_of_day.slice(0, 5)}
                  {r.subscriber_count > 0 && (
                    <span className="ml-2 text-xs">{'\u00B7'} {r.subscriber_count} subscribed</span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {currentUser && r.discord_notify_new_events && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn("h-8 w-8", r.is_subscribed && "text-interactive")}
                        disabled={isPending}
                        onClick={() => {
                          if (r.is_subscribed) {
                            unsubscribe.mutate(r.id, {
                              onError: () => toast.error('Failed to unsubscribe'),
                            });
                          } else {
                            subscribe.mutate(r.id, {
                              onSuccess: () => toast.success('Subscribed to notifications'),
                              onError: () => toast.error('Failed to subscribe'),
                            });
                          }
                        }}
                      >
                        {r.is_subscribed ? <MailCheck className="h-3.5 w-3.5" /> : <Mail className="h-3.5 w-3.5" />}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {r.is_subscribed ? 'Unsubscribe from notifications' : 'Get notified about new events'}
                    </TooltipContent>
                  </Tooltip>
                )}
                {onEdit && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => onEdit(r)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Edit repeating event</TooltipContent>
                  </Tooltip>
                )}
                <Badge variant={r.is_active ? 'default' : 'secondary'}>
                  {r.is_active ? 'Active' : 'Paused'}
                </Badge>
              </div>
            </div>
          </div>
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
  const [editOrgOpen, setEditOrgOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState<EventType | null>(null);
  const [editingRepeaterId, setEditingRepeaterId] = useState<number | null>(null);
  const [showAddUser, setShowAddUser] = useState(false);
  const [showCSVImport, setShowCSVImport] = useState(false);
  const [editDefaultsOpen, setEditDefaultsOpen] = useState(false);
  const [activeTab, setActiveTab] = useUrlTabs('leagues');

  const { data: events = [], isLoading: eventsLoading } = useEvents(
    pk ? { organization: pk } : undefined
  );
  const { data: repeaters = [], isLoading: repeatersLoading } = useEventRepeaters(
    pk ? { organization: pk } : undefined
  );

  // Org users from store (pk array) + cache resolution
  const { orgUserPks, orgUsersLoading, orgUsersOrgId, getOrgUsers } = useOrgStore();
  const orgUsers = useOrgUsers(pk ?? 0);
  const currentOrg = useOrgStore((s) => s.currentOrg);

  // Fetch org users when switching to users tab
  useEffect(() => {
    if (activeTab === 'users' && pk) {
      getOrgUsers(pk);
    }
  }, [activeTab, pk, getOrgUsers]);

  const isOrgAdmin =
    currentUser?.is_superuser ||
    organization?.owner?.pk === currentUser?.pk ||
    organization?.admins?.some((a) => a.pk === currentUser?.pk);

  const canEditEvents = isOrgAdmin || currentUser?.is_staff;

  // Staff can add members but not edit org settings
  const canAddMembers =
    isOrgAdmin ||
    organization?.staff?.some((s) => s.pk === currentUser?.pk);

  // AddUserModal callbacks
  const handleAddMember = useCallback(
    async (payload: AddMemberPayload) => {
      if (!pk) throw new Error('No organization');
      const user = await addOrgMember(pk, payload);
      // Optimistic update: upsert into cache + append pk
      useUserCacheStore.getState().upsert(user, { orgId: pk });
      const { orgUserPks } = useOrgStore.getState();
      if (user.pk != null) {
        useOrgStore.setState({ orgUserPks: [...orgUserPks, user.pk] });
      }
      return user;
    },
    [pk]
  );

  const addedPkSet = useMemo(
    () => new Set(orgUserPks),
    [orgUserPks]
  );
  const isUserAdded = useCallback(
    (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
    [addedPkSet]
  );

  const hasDiscordServer = Boolean(organization?.discord_server_id);

  // Check if the DraftForge bot has access to the org's Discord server
  const { data: botStatus } = useQuery({
    queryKey: ['discordBotStatus', pk],
    queryFn: () => checkDiscordBotStatus(pk!),
    enabled: !!pk && !!organization && !!currentUser && hasDiscordServer && !!isOrgAdmin,
    staleTime: 5 * 60 * 1000, // match backend cache TTL
  });
  const hasBotAccess = botStatus?.has_bot ?? null;

  // Page nav options for mobile navbar dropdown
  const userCountDisplay = orgUsersLoading || orgUsersOrgId !== pk ? '...' : orgUserPks.length;
  const pageNavOptions = useMemo(() => {
    const opts = [
      { value: 'leagues', label: `Leagues (${leagues.length})` },
      { value: 'events', label: `Events (${events.length})` },
      { value: 'users', label: `Users (${userCountDisplay})` },
    ];
    if (isOrgAdmin) {
      opts.push({ value: 'claims', label: 'Claims' });
    }
    return opts;
  }, [leagues.length, events.length, userCountDisplay, isOrgAdmin]);

  usePageNav(organization ? pageNavOptions : null, activeTab, setActiveTab);

  const breadcrumbSegments = useMemo((): BreadcrumbSegment[] => {
    if (!organization) return [];
    return [
      { type: 'organization' as const, label: organization.name },
    ];
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
        <div className="card bg-base-200 shadow-lg mb-8">
          <div className="card-body">
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
                <div className="flex items-start justify-between mb-2">
                  <h1 className="text-3xl font-bold">{organization.name}</h1>
                  {isOrgAdmin && (
                    <PrimaryButton
                      size="sm"
                      onClick={() => setEditOrgOpen(true)}
                      data-testid="edit-organization-button"
                    >
                      <Pencil className="w-4 h-4 mr-2" />
                      Edit
                    </PrimaryButton>
                  )}
                </div>

                {/* Discord Link + Bot Status */}
                <div className="flex flex-wrap items-center gap-3 mb-4">
                  {organization.discord_link && (
                    <a
                      href={organization.discord_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      <DiscordIcon className="w-5 h-5" />
                      <span>Join our Discord</span>
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  )}
                  {isOrgAdmin && hasDiscordServer && hasBotAccess === false && (
                    <AddDiscordBotButton
                      size="sm"
                      compact
                      tooltip="Enable Discord user search and event notifications"
                    />
                  )}
                </div>

                {/* Description */}
                {organization.description && (
                  <div className="prose prose-sm max-w-none">
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
            <TabsTrigger value="users" data-testid="org-tab-users">
              <Users className="w-4 h-4 mr-2" />
              Users ({orgUsersLoading || orgUsersOrgId !== pk ? '...' : orgUserPks.length})
            </TabsTrigger>
            {isOrgAdmin && (
              <TabsTrigger value="claims" data-testid="org-tab-claims">
                <ClipboardList className="w-4 h-4 mr-2" />
                Claims
              </TabsTrigger>
            )}
          </TabsList>

          {/* Leagues Tab */}
          <TabsContent value="leagues">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Leagues</h2>
              {isOrgAdmin && (
                <PrimaryButton onClick={() => setCreateLeagueOpen(true)}>
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
              <h2 className="text-xl font-semibold">Events</h2>
              <div className="flex items-center gap-2">
                {canEditEvents && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9"
                        onClick={() => setEditDefaultsOpen(true)}
                      >
                        <Settings className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Edit event defaults</TooltipContent>
                  </Tooltip>
                )}
                {isOrgAdmin && (
                  <PrimaryButton data-testid="create-event-btn" onClick={() => setCreateEventOpen(true)}>
                    <Plus className="w-4 h-4 mr-2" />
                    Create Event
                  </PrimaryButton>
                )}
              </div>
            </div>

            {/* Desktop: side-by-side columns */}
            <div className="hidden lg:grid lg:grid-cols-2 lg:gap-6">
              <EventsList events={events} loading={eventsLoading} onEdit={canEditEvents ? setEditingEvent : undefined} onEditSeries={canEditEvents ? setEditingRepeaterId : undefined} />
              <RepeatersList repeaters={repeaters} loading={repeatersLoading} onEdit={canEditEvents ? (r) => setEditingRepeaterId(r.id) : undefined} />
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
                  <EventsList events={events} loading={eventsLoading} onEdit={canEditEvents ? setEditingEvent : undefined} onEditSeries={canEditEvents ? setEditingRepeaterId : undefined} />
                </TabsContent>
                <TabsContent value="repeaters">
                  <RepeatersList repeaters={repeaters} loading={repeatersLoading} onEdit={canEditEvents ? (r) => setEditingRepeaterId(r.id) : undefined} />
                </TabsContent>
              </Tabs>
            </div>
          </TabsContent>

          {/* Users Tab */}
          <TabsContent value="users">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Organization Members</h2>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">
                  {orgUsers.length} {orgUsers.length === 1 ? 'member' : 'members'}
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

          {/* Claims Tab (Admin only) */}
          {isOrgAdmin && pk && (
            <TabsContent value="claims">
              <ClaimsTab organizationId={pk} />
            </TabsContent>
          )}
        </Tabs>
        </div>

        {pk && (
          <CreateLeagueModal
            open={createLeagueOpen}
            onOpenChange={setCreateLeagueOpen}
            organizationId={pk}
          />
        )}

        {isOrgAdmin && pk && (
          <CreateEventModal
            open={createEventOpen}
            onOpenChange={setCreateEventOpen}
            organizationId={pk}
            leagues={leagues}
          />
        )}

        <EditEventModal
          event={editingEvent}
          open={editingEvent !== null}
          onOpenChange={(open) => { if (!open) setEditingEvent(null); }}
        />

        <EditRepeaterModal
          repeater={repeaters.find((r) => r.id === editingRepeaterId) ?? null}
          open={editingRepeaterId !== null}
          onOpenChange={(open) => { if (!open) setEditingRepeaterId(null); }}
        />

        {organization && (
          <EditOrganizationModal
            open={editOrgOpen}
            onOpenChange={setEditOrgOpen}
            organization={organization}
            onSuccess={() => {
              refetch();
              queryClient.invalidateQueries({ queryKey: ['discordBotStatus', pk] });
            }}
          />
        )}

        {canAddMembers && pk && (
          <CSVImportModal
            open={showCSVImport}
            onOpenChange={setShowCSVImport}
            entityContext={{ orgId: pk }}
            onComplete={() => {
              const { clearOrgUsers, getOrgUsers } = useOrgStore.getState();
              clearOrgUsers();
              getOrgUsers(pk!);
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

        {editDefaultsOpen && pk && (
          <EditOrgDefaultsModal
            organizationId={pk}
            open={editDefaultsOpen}
            onOpenChange={setEditDefaultsOpen}
          />
        )}
    </div>
  );
}
