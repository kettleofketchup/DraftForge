import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';

import { SecondaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Skeleton } from '~/components/ui/skeleton';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  usePromotionStream,
  useSetPromotionBinding,
} from './connectionQueries';
import {
  CONNECTION_OPERATIONS,
  connectionErrorCode,
  connectionErrorMessage,
  type ApiConnection,
  type ConnectionForm,
  type PromotionEventBinding,
  type PromotionStream,
} from './connectionSchemas';
import {
  ActionNote,
  DirectionSwitch,
  featureLockReason,
  testBlockedReason,
  useConnectionTestAction,
} from './connectionSyncShared';

const log = getLogger('ConnectionPromotionTab');

const TRANSPORT_LABELS: Record<PromotionStream['transport'], string> = {
  env: 'Sending through the server configuration',
  connection: 'Sending through this connection',
  held: 'Held: sends wait until promotion push is on and events are bound',
  none: 'Not sending',
};

export interface ConnectionPromotionTabProps {
  form: UseFormReturn<ConnectionForm>;
  saved: ApiConnection | null;
  dirty: boolean;
  readOnly: boolean;
  orgId: number;
  access: OrgFeatureAccess;
  onRunStarted?: (runId: string) => void;
}

export function promotionPushLockedReason(
  saved: ApiConnection | null,
  access: Pick<OrgFeatureAccess, 'mmrSyncEnabled' | 'promotionEnabled'>,
): string | null {
  const feature = featureLockReason(access, 'promotion');
  if (feature) return feature;
  if (!saved?.promotion_stream) {
    return "Only the organization's promotion connection can push contacts. Bind events below first.";
  }
  return null;
}

export function ConnectionPromotionTab({
  form,
  saved,
  dirty,
  readOnly,
  orgId,
  access,
  onRunStarted,
}: ConnectionPromotionTabProps) {
  const stream = usePromotionStream(orgId, access, access.promotionEnabled);
  const test = useConnectionTestAction(orgId, access, saved, onRunStarted);
  const testReason = testBlockedReason(saved, dirty);
  const grants = CONNECTION_OPERATIONS.filter(
    (op) => op.feature === 'promotion',
  );
  const savedOps = saved?.operations ?? [];

  return (
    <div
      className="flex flex-col gap-6"
      data-testid="api-connection-promotion-tab"
    >
      <DirectionSwitch
        form={form}
        name="promotion_push_enabled"
        label="Promotion push"
        help="DraftForge records the organization's promotion sends in the external contact log. Needs bearer authentication. Off by default."
        readOnly={readOnly}
        lockedReason={promotionPushLockedReason(saved, access)}
      />

      <section
        className="flex flex-col gap-2"
        aria-labelledby="api-connection-promotion-grants"
      >
        <h3
          id="api-connection-promotion-grants"
          className="text-base font-semibold"
        >
          Inbound promotion grants
        </h3>
        <p className="text-xs text-muted-foreground">
          Change grants on the Inbound key tab.
        </p>
        <ul
          className="flex flex-col gap-1 text-sm"
          data-testid="api-connection-promotion-grant-list"
        >
          {grants
            .filter((op) => !op.legacy || savedOps.includes(op.value))
            .map((op) => (
              <li key={op.value} className="flex flex-col">
                <span>
                  {op.label}:{' '}
                  <span className="font-medium">
                    {savedOps.includes(op.value) ? 'granted' : 'not granted'}
                  </span>
                </span>
                <code className="font-mono text-xs text-muted-foreground">
                  {op.route}
                </code>
              </li>
            ))}
        </ul>
      </section>

      <section
        className="flex flex-col gap-3"
        aria-labelledby="api-connection-promotion-stream"
      >
        <h3
          id="api-connection-promotion-stream"
          className="text-base font-semibold"
        >
          Promotion stream
        </h3>
        {!access.promotionEnabled ? (
          <p className="text-sm text-muted-foreground">
            Promotion is locked for this organization.
          </p>
        ) : stream.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : stream.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {extractApiError(stream.error) ??
              'Failed to load the promotion stream'}
          </p>
        ) : stream.data ? (
          <StreamStatus
            stream={stream.data}
            saved={saved}
            readOnly={readOnly}
            orgId={orgId}
            access={access}
          />
        ) : null}
      </section>

      <section
        className="flex flex-col gap-3 border-t border-border pt-4"
        aria-labelledby="api-connection-promotion-test"
      >
        <h3
          id="api-connection-promotion-test"
          className="text-base font-semibold"
        >
          Test
        </h3>
        <p className="text-xs text-muted-foreground">
          Checks GET /health on the saved destination only. It sends no contact
          data and works while the push is off.
        </p>
        <div>
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={
              testReason !== null || test.pending || !access.promotionEnabled
            }
            onClick={() => void test.run('promotion_push')}
            data-testid="api-connection-promotion-test"
          >
            Test destination health
          </SecondaryButton>
        </div>
        <ActionNote
          reason={testReason}
          error={test.error}
          testId="api-connection-promotion-action"
        />
      </section>
    </div>
  );
}

