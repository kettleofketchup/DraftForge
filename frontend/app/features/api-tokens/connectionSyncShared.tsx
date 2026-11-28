import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';

import { GAME_LABEL, GAME_TYPES } from '~/components/game/constants';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
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
import { useTestConnection } from './connectionQueries';
import {
  connectionErrorCode,
  connectionErrorMessage,
  type ApiConnection,
  type ConnectionForm,
  type TestDirection,
} from './connectionSchemas';

const log = getLogger('ConnectionSync');

type Form = UseFormReturn<ConnectionForm>;

function savedBlockedReason(
  saved: ApiConnection | null,
  dirty: boolean,
  action: 'testing' | 'pulling',
): string | null {
  const runs = action === 'testing' ? 'Tests' : 'Pulls';
  if (!saved) return `Save the connection before ${action}.`;
  if (saved.archived_at) return `Archived connections cannot run.`;
  if (dirty) {
    return `Save or discard your changes first. ${runs} use the saved configuration.`;
  }
  if (!saved.outbound_base_url) {
    return `Add a destination on the General tab and save before ${action}.`;
  }
  if (saved.outbound_auth !== 'none' && !saved.credential_present) {
    return `Add the credential on the General tab and save before ${action}.`;
  }
  return null;
}

/** Why a test of the saved configuration cannot start, else null. Disabled directions can be tested. */
export function testBlockedReason(
  saved: ApiConnection | null,
  dirty: boolean,
): string | null {
  return savedBlockedReason(saved, dirty, 'testing');
}

/** Why Pull now cannot start, else null. */
export function pullBlockedReason(
  saved: ApiConnection | null,
  dirty: boolean,
): string | null {
  const blocked = savedBlockedReason(saved, dirty, 'pulling');
  if (blocked || !saved) return blocked;
  if (!saved.enabled) return 'Turn the connection on and save before pulling.';
  if (!saved.mmr_pull_enabled) {
    return 'Turn on MMR pull and save before pulling.';
  }
  return null;
}

export interface DirectionSwitchProps {
  form: Form;
  name: 'mmr_push_enabled' | 'mmr_pull_enabled' | 'promotion_push_enabled';
  label: string;
  help: string;
  readOnly: boolean;
  /** Turning on is refused with this reason; turning off always works. */
  lockedReason?: string | null;
}

export function DirectionSwitch({
  form,
  name,
  label,
  help,
  readOnly,
  lockedReason,
}: DirectionSwitchProps) {
  const id = `api-connection-${name.replaceAll('_', '-')}`;
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field, fieldState }) => (
        <div className="flex flex-col gap-1">
          <div className="flex items-start gap-3">
            <Switch
              id={id}
              checked={field.value}
              onCheckedChange={field.onChange}
              disabled={readOnly || (Boolean(lockedReason) && !field.value)}
              aria-describedby={`${id}-help`}
              data-testid={id}
            />
            <div className="flex flex-col">
              <Label htmlFor={id}>{label}</Label>
              <span id={`${id}-help`} className="text-xs text-muted-foreground">
                {help}
              </span>
              {lockedReason && (
                <span
                  className="text-xs text-warning"
                  data-testid={`${id}-locked`}
                >
                  {lockedReason}
                </span>
              )}
            </div>
          </div>
          {fieldState.error?.message && (
            <p role="alert" className="text-sm font-medium text-destructive">
              {fieldState.error.message}
            </p>
          )}
        </div>
      )}
    />
  );
}

export function featureLockReason(
  access: Pick<OrgFeatureAccess, 'mmrSyncEnabled' | 'promotionEnabled'>,
  feature: 'mmr_sync' | 'promotion',
): string | null {
  if (feature === 'mmr_sync' && !access.mmrSyncEnabled) {
    return 'The MMR sync API is locked for this organization. Existing settings can still be turned off.';
  }
  if (feature === 'promotion' && !access.promotionEnabled) {
    return 'Promotion is locked for this organization. Existing settings can still be turned off.';
  }
  return null;
}

