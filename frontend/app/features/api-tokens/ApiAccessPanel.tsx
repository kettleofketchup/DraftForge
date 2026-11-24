import { zodResolver } from '@hookform/resolvers/zod';
import { Copy } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
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
import { Skeleton } from '~/components/ui/skeleton';
import type { OrgFeatureAccess } from '~/features/org-features';
import { useIsSuperuser } from '~/hooks/usePermissions';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { ApiTokenTable } from './ApiTokenTable';
import { ApiUsageTable, usageToday } from './ApiUsageTable';
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
  TOKEN_NAME_MAX_LENGTH,
  USAGE_DAYS,
  isLimitField,
  type ApiLimits,
  type ApiLimitsForm,
  type ApiToken,
  type CreateTokenForm,
  type CreatedApiToken,
} from './schemas';

const log = getLogger('ApiAccessPanel');

export interface ApiAccessPanelProps {
  orgId: number;
  access: OrgFeatureAccess;
  enabled?: boolean;
}

export function ApiAccessPanel({
  orgId,
  access,
  enabled = true,
}: ApiAccessPanelProps) {
  const isSiteAdmin = useIsSuperuser();
  const tokens = useApiTokens(orgId, access, enabled);
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
        <h2 className="text-lg font-semibold">API access</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Personal tokens let an external service push member MMRs to{' '}
          <code className="font-mono text-xs">
            /api/organizations/{orgId}/mmr-sync/
          </code>{' '}
          with an{' '}
          <code className="font-mono text-xs">Authorization: Bearer</code>{' '}
          header. Requests count against your own daily usage.
        </p>
        {!access.mmrSyncEnabled && (
          <p
            className="mt-2 text-sm text-warning"
            data-testid="api-access-locked"
          >
            The MMR sync API is locked for this organization. Unlock it under
            Locked features before creating tokens.
          </p>
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
                size="sm"
                data-testid="api-token-create"
                disabled={!access.mmrSyncEnabled}
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

function TokenSecret({ token }: { token: string }) {
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(token);
      toast.success('Token copied');
    } catch (err) {
      log.warn('Clipboard write failed', { err });
      toast.error('Could not copy. Select the token and copy it manually.');
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-stretch gap-2">
        <code
          className="min-w-0 flex-1 break-all rounded-md border border-border bg-base-900/40 p-3 font-mono text-sm select-all"
          data-testid="api-token-secret"
        >
          {token}
        </code>
        <SecondaryButton
          type="button"
          size="sm"
          className="h-auto min-h-11 self-stretch sm:min-h-8"
          onClick={copy}
          aria-label="Copy token"
          data-testid="api-token-copy"
        >
          <Copy className="size-4" />
        </SecondaryButton>
      </div>
      <p className="text-sm text-warning" data-testid="api-token-once-note">
        This is the only time the full token is shown. Store it somewhere safe;
        if you lose it, revoke it and create a new one.
      </p>
    </div>
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
  const form = useForm<CreateTokenForm>({
    resolver: zodResolver(CreateTokenFormSchema),
    defaultValues: { name: '' },
  });

  useEffect(() => {
    if (open) form.reset({ name: '' });
  }, [open, form]);

  const submit = form.handleSubmit(async ({ name }) => {
    try {
      const token = await create.mutateAsync(name);
      onCreated(token);
    } catch (err) {
      log.error('Failed to create API token', { orgId, err });
      const message = extractApiError(err) ?? 'Could not create the token';
      form.setError('name', { message });
    }
  });

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
