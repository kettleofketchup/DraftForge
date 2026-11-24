import { RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, type ReactNode } from 'react';
import { toast } from 'sonner';

import { SecondaryButton } from '~/components/ui/buttons';
import { DataTable } from '~/components/ui/data-table';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

import { httpStatus, retryAfterSeconds } from './api';
import { makeBotAccessColumns } from './botAccessColumns';
import { getBotAccessProvider } from './providers';
import { useBotAccess, useRefreshBotAccess } from './queries';
import type { BotAccessRow, BotAccessSnapshot, ServiceStatus } from './schemas';

const log = getLogger('bot-access');

const UNREACHABLE =
  "The lobby service couldn't be reached, so bot access is unknown. Try again shortly.";

const SERVICE_MESSAGE: Partial<Record<ServiceStatus, string>> = {
  unavailable: UNREACHABLE,
  error: UNREACHABLE,
  disabled: "Hosted lobbies aren't enabled on this site.",
  not_configured: "Hosted lobbies aren't enabled on this site.",
  unsupported: "Lobby bot management isn't available for this game yet.",
};

const HOLDERS_ONLY_NOTE =
  'Only bots that already have access to this league are listed. Ask a site admin for the profile links of the other lobby bots.';

const REFRESHABLE: ReadonlySet<ServiceStatus> = new Set([
  'ok',
  'unavailable',
  'error',
]);

const REFRESH_OUTCOME_NOTE: Partial<
  Record<NonNullable<BotAccessSnapshot['refresh_outcome']>, string>
> = {
  timed_out: 'The check is still running. Refresh again shortly.',
  unavailable:
    "The lobby service couldn't be reached, so access wasn't re-checked.",
  not_supported_upstream:
    "The lobby service can't re-check league access right now, so the last results are shown.",
};

function tryAgainMessage(err: unknown): string {
  const seconds = retryAfterSeconds(err);
  return seconds === null
    ? 'Too many requests. Try again shortly.'
    : `Try again in ${seconds} s`;
}

function withDetail(message: string, err: unknown): string {
  const detail = extractApiError(err);
  return detail ? `${message} ${detail}` : message;
}

function withRowRefresh(
  rows: BotAccessRow[],
  refreshed: BotAccessSnapshot | undefined,
): BotAccessRow[] {
  if (!refreshed) return rows;
  const byPosition = new Map(
    refreshed.bots.map((b) => [b.position, b.refresh]),
  );
  return rows.map((r) => ({
    ...r,
    refresh: r.refresh ?? byPosition.get(r.position) ?? null,
  }));
}

export interface BotAccessPanelProps {
  leagueId: number;
  enabled: boolean;
}

/** Lists the platform's lobby bots and their access to this league's external league. */
export function BotAccessPanel({ leagueId, enabled }: BotAccessPanelProps) {
  const query = useBotAccess(leagueId, enabled);
  const refresh = useRefreshBotAccess(leagueId);
  const snapshot = query.data;
  const loggedError = useRef<unknown>(null);

  const queryError = snapshot ? null : query.error;
  const queryStatus = queryError ? httpStatus(queryError) : null;

  useEffect(() => {
    if (!queryError || queryError === loggedError.current) return;
    if (queryStatus === 404 || queryStatus === 429) return;
    loggedError.current = queryError;
    log.error('Bot access load failed', queryError);
  }, [queryError, queryStatus]);

  const onCopy = useCallback(async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success('Link copied');
    } catch (err) {
      log.warn('Copying the profile link failed', err);
      toast.error("Couldn't copy the link.");
    }
  }, []);

  const copy = getBotAccessProvider(snapshot?.provider ?? '');
  const columns = useMemo(
    () =>
      makeBotAccessColumns({
        onCopy: (url) => void onCopy(url),
        identityLabel: copy.identityLabel,
      }),
    [onCopy, copy.identityLabel],
  );
  const rows = useMemo(
    () => withRowRefresh(snapshot?.bots ?? [], refresh.data),
    [snapshot, refresh.data],
  );

  const onRefresh = () =>
    refresh.mutate(undefined, {
      onError: (err) => {
        if (httpStatus(err) === 429) {
          toast.error(tryAgainMessage(err));
          return;
        }
        log.error('Bot access refresh failed', err);
        toast.error(withDetail("Couldn't re-check bot access.", err));
      },
    });

  const service = snapshot?.service.status;
  const outcome = refresh.data?.refresh_outcome;
  const outcomeNote = outcome ? REFRESH_OUTCOME_NOTE[outcome] : undefined;

  let body: ReactNode = null;
  if (queryError) {
    const message =
      queryStatus === 404
        ? "You don't have access to lobby bots for this league."
        : queryStatus === 429
          ? tryAgainMessage(queryError)
          : withDetail("Couldn't load lobby bots.", queryError);
    body = (
      <div className="flex flex-col items-start gap-3">
        <p
          role="alert"
          className="text-sm text-muted-foreground"
          data-testid="bot-access-query-error"
        >
          {message}
        </p>
        {queryStatus !== 404 ? (
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            data-testid="bot-access-retry"
            onClick={() => void query.refetch()}
          >
            Retry
          </SecondaryButton>
        ) : null}
      </div>
    );
  } else if (snapshot && service === 'ok') {
    body = (
      <div className="flex flex-col gap-4">
        <copy.Help snapshot={snapshot} />
        {snapshot.roster === 'holders' ? (
          <p
            className="text-sm text-muted-foreground"
            data-testid="bot-access-roster-note"
          >
            {HOLDERS_ONLY_NOTE}
          </p>
        ) : null}
        {outcomeNote ? (
          <p
            role="status"
            className="text-sm text-warning"
            data-testid="bot-access-refresh-outcome"
          >
            {outcomeNote}
          </p>
        ) : null}
        <DataTable
          columns={columns}
          data={rows}
          getRowId={(r) => String(r.position)}
          getRowTestId={(r) => `bot-access-row-${r.position}`}
          emptyMessage={
            snapshot.roster === 'holders'
              ? 'No lobby bots have access to this league yet.'
              : 'No lobby bots are configured.'
          }
          data-testid="bot-access-table"
        />
      </div>
    );
  } else if (snapshot && service) {
    const message =
      service === 'league_not_linked'
        ? copy.notLinkedMessage
        : SERVICE_MESSAGE[service];
    body = (
      <p
        role="status"
        className={
          service === 'unavailable' || service === 'error'
            ? 'text-sm text-warning'
            : 'text-sm text-muted-foreground'
        }
        data-testid="bot-access-service-message"
      >
        {message}
      </p>
    );
  } else if (enabled) {
    body = <p className="text-sm text-muted-foreground">Loading lobby bots…</p>;
  }

  return (
    <section className="flex flex-col gap-4" data-testid="bot-access-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Lobby bots</h2>
        {snapshot && service && REFRESHABLE.has(service) && !queryError ? (
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            data-testid="bot-access-refresh"
            disabled={refresh.isPending}
            onClick={onRefresh}
          >
            <RefreshCw
              className={refresh.isPending ? 'size-4 animate-spin' : 'size-4'}
              aria-hidden="true"
            />
            Refresh access
          </SecondaryButton>
        ) : null}
      </div>
      {body}
    </section>
  );
}
