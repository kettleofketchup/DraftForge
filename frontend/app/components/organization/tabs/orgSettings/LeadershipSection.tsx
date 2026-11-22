import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type RefObject } from 'react';
import {
  useFieldArray,
  useForm,
  useWatch,
  type FieldErrors,
  type UseFormReturn,
} from 'react-hook-form';
import { toast } from 'sonner';

import { useOrganization } from '~/components/organization/hooks/useOrganization';
import {
  NumberSetting,
  SettingsGroup,
  ToggleSetting,
} from '~/components/organization/tabs/orgSettings/settingFields';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import {
  submitForm,
  type SettingsFormUnit,
} from '~/components/patterns/settingsSaveBar';
import { SecondaryButton } from '~/components/ui/buttons';
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
import { Switch } from '~/components/ui/switch';
import {
  LeadershipSettingsFormSchema,
  MAX_ACTIVE_TRAITS,
  TRAIT_KEY_MAX_LENGTH,
  TRAIT_LABEL_MAX_LENGTH,
  TraitFormSchema,
  refusalMessage,
  useDeleteTrait,
  useLeadershipSettings,
  useLeadershipTraits,
  usePatchLeadershipSettings,
  usePutTraits,
  type LeadershipSettings,
  type LeadershipSettingsForm,
  type TraitForm,
} from '~/features/leadership';
import {
  leadershipSettingsFieldErrors,
  leadershipSettingsPatch,
  pickLeadershipFormValues,
  slugifyTraitKey,
  traitFieldErrors,
  traitFormValues,
  traitPutItems,
} from '~/features/leadership/settingsForm';
import { useOrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

const log = getLogger('LeadershipSection');

const SECTION_ID = 'leadership';

type NumberField = Exclude<
  keyof LeadershipSettingsForm,
  'leaderboard_public' | 'points'
>;

export function useLeadershipSection(
  organizationId: number,
  enabled: boolean,
  sectionsRef: RefObject<SettingsDialogHandle<string> | null>,
): { content: ReactNode; unit: SettingsFormUnit } {
  const { organization } = useOrganization(
    enabled ? organizationId : undefined,
  );
  const access = useOrgFeatureAccess(organization ?? undefined);
  const settingsQuery = useLeadershipSettings(organizationId, access, enabled);
  const traitsQuery = useLeadershipTraits(organizationId, access, enabled);
  const settings = settingsQuery.data;
  const traits = traitsQuery.data;

  const form = useForm<LeadershipSettingsForm>({
    resolver: zodResolver(LeadershipSettingsFormSchema),
    defaultValues: settings ? pickLeadershipFormValues(settings) : undefined,
  });
  const traitForm = useForm<TraitForm>({
    resolver: zodResolver(TraitFormSchema),
    defaultValues: traits ? traitFormValues(traits) : undefined,
  });
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (settings && !form.formState.isDirty) {
      form.reset(pickLeadershipFormValues(settings));
    }
  }, [settings, form]);
  useEffect(() => {
    if (traits && !traitForm.formState.isDirty) {
      traitForm.reset(traitFormValues(traits));
    }
  }, [traits, traitForm]);
  useEffect(() => {
    if (settings && traits) setHydrated(true);
  }, [settings, traits]);

  const patch = usePatchLeadershipSettings(organizationId, access);
  const put = usePutTraits(organizationId, access);

  const select = (yes: boolean) => {
    if (yes) sectionsRef.current?.selectSection(SECTION_ID);
  };

  const saveSettings =
    (sel: boolean) =>
    async (values: LeadershipSettingsForm): Promise<boolean> => {
      if (!settings) return false;
      const body = leadershipSettingsPatch(values, settings);
      if (Object.keys(body).length === 0) {
        form.reset(values);
        return true;
      }
      try {
        const saved = await patch.mutateAsync(body);
        form.reset(pickLeadershipFormValues(saved));
        return true;
      } catch (err) {
        log.error('Failed to save leadership settings', {
          organizationId,
          err,
        });
        const fieldErrors = leadershipSettingsFieldErrors(err);
        for (const [field, message] of fieldErrors) {
          form.setError(field, { message });
        }
        if (fieldErrors.length === 0) {
          toast.error(
            extractApiError(err) ?? 'Could not save leadership settings',
          );
        }
        select(sel);
        return false;
      }
    };

  const saveTraits =
    (sel: boolean) =>
    async (values: TraitForm): Promise<boolean> => {
      try {
        const saved = await put.mutateAsync(traitPutItems(values));
        traitForm.reset(traitFormValues(saved));
        return true;
      } catch (err) {
        log.error('Failed to save captain traits', { organizationId, err });
        const fieldErrors = traitFieldErrors(err);
        for (const [field, message] of fieldErrors) {
          traitForm.setError(field, { message });
        }
        if (fieldErrors.length === 0) {
          toast.error(extractApiError(err) ?? 'Could not save traits');
        }
        select(sel);
        return false;
      }
    };

  const onInvalid =
    (sel: boolean) =>
    (_errors: FieldErrors): void => {
      select(sel);
      toast.error('Please fix the highlighted fields');
    };

  const settingsDirty = form.formState.isDirty;
  const traitsDirty = traitForm.formState.isDirty;

  const unit: SettingsFormUnit = {
    id: SECTION_ID,
    isDirty: enabled && (settingsDirty || traitsDirty),
    save: async (opts) => {
      const sel = opts?.select !== false;
      let ok = true;
      if (settingsDirty) {
        ok = (await submitForm(form, saveSettings(sel), onInvalid(sel))) && ok;
      }
      if (traitsDirty) {
        ok =
          (await submitForm(traitForm, saveTraits(sel), onInvalid(sel))) && ok;
      }
      return ok;
    },
    discard: () => {
      if (settings) form.reset(pickLeadershipFormValues(settings));
      if (traits) traitForm.reset(traitFormValues(traits));
    },
  };

  const error = settingsQuery.error ?? traitsQuery.error;
  const content = (
    <section
      data-testid="org-settings-leadership"
      className="rounded-lg border border-border p-4 sm:p-6"
    >
      <h2 className="text-lg font-semibold">Leadership</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Points for captaining and how teammates rate their captain.
      </p>
      {(settingsQuery.isLoading || traitsQuery.isLoading) && (
        <div className="mt-4 flex flex-col gap-3">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}
      {error && (
        <p
          className="mt-4 text-sm text-destructive"
          data-testid="leadership-settings-error"
        >
          {extractApiError(error) ?? 'Failed to load leadership settings'}
        </p>
      )}
      {settings && traits && hydrated && (
        <div className="mt-4 flex flex-col gap-6">
          <LeadershipSettingsFields form={form} settings={settings} />
          <TraitEditor
            form={traitForm}
            organizationId={organizationId}
            access={access}
          />
        </div>
      )}
    </section>
  );

  return { content, unit };
}

