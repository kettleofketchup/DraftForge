import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import {
  useForm,
  type FieldErrors,
  type Resolver,
  type UseFormReturn,
} from 'react-hook-form';
import { toast } from 'sonner';

import {
  getOrgSettings,
  orgSettingsKey,
  patchOrgSettings,
  signupRetentionFormSchema,
  toRetentionPatch,
  type OrgSettings,
  type SignupRetentionFormValues,
} from '~/components/api/orgSettingsAPI';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import {
  submitForm,
  type SettingsFormUnit,
} from '~/components/patterns/settingsSaveBar';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Label } from '~/components/ui/label';
import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import { Skeleton } from '~/components/ui/skeleton';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { SettingNumberInput } from './settingFields';

const log = getLogger('OrgSettings');

const SECTION_ID = 'signup-records';
const DAYS_FIELD = 'signup_record_retention_days';
const DEFAULT_PERIOD_DAYS = 365;

const EMPTY_FORM: SignupRetentionFormValues = {
  retention_mode: 'forever',
  signup_record_retention_days: null,
};

export function pickRetentionValues(s: OrgSettings): SignupRetentionFormValues {
  return {
    retention_mode:
      s.signup_record_retention_days === null ? 'forever' : 'period',
    signup_record_retention_days: s.signup_record_retention_days,
  };
}

function serverDaysError(err: unknown): string | undefined {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (!data || typeof data !== 'object') return undefined;
  const value = (data as Record<string, unknown>)[DAYS_FIELD];
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  return typeof value === 'string' ? value : undefined;
}

export function useSignupRecordsRetentionSection(
  organizationId: number,
  enabled: boolean,
  sectionsRef: RefObject<SettingsDialogHandle<string> | null>,
): { content: ReactNode; unit: SettingsFormUnit } {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: orgSettingsKey(organizationId),
    queryFn: () => getOrgSettings(organizationId),
    enabled,
  });

  const minRef = useRef(30);
  if (data) minRef.current = data.signup_record_min_retention_days;
  const resolver = useMemo<Resolver<SignupRetentionFormValues>>(
    () => (values, context, options) =>
      zodResolver(signupRetentionFormSchema(minRef.current))(
        values,
        context,
        options,
      ),
    [],
  );
  const form = useForm<SignupRetentionFormValues>({
    resolver,
    defaultValues: data ? pickRetentionValues(data) : EMPTY_FORM,
  });

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (!data) return;
    if (!form.formState.isDirty) form.reset(pickRetentionValues(data));
    setHydrated(true);
  }, [data, form]);

  const onSubmit =
    (select: boolean) =>
    async (values: SignupRetentionFormValues): Promise<boolean> => {
      try {
        const saved = await patchOrgSettings(
          organizationId,
          toRetentionPatch(values),
        );
        queryClient.setQueryData(orgSettingsKey(organizationId), saved);
        form.reset(pickRetentionValues(saved));
        return true;
      } catch (err) {
        log.error('Failed to save sign-up record retention', {
          organizationId,
          err,
        });
        const message = serverDaysError(err);
        if (message) {
          form.setError(DAYS_FIELD, { type: 'server', message });
          if (select) sectionsRef.current?.selectSection(SECTION_ID);
        } else {
          toast.error(extractApiError(err) ?? 'Could not save settings');
        }
        return false;
      }
    };

  const onInvalid =
    (select: boolean) =>
    (errors: FieldErrors<SignupRetentionFormValues>): void => {
      const message = Object.values(errors)[0]?.message;
      if (select) sectionsRef.current?.selectSection(SECTION_ID);
      toast.error('Please fix the highlighted fields', {
        description: typeof message === 'string' ? message : undefined,
      });
    };

  const unit: SettingsFormUnit = {
    id: SECTION_ID,
    isDirty: enabled && form.formState.isDirty,
    save: (opts) => {
      const select = opts?.select !== false;
      return submitForm(form, onSubmit(select), onInvalid(select));
    },
    discard: () => {
      if (data) form.reset(pickRetentionValues(data));
    },
  };

  const minDays = data?.signup_record_min_retention_days;
  const content = useMemo(
    () => (
      <section
        data-testid="org-settings-signup-records"
        className="rounded-lg border border-border p-6"
      >
        <h2 className="text-lg font-semibold">Sign-up records</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          How long the history of who signed up for each event is kept.
        </p>
        {isLoading && (
          <div className="mt-4 flex flex-col gap-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-40" />
          </div>
        )}
        {isError && (
          <p
            className="mt-4 text-sm text-destructive"
            data-testid="signup-retention-error"
          >
            {extractApiError(error) ?? 'Failed to load settings'}
          </p>
        )}
        {minDays !== undefined && hydrated && (
          <RetentionFields form={form} minDays={minDays} />
        )}
      </section>
    ),
    [isLoading, isError, error, minDays, hydrated, form],
  );

  return { content, unit };
}

function RetentionFields({
  form,
  minDays,
}: {
  form: UseFormReturn<SignupRetentionFormValues>;
  minDays: number;
}) {
  const onModeChange = (mode: string): void => {
    const opts = { shouldDirty: true, shouldValidate: false };
    if (mode === 'period') {
      form.setValue('retention_mode', 'period', opts);
      if (form.getValues(DAYS_FIELD) === null) {
        form.setValue(DAYS_FIELD, DEFAULT_PERIOD_DAYS, opts);
      }
    } else {
      form.setValue('retention_mode', 'forever', opts);
      form.setValue(DAYS_FIELD, null, opts);
      form.clearErrors(DAYS_FIELD);
    }
  };

  return (
    <Form {...form}>
      <div className="mt-4 flex flex-col gap-4">
        <FormField
          control={form.control}
          name="retention_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Keep sign-up records</FormLabel>
              <RadioGroup
                value={field.value}
                onValueChange={onModeChange}
                className="flex flex-col gap-2 sm:flex-row sm:gap-6"
              >
                <div className="flex min-h-11 items-center gap-2 sm:min-h-0">
                  <RadioGroupItem
                    value="forever"
                    id="signup-retention-forever"
                    data-testid="signup-retention-forever"
                  />
                  <Label htmlFor="signup-retention-forever">Forever</Label>
                </div>
                <div className="flex min-h-11 items-center gap-2 sm:min-h-0">
                  <RadioGroupItem
                    value="period"
                    id="signup-retention-period"
                    data-testid="signup-retention-period"
                  />
                  <Label htmlFor="signup-retention-period">
                    For a set period
                  </Label>
                </div>
              </RadioGroup>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name={DAYS_FIELD}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Days</FormLabel>
              <FormControl>
                <SettingNumberInput
                  nullable
                  min={minDays}
                  step={1}
                  inputMode="numeric"
                  disabled={form.watch('retention_mode') !== 'period'}
                  data-testid="signup-retention-days"
                  name={field.name}
                  ref={field.ref}
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                />
              </FormControl>
              <FormDescription>
                Minimum {minDays} days. Records for events that ended longer ago
                than this are deleted every night and cannot be recovered.
                Current sign-ups are never deleted.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
    </Form>
  );
}
