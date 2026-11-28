import { useState } from 'react';
import { toast } from 'sonner';

import { DOCS_BASE } from '~/components/feature/FeatureCard';
import { SecondaryButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Skeleton } from '~/components/ui/skeleton';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  useConnectionDeliveries,
  usePromotionOutbox,
  useResumeDeliveries,
  useResumePromotion,
  useResyncDeliveries,
  useSendPromotionBacklog,
} from './connectionQueries';
import {
  connectionErrorCode,
  connectionErrorMessage,
  type ApiConnection,
  type ConnectionDelivery,
  type PromotionOutbox,
} from './connectionSchemas';

const log = getLogger('ConnectionRecoveryPanel');

export const PROMOTION_OPERATOR_DOCS = `${DOCS_BASE}/features/promotion-contact-sync/`;

type Confirm = 'resync' | 'backlog' | null;

export interface ConnectionRecoveryPanelProps {
  orgId: number;
  access: OrgFeatureAccess;
  connection: ApiConnection;
  readOnly: boolean;
}

function reasonCounts(
  items: readonly ConnectionDelivery[],
): [string, number][] {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (item.state !== 'paused' || !item.last_reason) continue;
    counts.set(item.last_reason, (counts.get(item.last_reason) ?? 0) + 1);
  }
  return [...counts.entries()];
}

function errorText(err: unknown, fallback: string): string {
  const code = connectionErrorCode(err);
  return code
    ? connectionErrorMessage(code)
    : (extractApiError(err) ?? fallback);
}

export function ConnectionRecoveryPanel({
  orgId,
  access,
  connection,
  readOnly,
}: ConnectionRecoveryPanelProps) {
  const deliveries = useConnectionDeliveries(
    orgId,
    access,
    connection.id,
    null,
  );
  const outbox = usePromotionOutbox(
    orgId,
    access,
    connection.id,
    connection.promotion_stream,
  );
  const resume = useResumeDeliveries(orgId, access);
  const resync = useResyncDeliveries(orgId, access);
  const resumePromotion = useResumePromotion(orgId, access);
  const sendBacklog = useSendPromotionBacklog(orgId, access);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('');

  const act = async (
    label: string,
    action: () => Promise<number>,
    done: (n: number) => string,
  ): Promise<void> => {
    setError(null);
    try {
      const n = await action();
      const message = done(n);
      setStatus(message);
      toast.success(message);
    } catch (err) {
      log.error('Connection recovery failed', {
        orgId,
        connectionId: connection.id,
        action: label,
        code: connectionErrorCode(err),
      });
      setError(errorText(err, 'The action failed'));
    }
  };

  const counts = deliveries.data?.counts;
  const reasons = reasonCounts(deliveries.data?.items ?? []);
  const originChanged = reasons.some(([reason]) => reason === 'origin_changed');
  const unsent = counts ? counts.pending + counts.retry + counts.paused : 0;
  const held = outbox.data?.counts.backlog_held ?? 0;
  const version = connection.config_version;
  const locked = readOnly || Boolean(connection.archived_at);

  return (
    <div className="flex flex-col gap-6" data-testid="api-connection-recovery">
      <p className="sr-only" aria-live="polite">
        {status}
      </p>
      {error && (
        <p
          role="alert"
          className="text-sm font-medium text-destructive"
          data-testid="api-connection-recovery-error"
        >
          {error}
        </p>
      )}

      <section
        className="flex flex-col gap-3"
        aria-labelledby="api-connection-deliveries-heading"
      >
        <h3
          id="api-connection-deliveries-heading"
          className="text-base font-semibold"
        >
          MMR push deliveries
        </h3>
        {deliveries.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : deliveries.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {extractApiError(deliveries.error) ?? 'Failed to load deliveries'}
          </p>
        ) : counts ? (
          <>
            <dl
              className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4"
              data-testid="api-connection-delivery-counts"
            >
              {(['pending', 'in_flight', 'retry', 'paused'] as const).map(
                (state) => (
                  <div key={state} className="flex flex-col">
                    <dt className="text-xs text-muted-foreground">
                      {DELIVERY_LABELS[state]}
                    </dt>
                    <dd data-testid={`api-connection-delivery-count-${state}`}>
                      {counts[state]}
                    </dd>
                  </div>
                ),
              )}
            </dl>
            {reasons.length > 0 && (
              <ul
                className="flex flex-col gap-1 text-xs"
                data-testid="api-connection-delivery-reasons"
              >
                {reasons.map(([reason, n]) => (
                  <li key={reason}>
                    {n} paused: {connectionErrorMessage(reason)}
                  </li>
                ))}
              </ul>
            )}
            {originChanged && (
              <p
                className="text-sm text-warning"
                data-testid="api-connection-origin-resync"
              >
                The destination changed. Resume cannot send these to the new
                destination; resync sends each member&apos;s current MMR there
                instead.
              </p>
            )}
            {!locked && (
              <div className="flex flex-wrap gap-2">
                <SecondaryButton
                  type="button"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  disabled={counts.paused === 0 || resume.isPending}
                  onClick={() =>
                    void act(
                      'resume_deliveries',
                      () =>
                        resume.mutateAsync({
                          connectionId: connection.id,
                          configVersion: version,
                        }),
                      (n) => `${n} paused deliveries will be retried`,
                    )
                  }
                  data-testid="api-connection-deliveries-resume"
                >
                  Resume paused
                </SecondaryButton>
                <SecondaryButton
                  type="button"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  disabled={resync.isPending}
                  onClick={() => setConfirm('resync')}
                  data-testid="api-connection-deliveries-resync"
                >
                  Resync current state
                </SecondaryButton>
              </div>
            )}
            {counts.paused > 0 && !originChanged && (
              <p className="text-xs text-muted-foreground">
                Fix the cause first: replace a rejected credential or correct
                the push settings and save, then resume.
              </p>
            )}
          </>
        ) : null}
      </section>

      {connection.promotion_stream && (
        <PromotionRecovery
          outbox={outbox.data}
          loading={outbox.isLoading}
          loadError={outbox.isError ? outbox.error : null}
          locked={locked}
          resumePending={resumePromotion.isPending}
          backlogPending={sendBacklog.isPending}
          onResume={() =>
            void act(
              'resume_promotion',
              () => resumePromotion.mutateAsync(connection.id),
              (n) => `${n} paused promotion sends will be retried`,
            )
          }
          onSendBacklog={() => setConfirm('backlog')}
        />
      )}

      <ConfirmDialog
        open={confirm === 'resync'}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
        title="Resync current MMRs?"
        description={`${unsent} unsent deliveries are canceled, and every member's current MMR is queued for ${connection.outbound_base_url || 'the destination'} at a new revision. Large organizations are queued in batches of 500.`}
        confirmLabel="Resync"
        variant="warning"
        isLoading={resync.isPending}
        onConfirm={async () => {
          await act(
            'resync_deliveries',
            () =>
              resync.mutateAsync({
                connectionId: connection.id,
                configVersion: version,
              }),
            (n) => `${n} current MMRs queued`,
          );
          setConfirm(null);
        }}
        confirmTestId="api-connection-resync-confirm"
        cancelTestId="api-connection-resync-cancel"
      />
      <ConfirmDialog
        open={confirm === 'backlog'}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
        title={`Send ${held} held promotion ${held === 1 ? 'send' : 'sends'}?`}
        description={`These ${held} sends were recorded before external recording was set up for their events. Sending them records them externally now. If the count changes first, you will be asked again.`}
        confirmLabel={`Send ${held}`}
        variant="warning"
        isLoading={sendBacklog.isPending}
        onConfirm={async () => {
          await act(
            'send_backlog',
            () =>
              sendBacklog.mutateAsync({
                connectionId: connection.id,
                confirmedCount: held,
              }),
            (n) => `${n} held sends released`,
          );
          setConfirm(null);
        }}
        confirmTestId="api-connection-backlog-confirm"
        cancelTestId="api-connection-backlog-cancel"
      />
    </div>
  );
}