interface NumberFieldSpec {
  name: NumberField;
  label: string;
  help: string;
  step: number;
}

const REVIEW_FIELDS: NumberFieldSpec[] = [
  {
    name: 'review_window_hours',
    label: 'Review window (hours)',
    help: 'How long teammates can rate their captain after the event (1 to 336).',
    step: 1,
  },
  {
    name: 'rating_min_reviewers',
    label: 'Minimum reviewers',
    help: 'A rating is shown only once this many teammates have reviewed (2 to 20).',
    step: 1,
  },
  {
    name: 'ranked_min_reviews',
    label: 'Reviews to be ranked',
    help: 'Captains with fewer reviews are listed as new (1 to 50).',
    step: 1,
  },
];

const RATING_FIELDS: NumberFieldSpec[] = [
  {
    name: 'prior_rating',
    label: 'Prior rating',
    help: 'Assumed rating for a captain with few reviews (1 to 5).',
    step: 0.1,
  },
  {
    name: 'prior_strength',
    label: 'Prior strength',
    help: 'How many reviews the prior counts as (0 to 20).',
    step: 0.1,
  },
  {
    name: 'half_life_days',
    label: 'Half-life (days)',
    help: 'A review this many days old counts half as much (7 to 730).',
    step: 1,
  },
  {
    name: 'max_age_days',
    label: 'Max age (days)',
    help: 'Older reviews and points are ignored (30 to 1825, at least the half-life).',
    step: 1,
  },
];

const TEST_ID_PREFIX = 'leadership-setting';

function LeadershipSettingsFields({
  form,
  settings,
}: {
  form: UseFormReturn<LeadershipSettingsForm>;
  settings: LeadershipSettings;
}) {
  const shared = {
    control: form.control,
    setValue: form.setValue,
    testIdPrefix: TEST_ID_PREFIX,
  };
  const numberSettings = (fields: NumberFieldSpec[]) =>
    fields.map((spec) => (
      <NumberSetting
        key={spec.name}
        {...shared}
        {...spec}
        defaultValue={settings.defaults[spec.name]}
      />
    ));
  return (
    <Form {...form}>
      <SettingsGroup title="Reviews">
        {numberSettings(REVIEW_FIELDS)}
      </SettingsGroup>
      <SettingsGroup title="Points">
        <NumberSetting
          {...shared}
          name="rating_max_points"
          label="Rating max points"
          help="Extra points a top-rated captain earns per event (0 to 100)."
          step={1}
          defaultValue={settings.defaults.rating_max_points}
        />
        {settings.points.map((kind) => (
          <NumberSetting
            key={kind.kind}
            {...shared}
            name={`points.${kind.kind}`}
            label={kind.label}
            help={`Points per event. Default ${kind.default}.`}
            step={1}
            defaultValue={kind.default}
          />
        ))}
      </SettingsGroup>
      <SettingsGroup title="Rating">
        {numberSettings(RATING_FIELDS)}
      </SettingsGroup>
      <SettingsGroup title="Visibility">
        <ToggleSetting
          {...shared}
          name="leaderboard_public"
          label="Public ranking"
          help="Members see the leadership ranking. When off, only staff see it; captains still see their own aggregates."
          defaultValue={settings.defaults.leaderboard_public}
        />
      </SettingsGroup>
    </Form>
  );
}

