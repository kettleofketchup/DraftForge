import type { UseFormReturn } from 'react-hook-form';

import { Badge } from '~/components/ui/badge';
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
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { connectionStatus, lastSyncText } from './apiConnectionColumns';
import { relativeTime } from './apiTokenColumns';
import {
  CONNECTION_NAME_MAX_LENGTH,
  OUTBOUND_AUTH_LABELS,
  OUTBOUND_AUTH_VALUES,
  connectionErrorMessage,
  type ApiConnection,
  type ConnectionForm,
  type OutboundAuth,
} from './connectionSchemas';

export interface ConnectionGeneralTabProps {
  form: UseFormReturn<ConnectionForm>;
  /** The latest saved row; null while creating. */
  saved: ApiConnection | null;
  readOnly: boolean;
  onArchive?: () => void;
  archiving?: boolean;
}

export function ConnectionGeneralTab({
  form,
  saved,
  readOnly,
  onArchive,
  archiving = false,
}: ConnectionGeneralTabProps) {
  const auth = form.watch('outbound_auth');
  const action = form.watch('credential_action');
  const credentialError = form.formState.errors.outbound_credential?.message;
  const status = saved ? connectionStatus(saved) : null;

  return (
    <div className="flex flex-col gap-6">
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl>
              <Input
                {...field}
                maxLength={CONNECTION_NAME_MAX_LENGTH}
                placeholder="Ratings service"
                autoComplete="off"
                disabled={readOnly}
                data-testid="api-connection-name"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="enabled"
        render={({ field }) => (
          <div className="flex items-start gap-3">
            <Switch
              id="api-connection-enabled"
              checked={field.value}
              onCheckedChange={field.onChange}
              disabled={readOnly}
              aria-describedby="api-connection-enabled-help"
              data-testid="api-connection-enabled"
            />
            <div className="flex flex-col">
              <Label htmlFor="api-connection-enabled">Connection enabled</Label>
              <span
                id="api-connection-enabled-help"
                className="text-xs text-muted-foreground"
              >
                Turns every direction of this connection on or off. Each
                direction also has its own switch, and all start off.
              </span>
            </div>
          </div>
        )}
      />

      {saved && status && (
        <dl
          className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm"
          data-testid="api-connection-status"
        >
          <dt className="text-muted-foreground">Status</dt>
          <dd>
            <Badge variant={status.variant}>{status.label}</Badge>
          </dd>
          <dt className="text-muted-foreground">Last sync</dt>
          <dd>{lastSyncText(saved)}</dd>
          {saved.last_error_code && (
            <>
              <dt className="text-muted-foreground">Last error</dt>
              <dd
                className="text-destructive"
                data-testid="api-connection-last-error"
              >
                {connectionErrorMessage(saved.last_error_code)}
              </dd>
            </>
          )}
        </dl>
      )}

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-base font-semibold">
          Outbound destination
        </legend>
        <p className="text-sm text-muted-foreground">
          Where DraftForge sends pushes and pulls. HTTPS on port 443 only.
        </p>
        <FormField
          control={form.control}
          name="outbound_base_url"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Base URL</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="url"
                  inputMode="url"
                  placeholder="https://ratings.example"
                  autoComplete="off"
                  disabled={readOnly}
                  data-testid="api-connection-base-url"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="outbound_auth"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Authentication</FormLabel>
              <BrandSelect
                value={field.value}
                onValueChange={(value) => field.onChange(value as OutboundAuth)}
                disabled={readOnly}
              >
                <FormControl>
                  <BrandSelectTrigger data-testid="api-connection-auth">
                    <SelectValue />
                  </BrandSelectTrigger>
                </FormControl>
                <BrandSelectContent>
                  {OUTBOUND_AUTH_VALUES.map((value) => (
                    <BrandSelectItem key={value} value={value}>
                      {OUTBOUND_AUTH_LABELS[value]}
                    </BrandSelectItem>
                  ))}
                </BrandSelectContent>
              </BrandSelect>
              <FormDescription>
                The credential belongs to the external service. DraftForge
                stores it encrypted and never shows it again.
              </FormDescription>
            </FormItem>
          )}
        />
        {auth !== 'none' && (
          <CredentialControls
            form={form}
            saved={saved}
            action={action}
            readOnly={readOnly}
          />
        )}
        <OutboundAuthority form={form} saved={saved} readOnly={readOnly} />
        {credentialError && (
          <p
            role="alert"
            className="text-sm font-medium text-destructive"
            data-testid="api-connection-credential-error"
          >
            {credentialError}
          </p>
        )}
      </fieldset>

      {saved && !saved.archived_at && onArchive && (
        <div className="flex flex-col gap-2 border-t border-border pt-4">
          <p className="text-sm text-muted-foreground">
            Archiving turns every direction off, revokes the inbound key and
            removes the stored credential. Run history stays readable.
          </p>
          <div>
            <SecondaryButton
              type="button"
              color="red"
              className="min-h-11 sm:min-h-8"
              onClick={onArchive}
              disabled={archiving}
              data-testid="api-connection-archive"
            >
              Archive connection
            </SecondaryButton>
          </div>
        </div>
      )}
    </div>
  );
}

