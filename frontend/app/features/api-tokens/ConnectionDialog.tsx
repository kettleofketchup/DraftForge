import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useForm, type Resolver } from 'react-hook-form';
import { toast } from 'sonner';

import { FormTabsList } from '~/components/patterns/FormTabsList';
import { DIALOG_MOBILE_FULL_CSS } from '~/components/reusable/modal';
import {
  CancelButton,
  PrimaryButton,
  SecondaryButton,
} from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ConfirmDialog, InfoDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Skeleton } from '~/components/ui/skeleton';
import { Tabs, TabsContent } from '~/components/ui/tabs';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { ConnectionGeneralTab } from './ConnectionGeneralTab';
import { ConnectionInboundTab } from './ConnectionInboundTab';
import { TokenSecret } from './TokenSecret';
import {
  canManageConnections,
  useArchiveConnection,
  useConnection,
  useConnectionQueryHygiene,
  useCreateConnection,
  useIssueConnectionKey,
  useRevokeConnectionKey,
  useUpdateConnection,
} from './connectionQueries';
import { connectionKeys } from './connectionQueryKeys';
import {
  ConnectionFormSchema,
  buildConnectionCreate,
  buildConnectionPatch,
  connectionErrorCode,
  connectionErrorField,
  connectionErrorMessage,
  connectionFormDefaults,
  connectionFormValues,
  operationLabelList,
  type ApiConnection,
  type ConnectionForm,
  type IssuedKey,
} from './connectionSchemas';
import { useApiTokens } from './queries';
import type { ApiUserRef } from './schemas';

const log = getLogger('ConnectionDialog');

export interface ConnectionDialogProps {
  orgId: number;
  access: OrgFeatureAccess;
  /** null opens the create form. */
  connectionId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (connectionId: number) => void;
  /** Local unsaved state, for the host's close and navigation guard. */
  onDirtyChange?: (dirty: boolean) => void;
}

/**
 * A portaled, explicit-save editor. It renders no <form>, so neither Enter
 * nor its buttons can submit a host form it is rendered inside.
 */
export function ConnectionDialog(props: ConnectionDialogProps) {
  const { orgId, access, open, onOpenChange } = props;
  const allowed = canManageConnections(access);
  useConnectionQueryHygiene(orgId, access);
  useEffect(() => {
    if (open && !allowed) onOpenChange(false);
  }, [open, allowed, onOpenChange]);
  if (!open || !allowed) return null;
  // Remounting on org, viewer or connection drops drafts and shown keys.
  return (
    <ConnectionEditor
      key={`${orgId}:${access.viewerPk}:${props.connectionId ?? 'new'}`}
      {...props}
    />
  );
}

type KeyAction = 'rotate' | 'revoke' | 'archive' | 'discard' | null;

