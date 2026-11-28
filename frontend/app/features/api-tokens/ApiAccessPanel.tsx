import { zodResolver } from '@hookform/resolvers/zod';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { ConfirmDialog, FormDialog, InfoDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Skeleton } from '~/components/ui/skeleton';
import { Switch } from '~/components/ui/switch';
import type { OrgFeatureAccess } from '~/features/org-features';
import { useIsSuperuser } from '~/hooks/usePermissions';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { ApiConnectionTable } from './ApiConnectionTable';
import { ApiTokenTable } from './ApiTokenTable';
import { ApiUsageTable, usageToday } from './ApiUsageTable';
import { ConnectionDialog } from './ConnectionDialog';
import { TokenSecret } from './TokenSecret';
import { useConnectionQueryHygiene, useConnections } from './connectionQueries';
import type { ApiConnection } from './connectionSchemas';
import {
  useApiLimits,
  useApiTokens,
  useApiUsage,
  useCreateApiToken,
  useRevokeApiToken,
  useSetApiLimits,
} from './queries';
import {
  ApiLimitsFormSchema,
  CreateTokenFormSchema,
  DEFAULT_TOKEN_OPERATIONS,
  TOKEN_FEATURE_LABELS,
  TOKEN_NAME_MAX_LENGTH,
  TOKEN_OPERATIONS,
  USAGE_DAYS,
  isLimitField,
  type ApiLimits,
  type ApiLimitsForm,
  type ApiToken,
  type ApiUserRef,
  type CreateTokenForm,
  type CreatedApiToken,
  type TokenFeature,
  type TokenOperation,
} from './schemas';

const log = getLogger('ApiAccessPanel');

type TokenFeatureFlags = Pick<
  OrgFeatureAccess,
  'mmrSyncEnabled' | 'promotionEnabled'
>;

function featureEnabled(access: TokenFeatureFlags, feature: TokenFeature) {
  switch (feature) {
    case 'mmr_sync':
      return access.mmrSyncEnabled;
    case 'promotion':
      return access.promotionEnabled;
  }
}

function anyTokenFeature(access: TokenFeatureFlags): boolean {
  return TOKEN_OPERATIONS.some((op) => featureEnabled(access, op.feature));
}

/** The MMR pair, minus any operation whose feature is locked. */
function defaultOperations(access: TokenFeatureFlags): TokenOperation[] {
  return DEFAULT_TOKEN_OPERATIONS.filter((value) =>
    TOKEN_OPERATIONS.some(
      (op) => op.value === value && featureEnabled(access, op.feature),
    ),
  );
}

export interface ConnectionDraftState {
  dirty: boolean;
  /** Drops the open connection draft and closes its dialog. */
  discard: () => void;
}

export interface ApiAccessPanelProps {
  orgId: number;
  access: OrgFeatureAccess;
  enabled?: boolean;
  /** Reports the open connection dialog's unsaved state to the host. */
  onConnectionDraftChange?: (state: ConnectionDraftState) => void;
}

type ConnectionTarget = { id: number | null } | null;

