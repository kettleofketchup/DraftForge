import { generateMeta } from '~/lib/seo';
import { ArrowDownUp, Building2, CalendarDays, ChevronDown, Filter, ListFilter, Plus, Search } from 'lucide-react';

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
import { Input } from '~/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '~/components/ui/sheet';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover';
import { Switch } from '~/components/ui/switch';
import { useEvents } from '~/hooks/useEvent';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import api from '~/components/api/axios';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';

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
const EmptyEvents = ({ hasFilter }: { hasFilter: boolean }) => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <CalendarDays className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">No Events Found</h3>
    <p className="text-sm text-muted-foreground">
      {hasFilter
        ? 'No events match your filters. Try adjusting your search.'
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

const EVENT_STATES = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'signups_open', label: 'Signups Open' },
  { value: 'roll_call', label: 'Roll Call' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
] as const;

// Default: show active events only (hide completed/cancelled)
const DEFAULT_STATES = new Set(['upcoming', 'signups_open', 'roll_call', 'in_progress']);

const SORT_OPTIONS = [
  { value: 'closest', label: 'Closest' },
  { value: 'date-desc', label: 'Newest' },
  { value: 'date-asc', label: 'Oldest' },
  { value: 'signups', label: 'Signups' },
  { value: 'name', label: 'Name' },
] as const;