function ConnectionEditor({
  orgId,
  access,
  connectionId,
  onOpenChange,
  onCreated,
  onDirtyChange,
}: ConnectionDialogProps) {
  const queryClient = useQueryClient();
  const detail = useConnection(orgId, access, connectionId);
  const latest = detail.data ?? null;
  const tokens = useApiTokens(orgId, access);
  const create = useCreateConnection(orgId, access);
  const update = useUpdateConnection(orgId, access);
  const archive = useArchiveConnection(orgId, access);
  const revoke = useRevokeConnectionKey(orgId, access);
  const [secret, setSecret] = useState<IssuedKey | null>(null);
  const issue = useIssueConnectionKey(orgId, access, setSecret);

  const [base, setBase] = useState<ApiConnection | null>(null);
  const [rejected, setRejected] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<KeyAction>(null);
  const [tab, setTab] = useState('general');

  const baseRef = useRef<ApiConnection | null>(null);
  useEffect(() => {
    baseRef.current = base;
  }, [base]);
  const resolver = useCallback<Resolver<ConnectionForm>>(
    (values, context, options) =>
      zodResolver(ConnectionFormSchema(baseRef.current))(
        values,
        context,
        options,
      ) as ReturnType<Resolver<ConnectionForm>>,
    [],
  );
  const form = useForm<ConnectionForm>({
    resolver,
    defaultValues: connectionFormDefaults(),
  });
  const { isDirty } = form.formState;

  const adopt = useCallback(
    (row: ApiConnection): void => {
      setBase(row);
      baseRef.current = row;
      setRejected(false);
      setServerError(null);
      form.reset(connectionFormValues(row));
    },
    [form],
  );

  // A clean draft follows the server; a dirty one is kept and flagged stale.
  useEffect(() => {
    if (!latest) return;
    if (base === null || !form.formState.isDirty) {
      if (latest !== base) adopt(latest);
    }
  }, [latest, base, form, adopt]);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  const stale =
    rejected ||
    (base !== null &&
      latest !== null &&
      latest.config_version !== base.config_version);
  const readOnly = Boolean(latest?.archived_at);
  const creating = connectionId == null;

  const keyOwners = useMemo(() => {
    const owners = new Map<number, ApiUserRef | null>();
    for (const token of tokens.data ?? []) owners.set(token.id, token.user);
    return owners;
  }, [tokens.data]);

  const showError = (err: unknown, fallback: string): void => {
    const code = connectionErrorCode(err);
    toast.error(
      code ? connectionErrorMessage(code) : (extractApiError(err) ?? fallback),
    );
  };

  const save = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      if (creating) {
        const row = await create.mutateAsync(buildConnectionCreate(values));
        adopt(row);
        toast.success('Connection created');
        onCreated?.(row.id);
        return;
      }
      if (!base) return;
      const patch = buildConnectionPatch(base, values);
      if (Object.keys(patch).length === 1) {
        form.reset(connectionFormValues(base));
        return;
      }
      const row = await update.mutateAsync({
        connectionId: base.id,
        patch,
      });
      adopt(row);
      toast.success('Connection saved');
    } catch (err) {
      const code = connectionErrorCode(err);
      log.error('Failed to save API connection', { orgId, connectionId, code });
      if (code === 'configuration_changed') {
        setRejected(true);
        if (connectionId != null) {
          void queryClient.invalidateQueries({
            queryKey: connectionKeys.detail(
              orgId,
              access.viewerPk,
              connectionId,
            ),
          });
        }
        return;
      }
      const message = code
        ? connectionErrorMessage(code)
        : (extractApiError(err) ?? 'Could not save the connection');
      const field = code ? connectionErrorField(code) : null;
      if (field) form.setError(field, { message });
      else setServerError(message);
    }
  });

  const reload = (): void => {
    if (latest) adopt(latest);
  };

  const runIssue = async (rotate: boolean): Promise<void> => {
    if (!latest) return;
    try {
      await issue.mutateAsync({
        connectionId: latest.id,
        rotate,
        ...(latest.legacy_multi_credential
          ? { confirmed_operations: latest.operations }
          : {}),
      });
    } catch (err) {
      log.error('Failed to issue connection key', {
        orgId,
        connectionId: latest.id,
        code: connectionErrorCode(err),
      });
      showError(err, 'Could not issue the key');
    }
  };

  const runRevoke = async (): Promise<void> => {
    if (!latest) return;
    try {
      await revoke.mutateAsync(latest.id);
      toast.success('Key revoked');
    } catch (err) {
      log.error('Failed to revoke connection key', {
        orgId,
        connectionId: latest.id,
        code: connectionErrorCode(err),
      });
      showError(err, 'Could not revoke the key');
    }
  };

  const runArchive = async (): Promise<void> => {
    if (!latest) return;
    try {
      await archive.mutateAsync(latest.id);
      toast.success('Connection archived');
    } catch (err) {
      log.error('Failed to archive connection', {
        orgId,
        connectionId: latest.id,
        code: connectionErrorCode(err),
      });
      showError(err, 'Could not archive the connection');
    }
  };

  const requestClose = (): void => {
    if (form.formState.isDirty) setConfirm('discard');
    else onOpenChange(false);
  };

  const saving = create.isPending || update.isPending;
  const keyPending = issue.isPending || revoke.isPending;
  const loading = !creating && !latest;
  const title = creating
    ? 'Add API connection'
    : (latest?.name ?? 'Connection');
  const errors = form.formState.errors;

  return (
    <>
      <Dialog
        open
        onOpenChange={(next) => {
          if (!next) requestClose();
        }}
      >
        <DialogContent
          className={cn(
            DIALOG_MOBILE_FULL_CSS,
            'flex flex-col sm:h-auto sm:max-w-2xl',
          )}
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          onKeyDown={(e) => {
            if (
              e.key === 'Enter' &&
              e.target instanceof HTMLInputElement &&
              e.currentTarget.contains(e.target)
            ) {
              e.preventDefault();
              e.stopPropagation();
            }
          }}
          data-testid="api-connection-dialog"
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              Changes apply only when you select Save.
            </DialogDescription>
          </DialogHeader>

          {stale && (
            <div
              role="status"
              className="flex flex-col gap-2 rounded-md border border-warning/40 p-3 text-sm sm:flex-row sm:items-center"
              data-testid="api-connection-conflict"
            >
              <span className="flex-1">
                Someone else saved this connection. Your draft is kept; reload
                to see their version before saving.
              </span>
              <SecondaryButton
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={reload}
                disabled={!latest}
                data-testid="api-connection-reload"
              >
                Reload
              </SecondaryButton>
            </div>
          )}

          {detail.isError && (
            <p className="text-sm text-destructive" role="alert">
              {extractApiError(detail.error) ?? 'Failed to load the connection'}
            </p>
          )}

          {loading && !detail.isError ? (
            <Skeleton className="h-48 w-full" />
          ) : (
            <Form {...form}>
              <Tabs
                value={tab}
                onValueChange={setTab}
                className="flex min-h-0 flex-1 flex-col"
              >
                <FormTabsList
                  testIdPrefix="api-connection"
                  tabs={[
                    {
                      value: 'general',
                      label: 'General',
                      invalid: Boolean(
                        errors.name ||
                        errors.outbound_base_url ||
                        errors.outbound_credential,
                      ),
                    },
                    {
                      value: 'inbound',
                      label: 'Inbound key',
                      invalid: Boolean(errors.operations),
                    },
                  ]}
                />
                <ScrollArea className="max-h-[calc(100svh-14rem)] sm:max-h-[60vh] pr-4">
                  <div className="px-1 py-3">
                    <TabsContent value="general">
                      <ConnectionGeneralTab
                        form={form}
                        saved={latest}
                        readOnly={readOnly}
                        onArchive={
                          creating ? undefined : () => setConfirm('archive')
                        }
                        archiving={archive.isPending}
                      />
                    </TabsContent>
                    <TabsContent value="inbound">
                      <ConnectionInboundTab
                        form={form}
                        saved={latest}
                        dirty={isDirty || creating}
                        readOnly={readOnly}
                        access={access}
                        keyOwners={keyOwners}
                        pending={keyPending}
                        onIssue={() => void runIssue(false)}
                        onRotate={() => setConfirm('rotate')}
                        onRevoke={() => setConfirm('revoke')}
                      />
                    </TabsContent>
                  </div>
                </ScrollArea>
              </Tabs>
            </Form>
          )}

          {serverError && (
            <p
              role="alert"
              className="text-sm font-medium text-destructive"
              data-testid="api-connection-error"
            >
              {serverError}
            </p>
          )}
          <p className="sr-only" aria-live="polite">
            {saving ? 'Saving' : ''}
          </p>

          <DialogFooter className="flex-row justify-end gap-2">
            <CancelButton
              type="button"
              onClick={requestClose}
              disabled={saving}
              data-testid="api-connection-cancel"
            >
              {isDirty ? 'Cancel' : 'Close'}
            </CancelButton>
            {!readOnly && (
              <PrimaryButton
                type="button"
                onClick={() => void save()}
                disabled={saving || loading || (!isDirty && !creating)}
                data-testid="api-connection-save"
              >
                {saving ? 'Saving...' : creating ? 'Create' : 'Save'}
              </PrimaryButton>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <InfoDialog
        open={secret !== null}
        onOpenChange={(next) => {
          if (!next) setSecret(null);
        }}
        title="Key issued"
        description="Copy this key now. You won't be able to see it again."
        closeLabel="Done"
        data-testid="api-connection-key-dialog"
      >
        {secret && (
          <TokenSecret token={secret.token} testIdPrefix="api-connection-key" />
        )}
      </InfoDialog>
      <ConfirmDialog
        open={confirm === 'rotate'}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
        title="Rotate key?"
        description={
          latest?.legacy_multi_credential
            ? `Every current key stops working immediately. The new key holds: ${operationLabelList(latest.operations)}.`
            : 'The current key stops working immediately. Services using it must switch to the new key.'
        }
        confirmLabel="Rotate"
        variant="warning"
        isLoading={issue.isPending}
        onConfirm={() => runIssue(true)}
        confirmTestId="api-connection-rotate-confirm"
        cancelTestId="api-connection-rotate-cancel"
      />
      <ConfirmDialog
        open={confirm === 'revoke'}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
        title="Revoke key?"
        description="The key stops working immediately. Outbound sync on this connection is not affected; turn those directions off separately."
        confirmLabel="Revoke"
        variant="destructive"
        isLoading={revoke.isPending}
        onConfirm={runRevoke}
        confirmTestId="api-connection-revoke-confirm"
        cancelTestId="api-connection-revoke-cancel"
      />
      <ConfirmDialog
        open={confirm === 'archive'}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
        title="Archive connection?"
        description="Every direction turns off, the inbound key is revoked and the stored credential is removed. This can't be undone."
        confirmLabel="Archive"
        variant="destructive"
        isLoading={archive.isPending}
        onConfirm={runArchive}
        confirmTestId="api-connection-archive-confirm"
        cancelTestId="api-connection-archive-cancel"
      />
      <ConfirmDialog
        open={confirm === 'discard'}
        onOpenChange={(next) => {
          if (!next) setConfirm(null);
        }}
        title="Discard unsaved changes?"
        description="Your changes to this connection will be lost."
        confirmLabel="Discard"
        variant="destructive"
        onConfirm={() => {
          form.reset(
            base ? connectionFormValues(base) : connectionFormDefaults(),
          );
          onOpenChange(false);
        }}
        confirmTestId="api-connection-discard-confirm"
        cancelTestId="api-connection-discard-cancel"
      />
    </>
  );
}