function StreamStatus({
  stream,
  saved,
  readOnly,
  orgId,
  access,
}: {
  stream: PromotionStream;
  saved: ApiConnection | null;
  readOnly: boolean;
  orgId: number;
  access: OrgFeatureAccess;
}) {
  if (stream.source === 'deployment' && !stream.adopted) {
    return (
      <div
        className="flex flex-col gap-2"
        data-testid="api-connection-promotion-deployment"
      >
        <p className="text-sm">
          This organization&apos;s promotion sync is set in the server
          configuration. It is read-only here; a site operator can move it onto
          a connection.
        </p>
        <p className="text-xs text-muted-foreground">
          {TRANSPORT_LABELS[stream.transport]}
        </p>
        <BindingList stream={stream} />
      </div>
    );
  }
  const mine = saved !== null && stream.connection_id === saved.id;
  if (stream.source === 'connection' && !mine) {
    return (
      <p className="text-sm" data-testid="api-connection-promotion-elsewhere">
        Another connection carries this organization&apos;s promotion stream. An
        organization has one stream.
      </p>
    );
  }
  return (
    <div
      className="flex flex-col gap-3"
      data-testid="api-connection-promotion-own"
    >
      {mine ? (
        <p className="text-sm">
          This connection carries the promotion stream.{' '}
          <span className="text-muted-foreground">
            {TRANSPORT_LABELS[stream.transport]}
          </span>
        </p>
      ) : (
        <p className="text-sm">
          No connection carries promotion sends yet. Binding events here makes
          this connection the organization&apos;s promotion stream.
        </p>
      )}
      {saved && !readOnly ? (
        <BindingEditor
          key={JSON.stringify(stream.events)}
          stream={stream}
          connectionId={saved.id}
          orgId={orgId}
          access={access}
        />
      ) : (
        <>
          {!saved && (
            <p className="text-xs text-muted-foreground">
              Save the connection before binding events.
            </p>
          )}
          <BindingList stream={stream} />
        </>
      )}
    </div>
  );
}

function BindingList({ stream }: { stream: PromotionStream }) {
  if (stream.events.length === 0) {
    return <p className="text-xs text-muted-foreground">No events bound.</p>;
  }
  return (
    <ul
      className="flex flex-col gap-1 text-xs"
      data-testid="api-connection-promotion-events"
    >
      {stream.events.map((e) => (
        <li key={e.event_id}>
          Event {e.event_id} → occasion {e.occasion_id}
        </li>
      ))}
    </ul>
  );
}

const DIGITS = /^[1-9][0-9]{0,19}$/;

function BindingEditor({
  stream,
  connectionId,
  orgId,
  access,
}: {
  stream: PromotionStream;
  connectionId: number;
  orgId: number;
  access: OrgFeatureAccess;
}) {
  const save = useSetPromotionBinding(orgId, access);
  const [rows, setRows] = useState<PromotionEventBinding[]>(() =>
    stream.events.map(({ event_id, occasion_id }) => ({
      event_id,
      occasion_id,
    })),
  );
  const [error, setError] = useState<string | null>(null);
  const valid = rows.every(
    (r) => DIGITS.test(r.event_id.trim()) && DIGITS.test(r.occasion_id.trim()),
  );
  const update = (index: number, patch: Partial<PromotionEventBinding>): void =>
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );

  const submit = async (): Promise<void> => {
    setError(null);
    try {
      await save.mutateAsync({
        connectionId,
        events: rows.map((r) => ({
          event_id: r.event_id.trim(),
          occasion_id: r.occasion_id.trim(),
        })),
      });
      toast.success('Event bindings saved');
    } catch (err) {
      const code = connectionErrorCode(err);
      log.error('Failed to save promotion bindings', {
        orgId,
        connectionId,
        code,
      });
      setError(
        code
          ? connectionErrorMessage(code)
          : (extractApiError(err) ?? 'Could not save the bindings'),
      );
    }
  };

  return (
    <div
      className="flex flex-col gap-3"
      data-testid="api-connection-promotion-binding"
    >
      <p className="text-xs text-muted-foreground">
        Each DraftForge event maps to one external occasion. Bindings save on
        their own, separately from the connection settings. A binding with
        imported contacts cannot change.
      </p>
      <ul className="flex flex-col gap-2">
        {rows.map((row, index) => (
          <li
            key={index}
            className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          >
            <div className="flex flex-col gap-1">
              <Label
                htmlFor={`api-connection-binding-event-${index}`}
                className="text-xs"
              >
                Event ID
              </Label>
              <Input
                id={`api-connection-binding-event-${index}`}
                inputMode="numeric"
                value={row.event_id}
                onChange={(e) => update(index, { event_id: e.target.value })}
                data-testid={`api-connection-binding-event-${index}`}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label
                htmlFor={`api-connection-binding-occasion-${index}`}
                className="text-xs"
              >
                Occasion ID
              </Label>
              <Input
                id={`api-connection-binding-occasion-${index}`}
                inputMode="numeric"
                value={row.occasion_id}
                onChange={(e) => update(index, { occasion_id: e.target.value })}
                data-testid={`api-connection-binding-occasion-${index}`}
              />
            </div>
            <SecondaryButton
              type="button"
              size="sm"
              color="red"
              className="min-h-11 sm:min-h-8"
              onClick={() => setRows((c) => c.filter((_, i) => i !== index))}
              aria-label={`Remove binding ${index + 1}`}
            >
              Remove
            </SecondaryButton>
          </li>
        ))}
      </ul>
      {!valid && (
        <p className="text-xs text-destructive" role="alert">
          IDs are positive whole numbers.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <SecondaryButton
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() =>
            setRows((c) => [...c, { event_id: '', occasion_id: '' }])
          }
          data-testid="api-connection-binding-add"
        >
          Add event
        </SecondaryButton>
        <SecondaryButton
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          disabled={!valid || save.isPending}
          onClick={() => void submit()}
          data-testid="api-connection-binding-save"
        >
          Save event bindings
        </SecondaryButton>
      </div>
      {error && (
        <p
          role="alert"
          className="text-sm font-medium text-destructive"
          data-testid="api-connection-binding-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}
