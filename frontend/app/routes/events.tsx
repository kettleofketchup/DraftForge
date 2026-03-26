import { generateMeta } from '~/lib/seo';
import { CalendarDays, Plus } from 'lucide-react';

export function meta() {
  return generateMeta({
    title: 'Events',
    description: 'Upcoming Dota 2 tournaments and events',
    url: '/events',
  });
}

import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { EventStateBadge } from '~/components/events';
import type { EventType } from '~/components/events/schemas';
import { RepeaterCard } from '~/components/events/RepeaterCard';
import { useOrganizations } from '~/components/organization';
import { PrimaryButton } from '~/components/ui/buttons';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { useEvents } from '~/hooks/useEvent';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import api from '~/components/api/axios';

/** Skeleton loader for event cards */
const EventCardSkeleton = () => (
  <div className="animate-pulse bg-base-300 rounded-lg p-6 h-40" />
);

/** Grid of skeleton cards */
const EventGridSkeleton = ({ count = 6 }: { count?: number }) => (
  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    {Array.from({ length: count }).map((_, index) => (
      <EventCardSkeleton key={`skeleton-${index}`} />
    ))}
  </div>
);

/** Empty state when no events found */
const EmptyEvents = ({ hasOrgFilter }: { hasOrgFilter: boolean }) => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <CalendarDays className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">No Events Found</h3>
    <p className="text-sm text-muted-foreground">
      {hasOrgFilter
        ? 'No events found for this organization'
        : 'Create a new event to get started!'}
    </p>
  </div>
);

/** Individual event card */
function EventCard({ event }: { event: EventType }) {
  const scheduledDate = new Date(event.scheduled_at);
  const formattedDate = scheduledDate.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  return (
    <Link to={`/events/${event.id}`} data-testid={`event-card-${event.id}`}>
      <Card className="hover:border-primary/50 transition-colors cursor-pointer">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-semibold truncate" data-testid="event-card-name">
              {event.name}
            </h3>
            <EventStateBadge state={event.state} />
          </div>
          <p className="text-sm text-muted-foreground">{event.organization_name}</p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-1 text-sm text-muted-foreground">
            <span>{formattedDate}</span>
            <span>
              {event.signup_count} signup{event.signup_count !== 1 ? 's' : ''}
              {' / '}
              {event.confirmed_count} confirmed
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function useRepeaters(orgId?: number) {
  return useQuery({
    queryKey: ['repeaters', orgId],
    queryFn: () =>
      api.get('/events/repeaters/', { params: orgId ? { organization: orgId } : {} }).then((r) => r.data),
  });
}

export default function EventsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedOrgId = searchParams.get('organization');
  const selectedOrgIdNum = selectedOrgId ? parseInt(selectedOrgId, 10) : undefined;

  const { data: events, isLoading } = useEvents(
    selectedOrgIdNum ? { organization: selectedOrgIdNum } : undefined,
  );
  const { data: repeaters } = useRepeaters(selectedOrgIdNum);
  const { organizations } = useOrganizations();
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Get selected organization for permission checks
  const selectedOrg = useMemo(
    () => organizations.find((o) => o.pk === selectedOrgIdNum) || null,
    [organizations, selectedOrgIdNum],
  );
  const isOrgAdmin = useIsOrganizationAdmin(selectedOrg);

  // Can create events when org is selected AND user is org admin
  const canCreate = isOrgAdmin && selectedOrgIdNum;

  function setOrgFilter(value: string | null) {
    const newParams = new URLSearchParams(searchParams);
    if (value && value !== 'all') {
      newParams.set('organization', value);
    } else {
      newParams.delete('organization');
    }
    setSearchParams(newParams);
  }

  const renderEventGrid = () => {
    if (events && events.length > 0) {
      return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {events.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      );
    }

    if (isLoading) {
      return <EventGridSkeleton count={6} />;
    }

    return <EmptyEvents hasOrgFilter={!!selectedOrgId} />;
  };

  const renderRepeaterGrid = () => {
    if (repeaters && repeaters.length > 0) {
      return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {repeaters.map((repeater: { id: number; name: string; organization: number; organization_name?: string; frequency: string; is_active: boolean; subscriber_count: number; next_event_date: string | null }) => (
            <RepeaterCard key={repeater.id} repeater={repeater} />
          ))}
        </div>
      );
    }

    return (
      <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
        <CalendarDays className="w-16 h-16 mb-4 opacity-50" />
        <h3 className="text-xl font-semibold mb-2">No Repeating Series</h3>
        <p className="text-sm text-muted-foreground">
          Create a repeating event series from an organization page.
        </p>
      </div>
    );
  };

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <CalendarDays className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">Events</h1>
        </div>
        {canCreate && (
          <PrimaryButton
            onClick={() => setCreateModalOpen(true)}
            data-testid="create-event-btn"
          >
            <Plus className="w-4 h-4 mr-2" />
            Create Event
          </PrimaryButton>
        )}
      </div>

      {/* Organization Filter */}
      <div className="mb-6">
        <div className="w-64">
          <label className="text-sm font-medium mb-1 block">
            Filter by Organization
          </label>
          <Select
            value={selectedOrgId || 'all'}
            onValueChange={(v) => setOrgFilter(v === 'all' ? null : v)}
          >
            <SelectTrigger data-testid="events-org-filter">
              <SelectValue placeholder="All organizations" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All organizations</SelectItem>
              {organizations
                .filter((org) => org.pk != null)
                .map((org) => (
                  <SelectItem key={org.pk} value={org.pk!.toString()}>
                    {org.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Tabs: Events / Series */}
      <Tabs defaultValue="events">
        <TabsList className="mb-4">
          <TabsTrigger value="events" data-testid="events-tab-events">
            Events {events ? `(${events.length})` : ''}
          </TabsTrigger>
          <TabsTrigger value="series" data-testid="events-tab-series">
            Series {repeaters ? `(${repeaters.length})` : ''}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="events">
          {renderEventGrid()}
        </TabsContent>

        <TabsContent value="series">
          {renderRepeaterGrid()}
        </TabsContent>
      </Tabs>
    </div>
  );
}
