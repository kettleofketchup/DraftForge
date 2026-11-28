import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';

import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Switch } from '~/components/ui/switch';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  ConnectionMappingEditor,
  TemplateFieldsEditor,
} from './ConnectionMappingEditor';
import { usePullNow } from './connectionQueries';
import { RunCounters } from './connectionRunColumns';
import {
  OVERWRITE_POLICY_LABELS,
  OVERWRITE_POLICY_VALUES,
  connectionErrorCode,
  connectionErrorMessage,
  type ApiConnection,
  type ConnectionForm,
  type OverwritePolicy,
} from './connectionSchemas';
import {
  INTERVAL_MAX,
  INTERVAL_MIN,
  REQUESTS_PER_RUN,
  REQUEST_MODE_LABELS,
  estimateRequests,
  needsPerMemberAck,
  type PullForm,
} from './connectionSyncSchemas';
import {
  ActionNote,
  CredentialSlotFields,
  DirectionSwitch,
  GameTypeField,
  featureLockReason,
  pullBlockedReason,
  testBlockedReason,
  useConnectionTestAction,
} from './connectionSyncShared';

const log = getLogger('ConnectionMmrPullTab');

export interface ConnectionMmrPullTabProps {
  form: UseFormReturn<ConnectionForm>;
  /** The latest saved row; null while creating. */
  saved: ApiConnection | null;
  dirty: boolean;
  readOnly: boolean;
  orgId: number;
  access: OrgFeatureAccess;
  /** The org's saved member count, for the request estimate. */
  memberCount?: number | null;
  onRunStarted?: (runId: string) => void;
}

