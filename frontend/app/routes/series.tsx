import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, Pencil, Repeat, Users, ArrowLeft } from 'lucide-react';
import { generateMeta } from '~/lib/seo';
import { EventStateBadge } from '~/components/events';
import { EditRepeaterModal } from '~/components/events/EditRepeaterModal';
import type { EventType } from '~/components/events/schemas';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { useOrganization } from '~/components/organization';
import { useIsOrganizationStaff } from '~/hooks/usePermissions';
import api from '~/components/api/axios';
import type { Route } from './+types/series';

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
  const id = params.repeaterId ? parseInt(params.repeaterId, 10) : null;
  if (!id) return { repeater: null };
  try {
    const resp = await api.get(`/events/repeaters/${id}/`);
    return { repeater: resp.data };
  } catch {
    return { repeater: null };
  }
}

export function meta({ data }: Route.MetaArgs) {
  const repeater = data?.repeater;
  return generateMeta({
    title: repeater?.name ? `${repeater.name} — Event Series` : 'Event Series',
    description: repeater?.description || 'Repeating event series details',
  });
}

interface RepeaterDetail {
  id: number;
  name: string;
  description: string;
  organization: number;
  organization_name: string;
  frequency: string;
  day_of_week: number | null;
  time_of_day: string;
  is_active: boolean;
  subscriber_count: number;
  next_event_date: string | null;
  tournament_name: string;
  tournament_type: string;
  draft_type: string;
  game_type: number;
  people_per_team: number;
  number_of_teams: number | null;
}

const FREQUENCY_LABELS: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  biweekly: 'Biweekly',
  monthly: 'Monthly',
};

const DAY_LABELS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function useRepeater(id: number | null) {
  return useQuery<RepeaterDetail>({
    queryKey: ['repeater', id],
    queryFn: () => api.get(`/events/repeaters/${id}/`).then((r) => r.data),
    enabled: !!id,
  });
}

function useRepeaterEvents(repeaterId: number | null) {
  return useQuery<EventType[]>({
    queryKey: ['repeater-events', repeaterId],
    queryFn: () => api.get(`/events/?event_repeater=${repeaterId}`).then((r) => r.data),
    enabled: !!repeaterId,
  });
}