const DELIVERY_LABELS = {
  pending: 'Waiting',
  in_flight: 'Sending',
  retry: 'Retrying',
  paused: 'Paused',
} as const;

function PromotionRecovery({
  outbox,
  loading,
  loadError,
  locked,
  resumePending,
  backlogPending,
  onResume,
  onSendBacklog,
}: {
  outbox: PromotionOutbox | undefined;
  loading: boolean;
  loadError: unknown;
  locked: boolean;
  resumePending: boolean;
  backlogPending: boolean;
  onResume: () => void;
  onSendBacklog: () => void;
}) {
  const counts = outbox?.counts;
  const reconciliation = counts?.reconciliation_required ?? 0;
  return (
    <section
      className="flex flex-col gap-3 border-t border-border pt-4"
      aria-labelledby="api-connection-outbox-heading"
      data-testid="api-connection-promotion-recovery"
    >
      <h3
        id="api-connection-outbox-heading"
        className="text-base font-semibold"
      >
        Promotion sends
      </h3>
      {loading ? (
        <Skeleton className="h-12 w-full" />
      ) : loadError ? (
        <p role="alert" className="text-sm text-destructive">
          {extractApiError(loadError) ?? 'Failed to load promotion sends'}
        </p>
      ) : counts ? (
        <>
          <dl
            className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4"
            data-testid="api-connection-outbox-counts"
          >
            {(
              [
                ['pending', 'Waiting'],
                ['retry', 'Retrying'],
                ['paused', 'Paused'],
                ['backlog_held', 'Held backlog'],
                ['reconciliation_required', 'Needs review'],
                ['applied', 'Recorded'],
              ] as const
            ).map(([state, label]) => (
              <div key={state} className="flex flex-col">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd data-testid={`api-connection-outbox-count-${state}`}>
                  {counts[state]}
                </dd>
              </div>
            ))}
          </dl>
          {Object.entries(outbox?.reasons.paused ?? {}).length > 0 && (
            <ul className="flex flex-col gap-1 text-xs">
              {Object.entries(outbox?.reasons.paused ?? {}).map(
                ([reason, n]) => (
                  <li key={reason}>
                    {n} paused: {connectionErrorMessage(reason)}
                  </li>
                ),
              )}
            </ul>
          )}
          {!locked && (
            <div className="flex flex-wrap gap-2">
              <SecondaryButton
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                disabled={counts.paused === 0 || resumePending}
                onClick={onResume}
                data-testid="api-connection-promotion-resume"
              >
                Resume paused
              </SecondaryButton>
              <SecondaryButton
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                disabled={counts.backlog_held === 0 || backlogPending}
                onClick={onSendBacklog}
                data-testid="api-connection-promotion-send-backlog"
              >
                Send backlog ({counts.backlog_held})
              </SecondaryButton>
            </div>
          )}
          {reconciliation > 0 && (
            <p className="text-sm" data-testid="api-connection-reconciliation">
              {reconciliation}{' '}
              {reconciliation === 1 ? 'send needs' : 'sends need'} review by a
              site operator before they can be recorded externally. There is no
              action here.{' '}
              <a
                href={PROMOTION_OPERATOR_DOCS}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-2"
              >
                Operator instructions
              </a>
            </p>
          )}
        </>
      ) : null}
    </section>
  );
}