export function ConnectionMmrPullTab({
  form,
  saved,
  dirty,
  readOnly,
  orgId,
  access,
  memberCount,
  onRunStarted,
}: ConnectionMmrPullTabProps) {
  const auth = form.watch('outbound_auth');
  const method = form.watch('pull.method');
  const mode = form.watch('pull.request_mode');
  const pagination = form.watch('pull.pagination_kind');
  const pageSize = form.watch('pull.page_size');
  const interval = form.watch('interval_minutes');
  const bodyRows = form.watch('pull.body').length;
  const shape = {
    request_mode: mode,
    pagination_kind: pagination,
    page_size: pageSize,
  };
  const estimate = estimateRequests(shape, memberCount);
  const ack = needsPerMemberAck(shape, memberCount);

  const test = useConnectionTestAction(orgId, access, saved, onRunStarted);
  const pull = usePullNow(orgId, access);
  const [pullError, setPullError] = useState<string | null>(null);
  const testReason = testBlockedReason(saved, dirty);
  const pullReason = pullBlockedReason(saved, dirty);
  const lastRun =
    saved?.last_run_summary?.kind === 'mmr_pull'
      ? saved.last_run_summary
      : null;

  const runPull = async (): Promise<void> => {
    if (!saved) return;
    setPullError(null);
    try {
      const run = await pull.mutateAsync(saved.id);
      onRunStarted?.(run.id);
    } catch (err) {
      const code = connectionErrorCode(err);
      log.error('Failed to start pull', {
        orgId,
        connectionId: saved.id,
        code,
      });
      setPullError(
        code
          ? connectionErrorMessage(code)
          : (extractApiError(err) ?? 'Could not start the pull'),
      );
    }
  };

  return (
    <div className="flex flex-col gap-6" data-testid="api-connection-pull-tab">
      <DirectionSwitch
        form={form}
        name="mmr_pull_enabled"
        label="MMR pull"
        help="DraftForge fetches members' MMRs from the destination: on Pull now, and on the schedule below. Off by default."
        readOnly={readOnly}
        lockedReason={featureLockReason(access, 'mmr_sync')}
      />

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-base font-semibold">Request</legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[8rem_1fr]">
          <FormField
            control={form.control}
            name="pull.method"
            render={({ field, fieldState }) => (
              <FormItem>
                <FormLabel>Method</FormLabel>
                <BrandSelect
                  value={field.value}
                  onValueChange={(v) => field.onChange(v as PullForm['method'])}
                  disabled={readOnly}
                >
                  <FormControl>
                    <BrandSelectTrigger data-testid="api-connection-pull-method">
                      <SelectValue />
                    </BrandSelectTrigger>
                  </FormControl>
                  <BrandSelectContent>
                    <BrandSelectItem value="GET">GET</BrandSelectItem>
                    <BrandSelectItem value="POST">POST</BrandSelectItem>
                  </BrandSelectContent>
                </BrandSelect>
                {fieldState.error && <FormMessage />}
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="pull.path"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Path</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="/v1/orgs/{org_id}/ratings"
                    autoComplete="off"
                    spellCheck={false}
                    className="font-mono"
                    disabled={readOnly}
                    data-testid="api-connection-pull-path"
                  />
                </FormControl>
                <FormDescription>
                  Added to the base URL. {'{org_id}'} and {'{game_type}'} are
                  filled in.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        {method === 'POST' && (
          <p className="text-xs text-muted-foreground">
            The destination must treat this POST as a read. DraftForge does not
            retry it after an unclear failure.
          </p>
        )}
        <TemplateFieldsEditor
          form={form}
          name="pull.query"
          legend="Query fields"
          description="Member ID lists are sent comma-separated."
          readOnly={readOnly}
          scopes={['any', 'batch', 'member', 'page', 'paging', 'cursor']}
        />
        {(method === 'POST' || bodyRows > 0) && (
          <TemplateFieldsEditor
            form={form}
            name="pull.body"
            legend="JSON body fields"
            description="Member ID lists are sent as JSON arrays of strings."
            readOnly={readOnly}
            scopes={['any', 'batch', 'member', 'page', 'paging', 'cursor']}
          />
        )}
        {auth === 'api_key_field' && (
          <CredentialSlotFields
            form={form}
            prefix="pull"
            allowBody={method === 'POST'}
            readOnly={readOnly}
          />
        )}
        <FormField
          control={form.control}
          name="pull.request_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Request mode</FormLabel>
              <BrandSelect
                value={field.value}
                onValueChange={(v) =>
                  field.onChange(v as PullForm['request_mode'])
                }
                disabled={readOnly}
              >
                <FormControl>
                  <BrandSelectTrigger data-testid="api-connection-pull-mode">
                    <SelectValue />
                  </BrandSelectTrigger>
                </FormControl>
                <BrandSelectContent>
                  {Object.entries(REQUEST_MODE_LABELS).map(([v, label]) => (
                    <BrandSelectItem key={v} value={v}>
                      {label}
                    </BrandSelectItem>
                  ))}
                </BrandSelectContent>
              </BrandSelect>
              <FormMessage />
            </FormItem>
          )}
        />
        <p
          className="text-sm"
          aria-live="polite"
          data-testid="api-connection-pull-estimate"
        >
          {estimate === null
            ? 'Request estimate unavailable until the member count loads.'
            : `About ${estimate} request${estimate === 1 ? '' : 's'} per run for ${memberCount} member${memberCount === 1 ? '' : 's'}. A run makes at most ${REQUESTS_PER_RUN}.`}
        </p>
        {ack && (
          <FormField
            control={form.control}
            name="pull.acknowledge_per_member"
            render={({ field, fieldState }) => (
              <div className="flex flex-col gap-1 rounded-md border border-warning/40 p-3">
                <div className="flex items-start gap-3">
                  <Switch
                    id="api-connection-pull-ack"
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    disabled={readOnly}
                    aria-describedby="api-connection-pull-ack-help"
                    data-testid="api-connection-pull-ack"
                  />
                  <div className="flex flex-col">
                    <Label htmlFor="api-connection-pull-ack">
                      I understand per-member mode needs more than{' '}
                      {REQUESTS_PER_RUN} requests
                    </Label>
                    <span
                      id="api-connection-pull-ack-help"
                      className="text-xs text-muted-foreground"
                    >
                      A run stops at {REQUESTS_PER_RUN} requests and imports
                      nothing when the remaining members are not reached.
                    </span>
                  </div>
                </div>
                {fieldState.error?.message && (
                  <p
                    role="alert"
                    className="text-sm font-medium text-destructive"
                    data-testid="api-connection-pull-ack-error"
                  >
                    {fieldState.error.message}
                  </p>
                )}
              </div>
            )}
          />
        )}
      </fieldset>

      <ConnectionMappingEditor form={form} readOnly={readOnly} />

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-base font-semibold">Import rules</legend>
        <GameTypeField
          form={form}
          readOnly={readOnly}
          help="Which game's MMR a pull writes."
        />
        <FormField
          control={form.control}
          name="overwrite_policy"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Overwrite</FormLabel>
              <BrandSelect
                value={field.value}
                onValueChange={(v) => field.onChange(v as OverwritePolicy)}
                disabled={readOnly}
              >
                <FormControl>
                  <BrandSelectTrigger data-testid="api-connection-overwrite">
                    <SelectValue />
                  </BrandSelectTrigger>
                </FormControl>
                <BrandSelectContent>
                  {OVERWRITE_POLICY_VALUES.map((v) => (
                    <BrandSelectItem key={v} value={v}>
                      {OVERWRITE_POLICY_LABELS[v]}
                    </BrandSelectItem>
                  ))}
                </BrandSelectContent>
              </BrandSelect>
              <FormDescription>
                A value changed in DraftForge after the pull started is reported
                as a conflict and kept.
              </FormDescription>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="mark_verified"
          render={({ field }) => (
            <div className="flex items-start gap-3">
              <Switch
                id="api-connection-mark-verified"
                checked={field.value}
                onCheckedChange={field.onChange}
                disabled={readOnly}
                aria-describedby="api-connection-mark-verified-help"
                data-testid="api-connection-mark-verified"
              />
              <div className="flex flex-col">
                <Label htmlFor="api-connection-mark-verified">
                  Mark imported MMRs verified
                </Label>
                <span
                  id="api-connection-mark-verified-help"
                  className="text-xs text-muted-foreground"
                >
                  The admin who authorized this connection is recorded as the
                  verifier. The usual verification rules still apply.
                </span>
              </div>
            </div>
          )}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-base font-semibold">Schedule</legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="api-connection-schedule">Runs</Label>
            <BrandSelect
              value={interval === null ? 'manual' : 'interval'}
              onValueChange={(v) =>
                form.setValue('interval_minutes', v === 'manual' ? null : 60, {
                  shouldDirty: true,
                  shouldValidate: true,
                })
              }
              disabled={readOnly}
            >
              <BrandSelectTrigger
                id="api-connection-schedule"
                data-testid="api-connection-schedule"
              >
                <SelectValue />
              </BrandSelectTrigger>
              <BrandSelectContent>
                <BrandSelectItem value="manual">Manual only</BrandSelectItem>
                <BrandSelectItem value="interval">
                  Every N minutes
                </BrandSelectItem>
              </BrandSelectContent>
            </BrandSelect>
          </div>
          {interval !== null && (
            <FormField
              control={form.control}
              name="interval_minutes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Minutes between runs</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      inputMode="numeric"
                      min={INTERVAL_MIN}
                      max={INTERVAL_MAX}
                      name={field.name}
                      ref={field.ref}
                      onBlur={field.onBlur}
                      value={
                        field.value === null || Number.isNaN(field.value)
                          ? ''
                          : field.value
                      }
                      onChange={(e) => field.onChange(e.target.valueAsNumber)}
                      disabled={readOnly}
                      data-testid="api-connection-interval"
                    />
                  </FormControl>
                  <FormDescription>
                    {INTERVAL_MIN} to {INTERVAL_MAX} minutes. Turning the
                    schedule on waits one interval; it never imports right away.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}
        </div>
      </fieldset>

      <section
        className="flex flex-col gap-3 border-t border-border pt-4"
        aria-labelledby="api-connection-pull-actions"
      >
        <h3
          id="api-connection-pull-actions"
          className="text-base font-semibold"
        >
          Run
        </h3>
        <p className="text-xs text-muted-foreground">
          A test fetches with the saved configuration and reports how rows map.
          It imports nothing and works while the pull is off.
        </p>
        <div className="flex flex-wrap gap-2">
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={testReason !== null || test.pending}
            onClick={() => void test.run('mmr_pull')}
            data-testid="api-connection-pull-test"
          >
            Test configuration
          </SecondaryButton>
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={pullReason !== null || pull.isPending}
            onClick={() => void runPull()}
            data-testid="api-connection-pull-now"
          >
            Pull now
          </SecondaryButton>
        </div>
        <ActionNote
          reason={pullReason ?? testReason}
          error={test.error ?? pullError}
          testId="api-connection-pull-action"
        />
        {lastRun && (
          <div data-testid="api-connection-pull-last-run">
            <span className="text-sm font-medium">Last pull</span>
            <RunCounters run={lastRun} />
          </div>
        )}
      </section>
    </div>
  );
}
