import type { UseFormReturn } from 'react-hook-form';

import { SecondaryButton } from '~/components/ui/buttons';
import { FormField } from '~/components/ui/form';
import { Label } from '~/components/ui/label';
import { Switch } from '~/components/ui/switch';
import { DisplayName } from '~/components/user/avatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { activeCredentials } from './apiConnectionColumns';
import { maskedToken, relativeTime } from './apiTokenColumns';
import {
  CONNECTION_OPERATIONS,
  CONNECTION_OPERATION_VALUES,
  type ApiConnection,
  type ConnectionForm,
} from './connectionSchemas';
import {
  TOKEN_FEATURE_LABELS,
  type ApiUserRef,
  type TokenFeature,
} from './schemas';

export function featureUnlocked(
  access: Pick<OrgFeatureAccess, 'mmrSyncEnabled' | 'promotionEnabled'>,
  feature: TokenFeature,
): boolean {
  return feature === 'mmr_sync'
    ? access.mmrSyncEnabled
    : access.promotionEnabled;
}

/** Why a key cannot be issued or rotated now, else null. */
export function keyBlockedReason(
  saved: ApiConnection | null,
  dirty: boolean,
): string | null {
  if (!saved) return 'Save the connection before issuing a key.';
  if (saved.archived_at) return 'Archived connections cannot hold a key.';
  if (dirty) return 'Save your changes before issuing a key.';
  if (!saved.inbound_enabled) {
    return 'Turn on inbound access and save before issuing a key.';
  }
  if (saved.operations.length === 0) {
    return 'Grant at least one operation and save before issuing a key.';
  }
  return null;
}

export interface ConnectionInboundTabProps {
  form: UseFormReturn<ConnectionForm>;
  saved: ApiConnection | null;
  dirty: boolean;
  readOnly: boolean;
  access: OrgFeatureAccess;
  keyOwners: ReadonlyMap<number, ApiUserRef | null>;
  pending: boolean;
  onIssue: () => void;
  onRotate: () => void;
  onRevoke: () => void;
}

export function ConnectionInboundTab({
  form,
  saved,
  dirty,
  readOnly,
  access,
  keyOwners,
  pending,
  onIssue,
  onRotate,
  onRevoke,
}: ConnectionInboundTabProps) {
  const values = form.watch('operations');
  const operationsError = form.formState.errors.operations?.message;
  const savedOps = saved?.operations ?? [];
  const keys = saved ? activeCredentials(saved) : [];
  const blocked = keyBlockedReason(saved, dirty);

  return (
    <div className="flex flex-col gap-6">
      <FormField
        control={form.control}
        name="inbound_enabled"
        render={({ field }) => (
          <div className="flex items-start gap-3">
            <Switch
              id="api-connection-inbound-enabled"
              checked={field.value}
              onCheckedChange={field.onChange}
              disabled={readOnly}
              aria-describedby="api-connection-inbound-help"
              data-testid="api-connection-inbound-enabled"
            />
            <div className="flex flex-col">
              <Label htmlFor="api-connection-inbound-enabled">
                Inbound access
              </Label>
              <span
                id="api-connection-inbound-help"
                className="text-xs text-muted-foreground"
              >
                Lets the external service call DraftForge with this
                connection&apos;s key. It only works while the connection is
                enabled too.
              </span>
            </div>
          </div>
        )}
      />

      <FormField
        control={form.control}
        name="operations"
        render={({ field }) => (
          <fieldset
            className="flex flex-col gap-4"
            aria-describedby={
              operationsError ? 'api-connection-operations-error' : undefined
            }
            data-testid="api-connection-operations"
          >
            <legend className="mb-2 text-base font-semibold">Grants</legend>
            <p className="text-sm text-muted-foreground">
              The key can call only the routes granted here. Changing grants
              revokes the current key; issue a new one after saving.
            </p>
            {CONNECTION_OPERATIONS.filter(
              (op) =>
                !op.legacy ||
                savedOps.includes(op.value) ||
                field.value.includes(op.value),
            ).map((op) => {
              const unlocked = featureUnlocked(access, op.feature);
              const checked = field.value.includes(op.value);
              const id = `api-connection-op-${op.value.replace(':', '-')}`;
              return (
                <div key={op.value} className="flex items-start gap-3">
                  <Switch
                    id={id}
                    checked={checked}
                    disabled={readOnly || (!unlocked && !checked)}
                    aria-describedby={`${id}-help`}
                    onCheckedChange={(on) =>
                      field.onChange(
                        CONNECTION_OPERATION_VALUES.filter((v) =>
                          v === op.value ? on : field.value.includes(v),
                        ),
                      )
                    }
                    data-testid={`api-connection-op-${op.value}`}
                  />
                  <div id={`${id}-help`} className="flex min-w-0 flex-col">
                    <Label htmlFor={id} className="text-sm">
                      {op.label}
                    </Label>
                    <code className="font-mono text-xs break-words text-muted-foreground">
                      {op.route}
                    </code>
                    <span className="text-xs text-muted-foreground">
                      {op.description}
                    </span>
                    {!unlocked && (
                      <span
                        className="text-xs text-warning"
                        data-testid={`api-connection-op-${op.value}-locked`}
                      >
                        {TOKEN_FEATURE_LABELS[op.feature]} is locked for this
                        organization. Existing grants can still be removed.
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
            {operationsError && (
              <p
                id="api-connection-operations-error"
                role="alert"
                className="text-sm font-medium text-destructive"
                data-testid="api-connection-operations-error"
              >
                {operationsError}
              </p>
            )}
          </fieldset>
        )}
      />

      <section
        className="flex flex-col gap-3 border-t border-border pt-4"
        aria-labelledby="api-connection-key-heading"
      >
        <h3 id="api-connection-key-heading" className="text-base font-semibold">
          Inbound key
        </h3>
        {keys.length === 0 ? (
          <p className="text-sm text-muted-foreground">No key issued.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {keys.map((k) => {
              const owner = keyOwners.get(k.id);
              return (
                <li key={k.id} className="flex flex-col">
                  <code
                    className="font-mono text-xs wrap-anywhere"
                    data-testid="api-connection-key-prefix"
                  >
                    {maskedToken(k.prefix)}
                  </code>
                  <span className="text-xs text-muted-foreground">
                    Issued {relativeTime(k.created_at)}
                    {owner ? ` by ${DisplayName(owner)}` : ''}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        {saved?.legacy_multi_credential && keys.length > 0 && (
          <p className="text-xs text-muted-foreground">
            These keys were migrated from personal tokens. Rotating replaces all
            of them with one key holding this connection&apos;s grants.
          </p>
        )}
        {blocked && !readOnly && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="api-connection-key-hint"
          >
            {blocked}
          </p>
        )}
        {!readOnly && (
          <div className="flex flex-wrap gap-2">
            {keys.length === 0 ? (
              <SecondaryButton
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                disabled={blocked !== null || pending}
                onClick={onIssue}
                data-testid="api-connection-key-issue"
              >
                Issue key
              </SecondaryButton>
            ) : (
              <>
                <SecondaryButton
                  type="button"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  disabled={blocked !== null || pending}
                  onClick={onRotate}
                  data-testid="api-connection-key-rotate"
                >
                  Rotate key
                </SecondaryButton>
                <SecondaryButton
                  type="button"
                  size="sm"
                  color="red"
                  className="min-h-11 sm:min-h-8"
                  disabled={pending}
                  onClick={onRevoke}
                  data-testid="api-connection-key-revoke"
                >
                  Revoke key
                </SecondaryButton>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