function EventGrid({ events, opacity }: { events: EventType[]; opacity?: boolean }) {
  if (events.length === 0) return null;
  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {events.map((event) => (
        <Link key={event.id} to={`/events/${event.id}`}>
          <Card className={`hover:border-primary/50 transition-colors cursor-pointer ${opacity ? 'opacity-60' : ''}`}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-sm truncate">{event.name}</span>
                <EventStateBadge state={event.state} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-xs text-muted-foreground">
                {new Date(event.scheduled_at).toLocaleDateString(undefined, {
                  weekday: 'short', month: 'short', day: 'numeric',
                  hour: 'numeric', minute: '2-digit',
                })}
                <span className="ml-2">
                  {event.signup_count} signup{event.signup_count !== 1 ? 's' : ''}
                </span>
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}

export default function SeriesPage() {
  const { repeaterId } = useParams<{ repeaterId: string }>();
  const id = repeaterId ? parseInt(repeaterId, 10) : null;
  const queryClient = useQueryClient();

  const { data: repeater, isLoading } = useRepeater(id);
  const { data: events } = useRepeaterEvents(id);
  const [editOpen, setEditOpen] = useState(false);

  const { organization } = useOrganization(repeater?.organization);
  const isStaff = useIsOrganizationStaff(organization);

  // Current: signups_open, roll_call, in_progress
  const currentEvents = useMemo(
    () => events?.filter((e) => ['signups_open', 'roll_call', 'in_progress'].includes(e.state)) || [],
    [events],
  );

  // Upcoming: upcoming (signups not yet open)
  const upcomingEvents = useMemo(
    () => events?.filter((e) => e.state === 'upcoming') || [],
    [events],
  );

  // Past: completed, cancelled
  const pastEvents = useMemo(
    () => events?.filter((e) => ['completed', 'cancelled'].includes(e.state)) || [],
    [events],
  );

  if (isLoading) {
    return (
      <div className="container mx-auto p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 bg-base-300 rounded" />
          <div className="h-4 w-96 bg-base-300 rounded" />
        </div>
      </div>
    );
  }

  if (!repeater) {
    return (
      <div className="container mx-auto p-4">
        <div className="text-center py-16 text-muted-foreground">
          Series not found.
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-muted-foreground mb-4">
        <Link to="/events" className="hover:text-foreground">Events</Link>
        <span>/</span>
        <Link to="/events" className="hover:text-foreground">Series</Link>
        <span>/</span>
        <span className="text-foreground">{repeater.name}</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{repeater.name}</h1>
          <Link
            to={`/organizations/${repeater.organization}`}
            className="text-sm text-muted-foreground hover:text-primary"
          >
            {repeater.organization_name}
          </Link>
        </div>
        <div className="flex items-center gap-2">
          {isStaff && (
            <SecondaryButton
              size="sm"
              onClick={() => setEditOpen(true)}
              data-testid="edit-series-btn"
            >
              <Pencil className="h-4 w-4 mr-1" />
              Edit
            </SecondaryButton>
          )}
          <Badge
            className={
              repeater.is_active
                ? 'bg-success/20 text-success border-success/30'
                : 'bg-muted text-muted-foreground border-border'
            }
          >
            {repeater.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-base-300 border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Schedule</h3>
          <div className="space-y-1 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Repeat className="h-3.5 w-3.5" />
              <Badge className="bg-primary/20 text-primary border-primary/30">
                {FREQUENCY_LABELS[repeater.frequency] || repeater.frequency}
              </Badge>
            </div>
            {repeater.day_of_week !== null && (
              <p>{DAY_LABELS[repeater.day_of_week]}</p>
            )}
            <p>{repeater.time_of_day}</p>
          </div>
        </div>

        <div className="bg-base-300 border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Tournament Config</h3>
          <div className="space-y-1 text-sm text-muted-foreground">
            <p className="capitalize">{repeater.draft_type} draft</p>
            <p className="capitalize">{repeater.tournament_type.replace(/_/g, ' ')}</p>
            <p>{repeater.people_per_team}v{repeater.people_per_team}</p>
          </div>
        </div>

        <div className="bg-base-300 border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Stats</h3>
          <div className="space-y-1 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5" />
              <span>{repeater.subscriber_count} subscriber{repeater.subscriber_count !== 1 ? 's' : ''}</span>
            </div>
            <p>{events?.length || 0} total events</p>
            {repeater.next_event_date && (
              <div className="flex items-center gap-1.5">
                <CalendarDays className="h-3.5 w-3.5" />
                <span>Next: {new Date(repeater.next_event_date).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {repeater.description && (
        <div className="bg-base-300 border border-border rounded-lg p-4 mb-6">
          <p className="text-sm text-muted-foreground">{repeater.description}</p>
        </div>
      )}

      {/* Current Events (active right now) */}
      {currentEvents.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-3">
            Current Events
            <span className="text-sm text-muted-foreground font-normal ml-2">({currentEvents.length})</span>
          </h2>
          <EventGrid events={currentEvents} />
        </div>
      )}

      {/* Upcoming Events */}
      {upcomingEvents.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-3">
            Upcoming
            <span className="text-sm text-muted-foreground font-normal ml-2">({upcomingEvents.length})</span>
          </h2>
          <EventGrid events={upcomingEvents} />
        </div>
      )}

      {/* Past Events */}
      {pastEvents.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-muted-foreground mb-3">
            Past Events
            <span className="text-sm font-normal ml-2">({pastEvents.length})</span>
          </h2>
          <EventGrid events={pastEvents} opacity />
        </div>
      )}

      {/* No events at all */}
      {events?.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <CalendarDays className="h-12 w-12 mx-auto mb-3 opacity-50" />
          <p>No events generated yet for this series.</p>
        </div>
      )}

      {/* Edit Repeater Modal */}
      {isStaff && (
        <EditRepeaterModal
          repeater={repeater as any}
          open={editOpen}
          onOpenChange={(open) => {
            setEditOpen(open);
            if (!open) {
              queryClient.invalidateQueries({ queryKey: ['repeater', id] });
              queryClient.invalidateQueries({ queryKey: ['repeater-events', id] });
            }
          }}
        />
      )}
    </div>
  );
}
