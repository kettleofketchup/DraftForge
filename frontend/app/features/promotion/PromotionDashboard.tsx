import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { SecondaryButton } from '~/components/ui/buttons';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { cn } from '~/lib/utils';
import { CandidateList } from './CandidateList';
import { ComposePanel } from './ComposePanel';
import { usePreviewOptions } from './feedback';
import { usePromoEvents, usePromoTemplates } from './queries';
import {
  DEFAULT_CANDIDATE_FILTERS,
  type CandidateFilters,
  type CandidateRow,
  type PromoEvent,
  type PromoSendResult,
} from './schemas';

export interface PromotionDashboardProps {
  orgId: number;
  access: OrgFeatureAccess;
}

function formatEventTime(iso: string, locale: string, timeZone: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone,
    }).format(date);
  } catch {
    return date.toISOString();
  }
}

export function PromotionDashboard({ orgId, access }: PromotionDashboardProps) {
  const [searchParams] = useSearchParams();
  const requestedEvent = Number(searchParams.get('event'));
  const events = usePromoEvents(orgId, access);
  const templates = usePromoTemplates(orgId, access);
  const previewOptions = usePreviewOptions();

  const [eventId, setEventId] = useState<number | null>(null);
  const [filters, setFilters] = useState<CandidateFilters>(DEFAULT_CANDIDATE_FILTERS);
  const [candidate, setCandidate] = useState<CandidateRow | null>(null);
  const [justSent, setJustSent] = useState<number | null>(null);

  const resetEvent = useCallback((id: number | null): void => {
    setEventId(id);
    setCandidate(null);
    setJustSent(null);
  }, []);

  useEffect(() => {
    if (eventId != null || !events.data) return;
    if (events.data.some((e) => e.id === requestedEvent)) resetEvent(requestedEvent);
  }, [eventId, events.data, requestedEvent, resetEvent]);

  useEffect(() => {
    if (eventId != null && events.data && !events.data.some((e) => e.id === eventId)) {
      resetEvent(null);
    }
  }, [eventId, events.data, resetEvent]);

  const selectEvent = (event: PromoEvent): void => resetEvent(event.id);
  const onSent = useCallback((send: PromoSendResult | null) => {
    setJustSent(send?.id ?? null);
  }, []);
  const onSelectCandidate = (row: CandidateRow): void => {
    setCandidate(row);
    setJustSent(null);
  };

  const selectedEvent = events.data?.find((e) => e.id === eventId) ?? null;

  return (
    <div className="flex flex-col gap-4" data-testid="promo-dashboard">
      <section className="flex flex-col gap-2">
        <h3 className="font-semibold">Upcoming events</h3>
        {events.isLoading && <p className="text-sm text-muted-foreground">Loading events...</p>}
        {events.isError && (
          <p className="text-sm text-destructive" data-testid="promo-events-error">
            {extractApiError(events.error) ?? 'Could not load events.'}
          </p>
        )}
        {events.data && events.data.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="promo-events-empty">
            No upcoming events to promote.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {events.data?.map((event) => (
            <SecondaryButton
              key={event.id}
              type="button"
              onClick={() => selectEvent(event)}
              aria-pressed={event.id === eventId}
              className={cn('h-auto flex-col items-start py-2', event.id === eventId && 'ring-2 ring-primary')}
              data-testid={`promo-event-${event.id}`}
            >
              <span className="font-medium">{event.name}</span>
              <span className="text-xs text-muted-foreground">
                {formatEventTime(event.scheduled_at, previewOptions.locale, previewOptions.timeZone)}
              </span>
            </SecondaryButton>
          ))}
        </div>
      </section>

      {selectedEvent && (
        <div className="grid gap-4 lg:grid-cols-2">
          <CandidateList
            key={selectedEvent.id}
            orgId={orgId}
            access={access}
            eventId={selectedEvent.id}
            filters={filters}
            onFiltersChange={setFilters}
            selectedPk={candidate?.user_pk ?? null}
            onSelect={onSelectCandidate}
            hideUndoFor={justSent}
          />
          {candidate ? (
            <ComposePanel
              key={`${selectedEvent.id}-${candidate.user_pk}`}
              orgId={orgId}
              access={access}
              event={selectedEvent}
              candidate={candidate}
              templates={templates.data ?? []}
              onSent={onSent}
            />
          ) : (
            <p className="text-sm text-muted-foreground" data-testid="promo-pick-player">
              Pick a player to write a message.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
