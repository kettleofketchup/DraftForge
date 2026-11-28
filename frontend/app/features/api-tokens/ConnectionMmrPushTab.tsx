import type { UseFormReturn } from 'react-hook-form';

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
import type { OrgFeatureAccess } from '~/features/org-features';
import { TemplateFieldsEditor } from './ConnectionMappingEditor';
import type { ApiConnection, ConnectionForm } from './connectionSchemas';
import {
  ActionNote,
  CredentialSlotFields,
  DirectionSwitch,
  GameTypeField,
  featureLockReason,
  testBlockedReason,
  useConnectionTestAction,
} from './connectionSyncShared';

export interface ConnectionMmrPushTabProps {
  form: UseFormReturn<ConnectionForm>;
  saved: ApiConnection | null;
  dirty: boolean;
  readOnly: boolean;
  orgId: number;
  access: OrgFeatureAccess;
  onRunStarted?: (runId: string) => void;
}

export function ConnectionMmrPushTab({
  form,
  saved,
  dirty,
  readOnly,
  orgId,
  access,
  onRunStarted,
}: ConnectionMmrPushTabProps) {
  const auth = form.watch('outbound_auth');
  const test = useConnectionTestAction(orgId, access, saved, onRunStarted);
  const reason = testBlockedReason(saved, dirty);
  return (
    <div className="flex flex-col gap-6" data-testid="api-connection-push-tab">
      <DirectionSwitch
        form={form}
        name="mmr_push_enabled"
        label="MMR push"
        help="DraftForge posts each member's MMR change to the destination. Changes this connection imported are not sent back to it. Off by default."
        readOnly={readOnly}
        lockedReason={featureLockReason(access, 'mmr_sync')}
      />
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-base font-semibold">Request</legend>
        <FormField
          control={form.control}
          name="push.path"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Path</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  autoComplete="off"
                  spellCheck={false}
                  className="font-mono"
                  disabled={readOnly}
                  data-testid="api-connection-push-path"
                />
              </FormControl>
              <FormDescription>
                POSTed with a JSON body holding the delivery ID, org, game and
                one member&apos;s MMR and revision. {'{org_id}'} and{' '}
                {'{game_type}'} are filled in.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <TemplateFieldsEditor
          form={form}
          name="push.query"
          legend="Query fields"
          description="Pushes can use the Org ID and Game type variables."
          readOnly={readOnly}
          scopes={['any']}
        />
        {auth === 'api_key_field' && (
          <CredentialSlotFields
            form={form}
            prefix="push"
            allowBody
            readOnly={readOnly}
          />
        )}
        <GameTypeField
          form={form}
          readOnly={readOnly}
          help="Default pushes every game's MMR changes."
        />
      </fieldset>
      <section
        className="flex flex-col gap-3 border-t border-border pt-4"
        aria-labelledby="api-connection-push-actions"
      >
        <h3
          id="api-connection-push-actions"
          className="text-base font-semibold"
        >
          Test
        </h3>
        <p className="text-xs text-muted-foreground">
          Checks GET /health on the saved destination only. It sends no member
          data and works while the push is off.
        </p>
        <div>
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={reason !== null || test.pending}
            onClick={() => void test.run('mmr_push')}
            data-testid="api-connection-push-test"
          >
            Test destination health
          </SecondaryButton>
        </div>
        <ActionNote
          reason={reason}
          error={test.error}
          testId="api-connection-push-action"
        />
      </section>
    </div>
  );
}
