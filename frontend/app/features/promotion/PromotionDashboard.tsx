import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { usePreviewOptions } from '~/components/discord/timestamps';
import { GAME_LABEL, toGameType } from '~/components/game/constants';
import { SecondaryButton } from '~/components/ui/buttons';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { CandidateList } from './CandidateList';
import { reportPromoError } from './feedback';
import { candidateRowId, type ComposeMode } from './promotionColumns';
import {
  PromotionMessageDialog,
  type PromotionComposer,
} from './PromotionMessageDialog';
import {
  useCandidates,
  usePromoEvents,
  usePromoTemplates,
  useResolveDiscordMember,
} from './queries';
import {
  DEFAULT_CANDIDATE_FILTERS,
  isLinked,
  type CandidateFilters,
  type CandidateRow,
  type PromoEvent,
  type PromoSendResult,
} from './schemas';

const log = getLogger('PromotionDashboard');

export interface PromotionDashboardProps {
  orgId: number;
  access: OrgFeatureAccess;
}

function formatEventTime(
  iso: string,
  locale: string,
  timeZone: string,
): string {
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
  const [filters, setFilters] = useState<CandidateFilters>(
    DEFAULT_CANDIDATE_FILTERS,
  );
  const [composer, setComposer] = useState<PromotionComposer | null>(null);
  const [justSent, setJustSent] = useState<number | null>(null);
  const [pendingRowId, setPendingRowId] = useState<string | null>(null);
  // Bumped whenever the recipient context changes; a resolve that settles
  // under an older value is dropped instead of opening a stale composer.
  const contextToken = useRef(0);
  const resolve = useResolveDiscordMember(orgId, access, eventId ?? 0);

  // The same query CandidateList renders, so this adds no request.
  const candidates = useCandidates(orgId, access, eventId, filters);
  const filtersKey = JSON.stringify(filters);
  const [picked, setPicked] = useState<{
    key: string;
    at: number;
    sent: boolean;
  } | null>(null);

  const closeComposer = useCallback((): void => {
    contextToken.current += 1;
    setComposer(null);
    setJustSent(null);
    setPendingRowId(null);
    setPicked(null);
  }, []);

  // An open composer goes stale when list data fetched after the pick shows
  // a recorded external contact, under any filters, or when the list it was
  // opened from, with messaged players hidden, no longer lists the player.
  // Other filters can leave a row out for unrelated reasons, so only the
  // pick's own filters count a missing row. Once the dialog has marked a send,
  // a missing row is its own send (or the list catching up after its undo).
  const { data: rows, dataUpdatedAt, isPlaceholderData } = candidates;
  const candidatePk = composer?.candidate.user_pk ?? null;
  const candidateDiscordId = composer?.candidate.discordId ?? null;
  useEffect(() => {
    if (candidatePk == null || justSent != null || picked == null) return;
    if (!rows || isPlaceholderData || dataUpdatedAt <= picked.at) return;
    // A Discord member resolved to an account may still be listed by Discord ID.
    const row = rows.rows.find(
      (r) =>
        r.user_pk === candidatePk ||
        (candidateDiscordId != null && r.discordId === candidateDiscordId),
    );
    const hidden =
      row == null &&
      picked.key === filtersKey &&
      filters.hideMessaged &&
      !picked.sent;
    if (row?.external_contact || hidden) closeComposer();
  }, [
    candidatePk,
    candidateDiscordId,
    justSent,
    picked,
    rows,
    dataUpdatedAt,
    isPlaceholderData,
    filtersKey,
    filters.hideMessaged,
    closeComposer,
  ]);

  const resetEvent = useCallback(
    (id: number | null): void => {
      setEventId(id);
      closeComposer();
    },
    [closeComposer],
  );

  useEffect(() => {
    if (eventId != null || !events.data) return;
    if (events.data.some((e) => e.id === requestedEvent))
      resetEvent(requestedEvent);
  }, [eventId, events.data, requestedEvent, resetEvent]);

  useEffect(() => {
    if (
      eventId != null &&
      events.data &&
      !events.data.some((e) => e.id === eventId)
    ) {
      resetEvent(null);
    }
  }, [eventId, events.data, resetEvent]);

  const selectEvent = (event: PromoEvent): void => resetEvent(event.id);
  const onSent = useCallback((send: PromoSendResult | null) => {
    setJustSent(send?.id ?? null);
  }, []);
  // Set before the request: the send's own list refetch can land first.
  const onSending = useCallback(() => {
    setPicked((p) => (p ? { ...p, sent: true } : p));
  }, []);
  // A failed send recorded nothing, so a missing row is staleness again.
  const onSendFailed = useCallback(() => {
    setPicked((p) => (p ? { ...p, sent: false } : p));
  }, []);
  const syncConfigured = candidates.data?.contact_sync.configured ?? false;

  const resolveMutate = resolve.mutate;
  const onCompose = useCallback(
    (row: CandidateRow, mode: ComposeMode): void => {
      if (row.external_contact) return;
      contextToken.current += 1;
      const token = contextToken.current;
      setJustSent(null);
      const pick = { key: filtersKey, at: dataUpdatedAt, sent: false };
      if (isLinked(row)) {
        setPendingRowId(null);
        setComposer({ candidate: row, mode });
        setPicked(pick);
        return;
      }
      if (!row.discordId || eventId == null) return;
      const rowId = candidateRowId(row);
      setComposer(null);
      setPendingRowId(rowId);
      resolveMutate(row.discordId, {
        onSuccess: (resolved) => {
          if (token !== contextToken.current) {
            log.info('promo_resolve_member_discarded', { orgId, eventId });
            return;
          }
          setPendingRowId(null);
          if (resolved.external_contact) {
            toast.info(
              'A contact with this player is already recorded externally',
            );
            return;
          }
          if (isLinked(resolved)) {
            setComposer({ candidate: resolved, mode });
            setPicked(pick);
          }
        },
        onError: (err) => {
          if (token !== contextToken.current) return;
          setPendingRowId(null);
          const message = reportPromoError(
            log,
            'promo_resolve_member_failed',
            err,
            { orgId, eventId },
          );
          toast.error(message || 'Could not prepare this member');
        },
      });
    },
    [eventId, orgId, resolveMutate, filtersKey, dataUpdatedAt],
  );

  const selectedEvent = events.data?.find((e) => e.id === eventId) ?? null;
  const gameLabel = selectedEvent
    ? GAME_LABEL[toGameType(selectedEvent.game_type)]
    : 'Game';

  return (
    <div className="flex flex-col gap-4" data-testid="promo-dashboard">
      <section className="flex flex-col gap-2">
        <h3 className="font-semibold">Upcoming events</h3>
        {events.isLoading && (
          <p className="text-sm text-muted-foreground">Loading events...</p>
        )}
        {events.isError && (
          <p
            className="text-sm text-destructive"
            data-testid="promo-events-error"
          >
            {extractApiError(events.error) ?? 'Could not load events.'}
          </p>
        )}
        {events.data && events.data.length === 0 && (
          <p
            className="text-sm text-muted-foreground"
            data-testid="promo-events-empty"
          >
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
              className={cn(
                'h-auto flex-col items-start py-2',
                event.id === eventId && 'ring-2 ring-primary',
              )}
              data-testid={`promo-event-${event.id}`}
            >
              <span className="font-medium">{event.name}</span>
              <span className="text-xs text-muted-foreground">
                {formatEventTime(
                  event.scheduled_at,
                  previewOptions.locale,
                  previewOptions.timeZone,
                )}
              </span>
            </SecondaryButton>
          ))}
        </div>
      </section>

      {selectedEvent && (
        <>
          <p
            className="text-sm text-muted-foreground"
            data-testid="promo-pick-player"
          >
            Choose an audience, then use Message on a player to write a DM, or
            Mark as sent to record one you already sent. One player at a time.
          </p>
          <CandidateList
            key={selectedEvent.id}
            orgId={orgId}
            access={access}
            eventId={selectedEvent.id}
            filters={filters}
            onFiltersChange={(next) => {
              if (next.source !== filters.source) closeComposer();
              setFilters(next);
            }}
            onCompose={onCompose}
            pendingRowId={pendingRowId}
            hideUndoFor={composer ? justSent : null}
          />
          <PromotionMessageDialog
            orgId={orgId}
            access={access}
            event={selectedEvent}
            composer={composer}
            templates={templates.data ?? []}
            gameLabel={gameLabel}
            onClose={closeComposer}
            onSent={onSent}
            onSending={onSending}
            onSendFailed={onSendFailed}
            syncConfigured={syncConfigured}
          />
        </>
      )}
    </div>
  );
}