function TraitEditor({
  form,
  organizationId,
  access,
}: {
  form: UseFormReturn<TraitForm>;
  organizationId: number;
  access: ReturnType<typeof useOrgFeatureAccess>;
}) {
  const { fields, append, remove, swap } = useFieldArray({
    control: form.control,
    name: 'traits',
  });
  const rows = useWatch({ control: form.control, name: 'traits' }) ?? [];
  const deleteTrait = useDeleteTrait(organizationId, access);
  const activeCount = rows.filter((t) => t.active).length;
  const rootError =
    form.formState.errors.traits?.root?.message ??
    form.formState.errors.traits?.message;

  const addTrait = () => {
    const taken = new Set(rows.map((t) => t.key));
    append({
      key: slugifyTraitKey('trait', taken, TRAIT_KEY_MAX_LENGTH),
      label: '',
      active: activeCount < MAX_ACTIVE_TRAITS,
      saved: false,
    });
  };

  const onDelete = async (index: number) => {
    const row = rows[index];
    if (!row) return;
    if (!row.saved) {
      remove(index);
      return;
    }
    try {
      await deleteTrait.mutateAsync(row.key);
      remove(index);
      toast.success(`Deleted ${row.label}`);
    } catch (err) {
      log.warn('Trait delete refused', { organizationId, key: row.key, err });
      toast.error(refusalMessage(err));
    }
  };

  return (
    <Form {...form}>
      <fieldset
        className="flex flex-col gap-3"
        data-testid="leadership-trait-editor"
      >
        <legend className="mb-2 text-sm font-semibold">Traits</legend>
        <p className="text-sm text-muted-foreground">
          Teammates score each active trait from 1 to 5. Up to{' '}
          {MAX_ACTIVE_TRAITS} can be active. A trait that already has scores can
          only be deactivated.
        </p>
        <ol className="flex flex-col gap-3">
          {fields.map((item, index) => {
            const row = rows[index];
            return (
              <li
                key={item.id}
                data-testid={`leadership-trait-${index}`}
                className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-start"
              >
                <FormField
                  control={form.control}
                  name={`traits.${index}.label`}
                  render={({ field }) => (
                    <FormItem className="min-w-0 flex-1">
                      <FormLabel className="sr-only">
                        Trait {index + 1} name
                      </FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          maxLength={TRAIT_LABEL_MAX_LENGTH}
                          placeholder="Trait name"
                          data-testid={`leadership-trait-${index}-label`}
                          onChange={(e) => {
                            field.onChange(e);
                            if (row && !row.saved) {
                              const taken = new Set(
                                rows
                                  .filter((_, i) => i !== index)
                                  .map((t) => t.key),
                              );
                              form.setValue(
                                `traits.${index}.key`,
                                slugifyTraitKey(
                                  e.target.value,
                                  taken,
                                  TRAIT_KEY_MAX_LENGTH,
                                ),
                                { shouldDirty: true },
                              );
                            }
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                      {form.formState.errors.traits?.[index]?.key && (
                        <p className="text-sm text-destructive">
                          {form.formState.errors.traits[index]?.key?.message}
                        </p>
                      )}
                    </FormItem>
                  )}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <FormField
                    control={form.control}
                    name={`traits.${index}.active`}
                    render={({ field }) => (
                      <FormItem className="flex min-h-11 items-center gap-2">
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                            data-testid={`leadership-trait-${index}-active`}
                          />
                        </FormControl>
                        <FormLabel>Active</FormLabel>
                      </FormItem>
                    )}
                  />
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className="size-11"
                    aria-label={`Move ${row?.label || 'trait'} up`}
                    disabled={index === 0}
                    onClick={() => swap(index, index - 1)}
                  >
                    <ArrowUp />
                  </SecondaryButton>
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className="size-11"
                    aria-label={`Move ${row?.label || 'trait'} down`}
                    disabled={index === fields.length - 1}
                    onClick={() => swap(index, index + 1)}
                  >
                    <ArrowDown />
                  </SecondaryButton>
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className="size-11"
                    aria-label={`Delete ${row?.label || 'trait'}`}
                    data-testid={`leadership-trait-${index}-delete`}
                    disabled={deleteTrait.isPending}
                    onClick={() => void onDelete(index)}
                  >
                    <Trash2 />
                  </SecondaryButton>
                </div>
              </li>
            );
          })}
        </ol>
        {rootError && (
          <p className="text-sm text-destructive" role="alert">
            {rootError}
          </p>
        )}
        <div>
          <SecondaryButton
            type="button"
            className="min-h-11"
            data-testid="leadership-trait-add"
            onClick={addTrait}
          >
            <Plus data-icon="inline-start" />
            Add trait
          </SecondaryButton>
        </div>
      </fieldset>
    </Form>
  );
}
