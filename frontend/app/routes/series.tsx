import { useMemo } from 'react';
import { Link, useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { CalendarDays, Repeat, Users, ArrowLeft } from 'lucide-react';
import { generateMeta } from '~/lib/seo';
import { EventStateBadge } from '~/components/events';
import type { EventType } from '~/components/events/schemas';
import { Badge } from '~/components/ui/badge';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
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

export default function SeriesPage() {
  const { repeaterId } = useParams<{ repeaterId: string }>();
  const id = repeaterId ? parseInt(repeaterId, 10) : null;

  const { data: repeater, isLoading } = useRepeater(id);
  const { data: events } = useRepeaterEvents(id);

  const upcomingEvents = useMemo(
    () => events?.filter((e) => ['upcoming', 'signups_open', 'roll_call'].includes(e.state)) || [],
    [events],
  );
  const pastEvents = useMemo(
    () => events?.filter((e) => ['in_progress', 'completed', 'cancelled'].includes(e.state)) || [],
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
      {/* Header */}
      <div className="mb-6">
        <Link to="/events" className="text-sm text-muted-foreground hover:text-foreground mb-2 inline-flex items-center gap-1">
          <ArrowLeft className="h-3 w-3" />
          Back to Events
        </Link>
        <div className="flex items-start justify-between mt-2">
          <div>
            <h1 className="text-2xl font-bold">{repeater.name}</h1>
            <Link
              to={`/organizations/${repeater.organization}`}
              className="text-sm text-muted-foreground hover:text-primary"
            >
              {repeater.organization_name}
            </Link>
          </div>
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

      {/* Upcoming Events */}
      {upcomingEvents.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-3">Upcoming Events</h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {upcomingEvents.map((event) => (
              <Link key={event.id} to={`/events/${event.id}`}>
                <Card className="hover:border-primary/50 transition-colors cursor-pointer">
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
        </div>
      )}

      {/* Past Events */}
      {pastEvents.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3 text-muted-foreground">Past Events</h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {pastEvents.map((event) => (
              <Link key={event.id} to={`/events/${event.id}`}>
                <Card className="hover:border-primary/50 transition-colors cursor-pointer opacity-70">
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
                      })}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