export function ApiAccessPanel({
  orgId,
  access,
  enabled = true,
  onConnectionDraftChange,
}: ApiAccessPanelProps) {
  const isSiteAdmin = useIsSuperuser();
  useConnectionQueryHygiene(orgId, access);
  const connections = useConnections(orgId, access, enabled);
  const [target, setTarget] = useState<ConnectionTarget>(null);
  const onManage = useCallback(
    (row: ApiConnection) => setTarget({ id: row.id }),
    [],
  );
  const closeConnection = useCallback(() => setTarget(null), []);
  const onConnectionDirty = useCallback(
    (dirty: boolean) =>
      onConnectionDraftChange?.({ dirty, discard: closeConnection }),
    [onConnectionDraftChange, closeConnection],
  );
  const tokens = useApiTokens(orgId, access, enabled);
  const keyOwners = useMemo(() => {
    const owners = new Map<number, ApiUserRef | null>();
    for (const token of tokens.data ?? []) owners.set(token.id, token.user);
    return owners;
  }, [tokens.data]);
  const usage = useApiUsage(orgId, access, USAGE_DAYS, enabled);
  const limits = useApiLimits(orgId, access, enabled);
  const revoke = useRevokeApiToken(orgId, access);

  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<CreatedApiToken | null>(null);
  const [revoking, setRevoking] = useState<ApiToken | null>(null);

  const onRevoke = useCallback((token: ApiToken) => setRevoking(token), []);

  const confirmRevoke = async (): Promise<void> => {
    if (!revoking) return;
    try {
      await revoke.mutateAsync(revoking.id);
      toast.success(`Revoked ${revoking.name}`);
    } catch (err) {
      log.error('Failed to revoke API token', {
        orgId,
        tokenId: revoking.id,
        err,
      });
      toast.error(extractApiError(err) ?? 'Could not revoke the token');
    }
  };

  return (
    <section
      data-testid="org-settings-api-access"
      className="flex flex-col gap-8 rounded-lg border border-border p-6"
    >
      <div>
        <h2 className="text-lg font-semibold">API connections</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect external services to this organization&apos;s members and
          contact history. Each connection has its own scoped inbound key and
          its own outbound settings, and every direction starts off.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Personal tokens let an external service push member MMRs to{' '}
          <code className="font-mono text-xs">
            /api/organizations/{orgId}/mmr-sync/
          </code>{' '}
          with an{' '}
          <code className="font-mono text-xs">Authorization: Bearer</code>{' '}
          header. Requests count against your own daily usage.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Each token can only do what it was granted when created. The adaptor
          needs the promotion operations; new tokens get the MMR pair unless you
          choose otherwise.
        </p>
        {!anyTokenFeature(access) && (
          <p
            className="mt-2 text-sm text-warning"
            data-testid="api-access-locked"
          >
            The MMR sync API and Promotion are both locked for this
            organization. Unlock one under Locked features before creating
            tokens.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-base font-semibold">Connections</h3>
        {connections.isLoading && <Skeleton className="h-24 w-full" />}
        {connections.isError && (
          <p
            className="text-sm text-destructive"
            data-testid="api-connections-error"
          >
            {extractApiError(connections.error) ??
              'Failed to load API connections'}
          </p>
        )}
        {connections.data && (
          <ApiConnectionTable
            connections={connections.data}
            onManage={onManage}
            keyOwners={keyOwners}
            toolbarActions={
              <PrimaryButton
                type="button"
                size="sm"
                data-testid="api-connection-create"
                disabled={!anyTokenFeature(access)}
                onClick={() => setTarget({ id: null })}
              >
                Add connection
              </PrimaryButton>
            }
          />
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-base font-semibold">Tokens</h3>
        {tokens.isLoading && <Skeleton className="h-24 w-full" />}
        {tokens.isError && (
          <p
            className="text-sm text-destructive"
            data-testid="api-tokens-error"
          >
            {extractApiError(tokens.error) ?? 'Failed to load API tokens'}
          </p>
        )}
        {tokens.data && (
          <ApiTokenTable
            tokens={tokens.data}
            onRevoke={onRevoke}
            revoking={revoke.isPending}
            toolbarActions={
              <PrimaryButton
                type="button"
                size="sm"
                data-testid="api-token-create"
                disabled={!anyTokenFeature(access)}
                onClick={() => setCreateOpen(true)}
              >
                Create token
              </PrimaryButton>
            }
          />
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-base font-semibold">
          Usage, last {USAGE_DAYS} days
        </h3>
        {usage.isLoading && <Skeleton className="h-24 w-full" />}
        {usage.isError && (
          <p className="text-sm text-destructive" data-testid="api-usage-error">
            {extractApiError(usage.error) ?? 'Failed to load API usage'}
          </p>
        )}
        {usage.data && (
          <ApiUsageTable
            users={usage.data.users}
            today={usageToday(usage.data.since, usage.data.days)}
          />
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-base font-semibold">Rate limits</h3>
        <p className="text-sm text-muted-foreground">
          Each token is limited separately. Requests over a limit are refused
          and counted as throttled.
        </p>
        {limits.isLoading && <Skeleton className="h-12 w-full" />}
        {limits.isError && (
          <p
            className="text-sm text-destructive"
            data-testid="api-limits-error"
          >
            {extractApiError(limits.error) ?? 'Failed to load rate limits'}
          </p>
        )}
        {limits.data &&
          (isSiteAdmin ? (
            <LimitsForm orgId={orgId} access={access} limits={limits.data} />
          ) : (
            <dl
              className="grid grid-cols-2 gap-2 text-sm sm:max-w-sm"
              data-testid="api-limits"
            >
              <dt className="text-muted-foreground">Per minute</dt>
              <dd className="tabular-nums" data-testid="api-limits-per-minute">
                {limits.data.per_minute.toLocaleString()}
              </dd>
              <dt className="text-muted-foreground">Per day</dt>
              <dd className="tabular-nums" data-testid="api-limits-per-day">
                {limits.data.per_day.toLocaleString()}
              </dd>
            </dl>
          ))}
      </div>

      <ConnectionDialog
        orgId={orgId}
        access={access}
        connectionId={target?.id ?? null}
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) closeConnection();
        }}
        onCreated={(id) => setTarget({ id })}
        onDirtyChange={onConnectionDirty}
      />
      <CreateTokenDialog
        orgId={orgId}
        access={access}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(token) => {
          setCreateOpen(false);
          setCreated(token);
        }}
      />
      <InfoDialog
        open={created !== null}
        onOpenChange={(open) => {
          if (!open) setCreated(null);
        }}
        title="Token created"
        description="Copy this token now. You won't be able to see it again."
        closeLabel="Done"
        data-testid="api-token-created-dialog"
      >
        {created && <TokenSecret token={created.token} />}
      </InfoDialog>
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => {
          if (!open) setRevoking(null);
        }}
        title="Revoke token?"
        description={
          revoking
            ? `${revoking.name} stops working immediately. This can't be undone.`
            : ''
        }
        confirmLabel="Revoke"
        variant="destructive"
        isLoading={revoke.isPending}
        onConfirm={confirmRevoke}
        confirmTestId="api-token-revoke-confirm"
        cancelTestId="api-token-revoke-cancel"
      />
    </section>
  );
}

interface CreateTokenDialogProps {
  orgId: number;
  access: OrgFeatureAccess;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (token: CreatedApiToken) => void;
}

function CreateTokenDialog({
  orgId,
  access,
  open,
  onOpenChange,
  onCreated,
}: CreateTokenDialogProps) {
  const create = useCreateApiToken(orgId, access);
  const { mmrSyncEnabled, promotionEnabled } = access;
  // Keyed on the flags: `access` is a fresh object on every render.
  const defaults = useMemo(
    () => defaultOperations({ mmrSyncEnabled, promotionEnabled }),
    [mmrSyncEnabled, promotionEnabled],
  );
  const form = useForm<CreateTokenForm>({
    resolver: zodResolver(CreateTokenFormSchema),
    defaultValues: { name: '', operations: defaults },
  });

  useEffect(() => {
    if (open) form.reset({ name: '', operations: defaults });
  }, [open, form, defaults]);

  const submit = form.handleSubmit(async ({ name, operations }) => {
    try {
      const token = await create.mutateAsync({ name, operations });
      onCreated(token);
    } catch (err) {
      log.error('Failed to create API token', { orgId, err });
      const response = (
        err as { response?: { status?: number; data?: unknown } }
      ).response;
      const opsErrors = (response?.data as { operations?: unknown } | undefined)
        ?.operations;
      if (Array.isArray(opsErrors) && opsErrors.length > 0) {
        form.setError('operations', { message: String(opsErrors[0]) });
        return;
      }
      const message = extractApiError(err) ?? 'Could not create the token';
      // 403 here means an operation's feature is locked or not permitted.
      form.setError(response?.status === 403 ? 'operations' : 'name', {
        message,
      });
    }
  });
  const operationsError = form.formState.errors.operations?.message;

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Create API token"
      description="Name the token after the service that will use it."
      submitLabel="Create"
      isSubmitting={create.isPending}
      onSubmit={submit}
      size="sm"
      data-testid="api-token-create-dialog"
      submitTestId="api-token-create-submit"
      cancelTestId="api-token-create-cancel"
    >
      <Form {...form}>
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  maxLength={TOKEN_NAME_MAX_LENGTH}
                  placeholder="MMR bot"
                  autoComplete="off"
                  data-testid="api-token-name"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="operations"
          render={({ field }) => (
            <fieldset
              className="mt-4 flex flex-col gap-3"
              aria-describedby={
                operationsError ? 'api-token-operations-error' : undefined
              }
              data-testid="api-token-operations"
            >
              <legend className="mb-2 text-sm font-medium">Operations</legend>
              {TOKEN_OPERATIONS.map((op) => {
                const enabled = featureEnabled(access, op.feature);
                const id = `api-token-op-${op.value.replace(':', '-')}`;
                const checked = field.value.includes(op.value);
                return (
                  <div key={op.value} className="flex items-start gap-3">
                    <Switch
                      id={id}
                      checked={checked}
                      disabled={!enabled}
                      aria-describedby={enabled ? undefined : `${id}-locked`}
                      onCheckedChange={(on) =>
                        field.onChange(
                          on
                            ? TOKEN_OPERATIONS.map((o) => o.value).filter(
                                (v) =>
                                  v === op.value || field.value.includes(v),
                              )
                            : field.value.filter((v) => v !== op.value),
                        )
                      }
                      data-testid={`api-token-op-${op.value}`}
                    />
                    <div className="flex min-w-0 flex-col">
                      <Label htmlFor={id} className="text-sm">
                        {op.label}
                      </Label>
                      <code className="font-mono text-xs text-muted-foreground">
                        {op.value}
                      </code>
                      {op.description && (
                        <span
                          className="text-xs text-muted-foreground"
                          data-testid={`api-token-op-${op.value}-description`}
                        >
                          {op.description}
                        </span>
                      )}
                      {!enabled && (
                        <span
                          id={`${id}-locked`}
                          className="text-xs text-warning"
                          data-testid={`api-token-op-${op.value}-locked`}
                        >
                          {TOKEN_FEATURE_LABELS[op.feature]} is locked for this
                          organization.
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
              {operationsError && (
                <p
                  id="api-token-operations-error"
                  className="text-sm font-medium text-destructive"
                  data-testid="api-token-operations-error"
                >
                  {operationsError}
                </p>
              )}
            </fieldset>
          )}
        />
      </Form>
    </FormDialog>
  );
}

interface LimitsFormProps {
  orgId: number;
  access: OrgFeatureAccess;
  limits: ApiLimits;
}

function LimitsForm({ orgId, access, limits }: LimitsFormProps) {
  const save = useSetApiLimits(orgId, access);
  const form = useForm<ApiLimitsForm>({
    resolver: zodResolver(ApiLimitsFormSchema),
    defaultValues: limits,
  });

  useEffect(() => {
    if (!form.formState.isDirty) form.reset(limits);
  }, [limits, form]);

  const submit = form.handleSubmit(async (values) => {
    try {
      const saved = await save.mutateAsync(values);
      form.reset(saved);
      toast.success('Rate limits saved');
    } catch (err) {
      log.error('Failed to save API limits', { orgId, err });
      const data = (err as { response?: { data?: unknown } }).response?.data;
      let fieldError = false;
      if (data && typeof data === 'object') {
        for (const [field, messages] of Object.entries(data)) {
          if (isLimitField(field) && Array.isArray(messages)) {
            form.setError(field, { message: String(messages[0]) });
            fieldError = true;
          }
        }
      }
      if (!fieldError) {
        toast.error(extractApiError(err) ?? 'Could not save rate limits');
      }
    }
  });

  return (
    <Form {...form}>
      <div
        role="group"
        aria-label="Rate limits"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && e.target instanceof HTMLInputElement) {
            e.preventDefault();
            void submit();
          }
        }}
        className="flex flex-col gap-4 sm:max-w-sm"
        data-testid="api-limits-form"
      >
        <p className="text-xs text-muted-foreground">
          Site admins only. Applies to every token in this organization.
        </p>
        {(['per_minute', 'per_day'] as const).map((name) => (
          <FormField
            key={name}
            control={form.control}
            name={name}
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  {name === 'per_minute'
                    ? 'Requests per minute'
                    : 'Requests per day'}
                </FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    inputMode="numeric"
                    min={1}
                    step={1}
                    name={field.name}
                    ref={field.ref}
                    onBlur={field.onBlur}
                    value={Number.isNaN(field.value) ? '' : field.value}
                    onChange={(e) =>
                      field.onChange(
                        e.target.value === ''
                          ? Number.NaN
                          : Number(e.target.value),
                      )
                    }
                    disabled={save.isPending}
                    data-testid={`api-limits-${name}`}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ))}
        <div>
          <SecondaryButton
            type="button"
            onClick={() => void submit()}
            disabled={save.isPending || !form.formState.isDirty}
            data-testid="api-limits-save"
          >
            {save.isPending ? 'Saving...' : 'Save limits'}
          </SecondaryButton>
        </div>
      </div>
    </Form>
  );
}