function CredentialControls({
  form,
  saved,
  action,
  readOnly,
}: {
  form: UseFormReturn<ConnectionForm>;
  saved: ApiConnection | null;
  action: ConnectionForm['credential_action'];
  readOnly: boolean;
}) {
  const stored = saved?.credential_present ?? false;
  const setAction = (next: ConnectionForm['credential_action']): void => {
    form.setValue('credential_action', next, { shouldDirty: true });
    form.setValue('outbound_credential', '', { shouldDirty: true });
    form.clearErrors('outbound_credential');
  };
  return (
    <div
      className="flex flex-col gap-3"
      data-testid="api-connection-credential-block"
    >
      <p className="text-sm" data-testid="api-connection-credential-status">
        {stored
          ? `Credential stored${
              saved?.outbound_credential_set_at
                ? `, set ${relativeTime(saved.outbound_credential_set_at)}`
                : ''
            }`
          : 'No credential stored'}
        {action === 'clear' && ' (will be removed when you save)'}
      </p>
      {action === 'replace' ? (
        <FormField
          control={form.control}
          name="outbound_credential"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{stored ? 'New credential' : 'Credential'}</FormLabel>
              <FormControl>
                <Input
                  name={field.name}
                  ref={field.ref}
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  type="password"
                  autoComplete="new-password"
                  disabled={readOnly}
                  data-testid="api-connection-credential"
                />
              </FormControl>
            </FormItem>
          )}
        />
      ) : null}
      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          {action === 'keep' ? (
            <>
              <SecondaryButton
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={() => setAction('replace')}
                data-testid="api-connection-credential-replace"
              >
                {stored ? 'Replace credential' : 'Add credential'}
              </SecondaryButton>
              {stored && (
                <SecondaryButton
                  type="button"
                  size="sm"
                  color="red"
                  className="min-h-11 sm:min-h-8"
                  onClick={() => setAction('clear')}
                  data-testid="api-connection-credential-clear"
                >
                  Clear credential
                </SecondaryButton>
              )}
            </>
          ) : (
            <SecondaryButton
              type="button"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => setAction('keep')}
              data-testid="api-connection-credential-keep"
            >
              {action === 'clear' ? 'Keep stored credential' : 'Cancel'}
            </SecondaryButton>
          )}
        </div>
      )}
    </div>
  );
}

const OUTBOUND_DIRECTIONS = [
  { name: 'mmr_pull_enabled', label: 'MMR pull' },
  { name: 'mmr_push_enabled', label: 'MMR push' },
  { name: 'promotion_push_enabled', label: 'promotion push' },
] as const;

/** Who outbound work runs under, and the way back after that admin lost access. */
function OutboundAuthority({
  form,
  saved,
  readOnly,
}: {
  form: UseFormReturn<ConnectionForm>;
  saved: ApiConnection | null;
  readOnly: boolean;
}) {
  const auth = form.watch('outbound_auth');
  const principal =
    saved && (saved.outbound_auth === 'none') === (auth === 'none')
      ? saved.outbound_principal
      : null;
  const lost = saved?.last_error_code === 'authority_lost';
  const directions = OUTBOUND_DIRECTIONS.filter(
    (d) => d.name !== 'promotion_push_enabled' || saved?.promotion_stream,
  );
  const reenable = (name: (typeof OUTBOUND_DIRECTIONS)[number]['name']) => {
    form.setValue(name, true, { shouldDirty: true, shouldValidate: true });
    if (auth !== 'none' && form.getValues('credential_action') !== 'replace') {
      form.setValue('credential_action', 'replace', { shouldDirty: true });
      form.setValue('outbound_credential', '', { shouldDirty: true });
    }
  };
  return (
    <div
      className="flex flex-col gap-2 text-sm"
      data-testid="api-connection-authority"
    >
      {principal ? (
        <div
          className="flex flex-wrap items-center gap-2"
          data-testid="api-connection-authorizer"
        >
          <span className="text-muted-foreground">
            {auth === 'none' ? 'Authorized by' : 'Credential supplied by'}
          </span>
          <UserAvatar user={principal} size="xs" />
          <span>{DisplayName(principal)}</span>
        </div>
      ) : (
        <p
          className="text-xs text-muted-foreground"
          data-testid="api-connection-authorizer-none"
        >
          {auth === 'none'
            ? 'No credential is sent. Outbound work runs under the admin who turns on a direction and saves.'
            : 'Outbound work runs under the admin who supplies the credential.'}
        </p>
      )}
      {lost && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-md border border-warning/40 p-3"
          data-testid="api-connection-authority-lost"
        >
          <p>
            Outbound directions were turned off because the admin who authorized
            them no longer manages this organization.
            {auth === 'none'
              ? ' Turning a direction back on and saving makes you the authorizer.'
              : ' Enter a new credential; saving makes you its owner.'}
          </p>
          {!readOnly && (
            <div className="flex flex-wrap gap-2">
              {directions.map((d) => (
                <SecondaryButton
                  key={d.name}
                  type="button"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  onClick={() => reenable(d.name)}
                  data-testid={`api-connection-reenable-${d.name}`}
                >
                  Turn {d.label} back on
                </SecondaryButton>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
