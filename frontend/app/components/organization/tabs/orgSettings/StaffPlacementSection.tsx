import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode, type RefObject } from 'react';
import { useForm, type FieldErrors, type UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';

import {
  getOrgSettings,
  orgSettingsKey,
  patchOrgSettings,
  StaffPlacementFormSchema,
  type OrgSettings,
  type StaffOverridePolicy,
  type StaffPlacementFormValues,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Skeleton } from '~/components/ui/skeleton';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

const log = getLogger('OrgSettings');

const POLICY_OPTIONS: readonly {
  value: StaffOverridePolicy;
  label: string;
  help: string;
}[] = [
  {
    value: 'silent',
    label: 'Silent',
    help: 'Staff placements ignore seating rules',
  },
  {
    value: 'confirm',
    label: 'Confirm',
    help: 'Staff must confirm a warning naming the broken rule',
  },
  {
    value: 'block',
    label: 'Block',
    help: 'Staff placements that break seating rules are refused',
  },
];

export function pickFormValues(s: OrgSettings): StaffPlacementFormValues {
  return {
    staff_override_policy: s.staff_override_policy,
    staff_override_warning_codes: [...s.staff_override_warning_codes],
  };
}

const SECTION_ID = 'staff-placement';

const EMPTY_FORM: StaffPlacementFormValues = {
  staff_override_policy: 'silent',
  staff_override_warning_codes: [],
};

export function useStaffPlacementSection(
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
  const form = useForm<StaffPlacementFormValues>({
    resolver: zodResolver(StaffPlacementFormSchema),
    defaultValues: data ? pickFormValues(data) : EMPTY_FORM,
  });

  // Fields mount only after the form holds the loaded values: Radix Select's
  // hidden native select emits onChange('') when its value changes after mount.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (!data) return;
    if (!form.formState.isDirty) form.reset(pickFormValues(data));
    setHydrated(true);
  }, [data, form]);

  const onSubmit = async (
    values: StaffPlacementFormValues,
  ): Promise<boolean> => {
    const dirty = form.formState.dirtyFields;
    const changes: Partial<StaffPlacementFormValues> = {};
    if (dirty.staff_override_policy) {
      changes.staff_override_policy = values.staff_override_policy;
    }
    if (dirty.staff_override_warning_codes) {
      changes.staff_override_warning_codes =
        values.staff_override_warning_codes;
    }
    try {
      const saved = await patchOrgSettings(organizationId, changes);
      queryClient.setQueryData(orgSettingsKey(organizationId), saved);
      form.reset(pickFormValues(saved));
      return true;
    } catch (err) {
      log.error('Failed to save org settings', { organizationId, err });
      toast.error(extractApiError(err) ?? 'Could not save settings');
      return false;
    }
  };

  const onInvalid =
    (select: boolean) =>
    (errors: FieldErrors<StaffPlacementFormValues>): void => {
      const message = Object.values(errors)[0]?.message;
      if (select) sectionsRef.current?.selectSection(SECTION_ID);
      toast.error('Please fix the highlighted fields', {
        description: typeof message === 'string' ? message : undefined,
      });
    };

  const unit: SettingsFormUnit = {
    id: SECTION_ID,
    isDirty: enabled && form.formState.isDirty,
    save: (opts) =>
      submitForm(form, onSubmit, onInvalid(opts?.select !== false)),
    discard: () => {
      if (data) form.reset(pickFormValues(data));
    },
  };

  const content = (
    <section
      data-testid="org-settings-staff-placement"
      className="rounded-lg border border-border p-6"
    >
      <h2 className="text-lg font-semibold">Staff placement</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        How seating rules apply when staff place members on a roster.
        Eligibility and team rules, such as a missing Steam ID, MMR below the
        minimum or the stand-in cap, always ask staff to confirm with a reason,
        whatever this policy says.
      </p>
      {isLoading && (
        <div className="mt-4 flex flex-col gap-3">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}
      {isError && (
        <p
          className="mt-4 text-sm text-destructive"
          data-testid="org-settings-error"
        >
          {extractApiError(error) ?? 'Failed to load settings'}
        </p>
      )}
      {data && hydrated && <StaffPlacementFields form={form} settings={data} />}
    </section>
  );

  return { content, unit };
}

function StaffPlacementFields({
  form,
  settings,
}: {
  form: UseFormReturn<StaffPlacementFormValues>;
  settings: OrgSettings;
}) {
  const allCodes = settings.available_warning_codes.map((c) => c.code);

  return (
    <Form {...form}>
      <div className="mt-4 flex flex-col gap-6">
        <FormField
          control={form.control}
          name="staff_override_policy"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Staff override policy</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger
                    data-testid="org-settings-policy-select"
                    className="w-full sm:w-64"
                  >
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {POLICY_OPTIONS.map((o) => (
                    <SelectItem
                      key={o.value}
                      value={o.value}
                      data-testid={`org-settings-policy-option-${o.value}`}
                    >
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                {POLICY_OPTIONS.find((o) => o.value === field.value)?.help}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="staff_override_warning_codes"
          render={({ field }) => {
            const selected = new Set(field.value);
            const toggle = (code: string, checked: boolean) => {
              const next = new Set(selected);
              if (checked) next.add(code);
              else next.delete(code);
              field.onChange(allCodes.filter((c) => next.has(c)));
            };
            return (
              <FormItem>
                <FormLabel>Seating rules staff are warned about</FormLabel>
                <div className="flex flex-col gap-2">
                  {settings.available_warning_codes.map(({ code, label }) => (
                    <label
                      key={code}
                      className="flex min-h-11 cursor-pointer items-center gap-3 text-sm sm:min-h-0"
                    >
                      <input
                        type="checkbox"
                        data-testid={`org-settings-code-${code}`}
                        checked={selected.has(code)}
                        onChange={(e) => toggle(code, e.target.checked)}
                        className="h-4 w-4 shrink-0 rounded border-border accent-primary"
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <FormMessage />
              </FormItem>
            );
          }}
        />
      </div>
    </Form>
  );
}
