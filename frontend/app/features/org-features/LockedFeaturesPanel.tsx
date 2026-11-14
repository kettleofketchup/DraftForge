import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import { Switch } from '~/components/ui/switch';
import { Textarea } from '~/components/ui/textarea';
import { useIsSuperuser } from '~/hooks/usePermissions';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { getOrgFeatures, setOrgFeature } from './api';
import { orgFeaturesKey } from './queryKeys';
import {
  OrgFeatureFormSchema,
  type FeatureKey,
  type OrgFeatureFormValues,
  type OrgFeatureRow,
} from './schemas';

const log = getLogger('LockedFeaturesPanel');

const FEATURE_LABELS: Record<FeatureKey, string> = {
  contributions: 'Contributions',
  promotion: 'Promotion',
};

export interface LockedFeaturesPanelProps {
  orgId: number;
}

export function LockedFeaturesPanel({ orgId }: LockedFeaturesPanelProps) {
  const isSuperuser = useIsSuperuser();
  const {
    data: rows,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: orgFeaturesKey(orgId),
    queryFn: () => getOrgFeatures(orgId),
    enabled: isSuperuser,
  });

  if (!isSuperuser) return null;

  return (
    <section
      data-testid="locked-features-panel"
      className="mt-12 rounded-lg border border-primary/40 bg-base-900/40 p-6"
    >
      <h2 className="text-lg font-semibold">Locked features</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Site admins only. Locked features are hidden from the organization;
        their data is kept.
      </p>
      {isLoading && (
        <p className="mt-4 text-sm text-muted-foreground">Loading...</p>
      )}
      {isError && (
        <p
          className="mt-4 text-sm text-destructive"
          data-testid="locked-features-error"
        >
          {extractApiError(error) ?? 'Failed to load locked features'}
        </p>
      )}
      <div className="mt-4 flex flex-col gap-4">
        {rows?.map((row) => (
          <LockedFeatureRow
            key={`${row.feature}:${row.enabled}:${row.notes}:${row.enabled_at ?? ''}`}
            orgId={orgId}
            row={row}
          />
        ))}
      </div>
    </section>
  );
}

interface LockedFeatureRowProps {
  orgId: number;
  row: OrgFeatureRow;
}

function LockedFeatureRow({ orgId, row }: LockedFeatureRowProps) {
  const queryClient = useQueryClient();
  const label = FEATURE_LABELS[row.feature];
  const form = useForm<OrgFeatureFormValues>({
    resolver: zodResolver(OrgFeatureFormSchema),
    defaultValues: { enabled: row.enabled, notes: row.notes },
  });

  const mutation = useMutation({
    mutationFn: (values: OrgFeatureFormValues) =>
      setOrgFeature(orgId, { feature: row.feature, ...values }),
    onSuccess: async (updated, values) => {
      queryClient.setQueryData(orgFeaturesKey(orgId), updated);
      if (values.enabled === row.enabled) toast.success(`${label} notes saved`);
      else toast.success(`${label} ${values.enabled ? 'unlocked' : 'locked'}`);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: organizationQueryKey(orgId),
        }),
        queryClient.invalidateQueries({ queryKey: orgFeaturesKey(orgId) }),
      ]);
    },
    onError: (err) => {
      log.error('Failed to save org feature', {
        orgId,
        feature: row.feature,
        err,
      });
      toast.error(extractApiError(err) ?? `Failed to save ${label}`);
    },
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
        className="flex flex-col gap-3 rounded-md border border-border p-4"
        data-testid={`locked-feature-row-${row.feature}`}
      >
        <FormField
          control={form.control}
          name="enabled"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center gap-3">
              <FormControl>
                <Switch
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  disabled={mutation.isPending}
                  data-testid={`locked-feature-switch-${row.feature}`}
                />
              </FormControl>
              <FormLabel className="font-medium">{label}</FormLabel>
            </FormItem>
          )}
        />
        {row.enabled_by && (
          <p className="text-xs text-muted-foreground">
            Last unlocked by {row.enabled_by.username}
            {row.enabled_at &&
              ` on ${new Date(row.enabled_at).toLocaleString()}`}
          </p>
        )}
        <FormField
          control={form.control}
          name="notes"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-sm">Notes</FormLabel>
              <FormControl>
                <Textarea
                  {...field}
                  rows={2}
                  disabled={mutation.isPending}
                  placeholder="Payment reference, trial end, ..."
                  data-testid={`locked-feature-notes-${row.feature}`}
                />
              </FormControl>
            </FormItem>
          )}
        />
        <div>
          <SecondaryButton
            type="submit"
            disabled={mutation.isPending}
            data-testid={`locked-feature-save-${row.feature}`}
          >
            {mutation.isPending ? 'Saving...' : 'Save'}
          </SecondaryButton>
        </div>
      </form>
    </Form>
  );
}