export function CredentialSlotFields({
  form,
  prefix,
  allowBody,
  readOnly,
}: {
  form: Form;
  prefix: 'push' | 'pull';
  allowBody: boolean;
  readOnly: boolean;
}) {
  const location = form.watch(`${prefix}.credential_location`);
  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      data-testid={`api-connection-${prefix}-credential-slot`}
    >
      <FormField
        control={form.control}
        name={`${prefix}.credential_location`}
        render={({ field }) => (
          <FormItem>
            <FormLabel>API key goes in</FormLabel>
            <BrandSelect
              value={field.value}
              onValueChange={field.onChange}
              disabled={readOnly}
            >
              <FormControl>
                <BrandSelectTrigger
                  data-testid={`api-connection-${prefix}-credential-location`}
                >
                  <SelectValue />
                </BrandSelectTrigger>
              </FormControl>
              <BrandSelectContent>
                <BrandSelectItem value="none">Not chosen</BrandSelectItem>
                <BrandSelectItem value="query">A query field</BrandSelectItem>
                {allowBody && (
                  <BrandSelectItem value="body">A body field</BrandSelectItem>
                )}
              </BrandSelectContent>
            </BrandSelect>
            <FormDescription>
              DraftForge fills it with the stored credential when it sends.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      {location !== 'none' && (
        <FormField
          control={form.control}
          name={`${prefix}.credential_key`}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Key field name</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder="api_key"
                  autoComplete="off"
                  disabled={readOnly}
                  data-testid={`api-connection-${prefix}-credential-key`}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}

export function GameTypeField({
  form,
  readOnly,
  help,
}: {
  form: Form;
  readOnly: boolean;
  help: string;
}) {
  return (
    <FormField
      control={form.control}
      name="game_type"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Game</FormLabel>
          <BrandSelect
            value={field.value === null ? 'default' : `${field.value}`}
            onValueChange={(v) =>
              field.onChange(v === 'default' ? null : Number(v))
            }
            disabled={readOnly}
          >
            <FormControl>
              <BrandSelectTrigger data-testid="api-connection-game-type">
                <SelectValue />
              </BrandSelectTrigger>
            </FormControl>
            <BrandSelectContent>
              <BrandSelectItem value="default">
                Default (pull Dota 2, push every game)
              </BrandSelectItem>
              {GAME_TYPES.map((game) => (
                <BrandSelectItem key={game} value={`${game}`}>
                  {GAME_LABEL[game]}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
          <FormDescription>{help}</FormDescription>
        </FormItem>
      )}
    />
  );
}

/** Starts a test of the saved configuration and reports refusals inline. */
export function useConnectionTestAction(
  orgId: number,
  access: OrgFeatureAccess,
  saved: ApiConnection | null,
  onRunStarted?: (runId: string) => void,
) {
  const test = useTestConnection(orgId, access);
  const [error, setError] = useState<string | null>(null);
  const run = async (direction: TestDirection): Promise<void> => {
    if (!saved) return;
    setError(null);
    try {
      const runId = await test.mutateAsync({
        connectionId: saved.id,
        direction,
      });
      onRunStarted?.(runId);
    } catch (err) {
      const code = connectionErrorCode(err);
      log.error('Failed to start connection test', {
        orgId,
        connectionId: saved.id,
        direction,
        code,
      });
      setError(
        code
          ? connectionErrorMessage(code)
          : (extractApiError(err) ?? 'Could not start the test'),
      );
    }
  };
  return { run, pending: test.isPending, error };
}

export function ActionNote({
  reason,
  error,
  testId,
}: {
  reason: string | null;
  error: string | null;
  testId: string;
}) {
  return (
    <>
      {reason && (
        <p
          className="text-xs text-muted-foreground"
          data-testid={`${testId}-reason`}
        >
          {reason}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="text-sm font-medium text-destructive"
          data-testid={`${testId}-error`}
        >
          {error}
        </p>
      )}
    </>
  );
}