/** Shared filter controls — rendered inline on desktop, in Sheet on mobile */
function FilterControls({
  selectedOrgId,
  setOrgFilter,
  organizations,
  selectedStates,
  toggleState,
  sortBy,
  setSortBy,
  vertical,
}: {
  selectedOrgId: string | null;
  setOrgFilter: (v: string | null) => void;
  organizations: { pk?: number; name: string }[];
  selectedStates: Set<string>;
  toggleState: (v: string) => void;
  sortBy: string;
  setSortBy: (v: string) => void;
  vertical?: boolean;
}) {
  const wrapper = vertical ? 'flex flex-col gap-4' : 'contents';
  return (
    <div className={wrapper}>
      {/* Organization */}
      <div>
        <label className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-0.5">
          <Building2 className="h-3 w-3" />
          Organization
        </label>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={`${vertical ? 'w-full' : 'w-40'} justify-between font-normal`}
              data-testid="events-org-filter"
            >
              <span className="truncate">
                {selectedOrgId ? organizations.find((o) => o.pk?.toString() === selectedOrgId)?.name || 'Org' : 'All'}
              </span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-48 p-1" align="start">
            <button
              className={`w-full text-left px-3 py-1.5 text-sm rounded hover:bg-base-400/30 ${!selectedOrgId ? 'text-primary font-medium' : ''}`}
              onClick={() => setOrgFilter(null)}
            >
              All
            </button>
            {organizations
              .filter((org) => org.pk != null)
              .map((org) => (
                <button
                  key={org.pk}
                  className={`w-full text-left px-3 py-1.5 text-sm rounded hover:bg-base-400/30 truncate ${selectedOrgId === org.pk?.toString() ? 'text-primary font-medium' : ''}`}
                  onClick={() => setOrgFilter(org.pk!.toString())}
                >
                  {org.name}
                </button>
              ))}
          </PopoverContent>
        </Popover>
      </div>

      {/* State — multi-select with switches */}
      <div>
        <label className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-0.5">
          <ListFilter className="h-3 w-3" />
          State
        </label>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={`${vertical ? 'w-full' : 'w-36'} justify-between font-normal`}
              data-testid="events-state-filter"
            >
              <span className="truncate">
                {selectedStates.size === EVENT_STATES.length
                  ? 'All'
                  : selectedStates.size === 0
                    ? 'None'
                    : `${selectedStates.size} selected`}
              </span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-48 p-2" align="start">
            <div className="space-y-2">
              {EVENT_STATES.map((s) => (
                <label
                  key={s.value}
                  className="flex items-center justify-between gap-2 px-1 py-0.5 rounded hover:bg-base-400/30 cursor-pointer"
                >
                  <span className="text-sm">{s.label}</span>
                  <Switch
                    checked={selectedStates.has(s.value)}
                    onCheckedChange={() => toggleState(s.value)}
                    data-testid={`events-state-${s.value}`}
                  />
                </label>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* Sort */}
      <div>
        <label className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-0.5">
          <ArrowDownUp className="h-3 w-3" />
          Sort
        </label>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={`${vertical ? 'w-full' : 'w-36'} justify-between font-normal`}
              data-testid="events-sort"
            >
              <span className="truncate">
                {SORT_OPTIONS.find((s) => s.value === sortBy)?.label || 'Closest'}
              </span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-40 p-1" align="start">
            {SORT_OPTIONS.map((s) => (
              <button
                key={s.value}
                className={`w-full text-left px-3 py-1.5 text-sm rounded hover:bg-base-400/30 ${sortBy === s.value ? 'text-primary font-medium' : ''}`}
                onClick={() => setSortBy(s.value)}
              >
                {s.label}
              </button>
            ))}
          </PopoverContent>
        </Popover>
      </div>
    </div>
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

  const { data: repeaters } = useRepeaters(selectedOrgIdNum);
  const { organizations } = useOrganizations();
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Filters + sort
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearch = useDebouncedValue(searchQuery, 300);
  const [selectedStates, setSelectedStates] = useState<Set<string>>(new Set(DEFAULT_STATES));
  const [sortBy, setSortBy] = useState<string>('closest');

  // Map sort UI values to backend ordering params
  const SORT_TO_ORDERING: Record<string, string> = {
    closest: 'closest',
    'date-desc': '-scheduled_at',
    'date-asc': 'scheduled_at',
    signups: '-signup_count',
    name: 'name',
  };

  // Fetch events with all filters as backend query params
  const { data: events, isLoading } = useEvents({
    ...(selectedOrgIdNum ? { organization: selectedOrgIdNum } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(selectedStates.size < EVENT_STATES.length ? { states: [...selectedStates] } : {}),
    ordering: SORT_TO_ORDERING[sortBy] || 'closest',
  });

  // Get selected organization for permission checks
  const selectedOrg = useMemo(
    () => organizations.find((o) => o.pk === selectedOrgIdNum) || null,
    [organizations, selectedOrgIdNum],
  );
  const isOrgAdmin = useIsOrganizationAdmin(selectedOrg);
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

  // Events come pre-filtered/sorted from backend — no client-side filtering needed
  const filteredEvents = events || [];

  const statesChanged = selectedStates.size !== DEFAULT_STATES.size ||
    [...DEFAULT_STATES].some((s) => !selectedStates.has(s));
  const hasActiveFilter = debouncedSearch || statesChanged || !!selectedOrgId;
  const activeFilterCount = [
    selectedOrgId ? 1 : 0,
    statesChanged ? 1 : 0,
    sortBy !== 'closest' ? 1 : 0,
  ].reduce((a, b) => a + b, 0);

  const renderEventGrid = () => {
    if (filteredEvents.length > 0) {
      return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredEvents.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      );
    }

    if (isLoading) {
      return <EventGridSkeleton count={6} />;
    }

    return <EmptyEvents hasFilter={hasActiveFilter} />;
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
          {events && (
            <span className="text-sm text-muted-foreground">
              {hasActiveFilter ? `${filteredEvents.length} of ${events.length}` : `${events.length} total`}
            </span>
          )}
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

      {/* Search + Filter bar */}
      <div className="flex items-end gap-3 mb-6">
        {/* Search — always visible */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search events..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 shadow-md hover:shadow-lg hover:bg-accent dark:hover:bg-input/95 transition-all"
            data-testid="events-search-input"
          />
        </div>

        {/* Desktop filters — hidden on mobile */}
        <div className="hidden md:flex gap-3">
          <FilterControls
            selectedOrgId={selectedOrgId}
            setOrgFilter={setOrgFilter}
            organizations={organizations}
            selectedStates={selectedStates}
            toggleState={(v) => setSelectedStates((prev) => {
              const next = new Set(prev);
              if (next.has(v)) next.delete(v); else next.add(v);
              return next;
            })}
            sortBy={sortBy}
            setSortBy={setSortBy}
          />
        </div>

        {/* Mobile filter button — shown on mobile only */}
        <div className="md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" className="relative" data-testid="events-filter-btn">
                <Filter className="h-4 w-4" />
                {activeFilterCount > 0 && (
                  <Badge className="absolute -top-1.5 -right-1.5 h-4 w-4 p-0 flex items-center justify-center text-[10px] bg-primary">
                    {activeFilterCount}
                  </Badge>
                )}
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-80">
              <SheetHeader>
                <SheetTitle>Filters</SheetTitle>
              </SheetHeader>
              <div className="flex flex-col gap-5 mt-6">
                <FilterControls
                  selectedOrgId={selectedOrgId}
                  setOrgFilter={setOrgFilter}
                  organizations={organizations}
                  selectedStates={selectedStates}
                  toggleState={(v) => setSelectedStates((prev) => {
                    const next = new Set(prev);
                    if (next.has(v)) next.delete(v); else next.add(v);
                    return next;
                  })}
                  sortBy={sortBy}
                  setSortBy={setSortBy}
                  vertical
                />
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {/* Tabs: Events / Series */}
      <Tabs defaultValue="events">
        <TabsList className="mb-4">
          <TabsTrigger value="events" data-testid="events-tab-events">
            Events {filteredEvents.length > 0 ? `(${filteredEvents.length})` : ''}
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
