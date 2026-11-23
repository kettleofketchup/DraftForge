import { zodResolver } from '@hookform/resolvers/zod';
import { ChevronDown, RotateCcw } from 'lucide-react';
import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import {
  useForm,
  useWatch,
  type Control,
  type FieldErrors,
  type PathValue,
  type UseFormReturn,
  type UseFormSetValue,
} from 'react-hook-form';
import { toast } from 'sonner';

import { useOrganization } from '~/components/organization/hooks/useOrganization';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import {
  submitForm,
  type SettingsFormUnit,
} from '~/components/patterns/settingsSaveBar';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Skeleton } from '~/components/ui/skeleton';
import { Switch } from '~/components/ui/switch';
import {
  CONDUCT_SETTINGS_FIELDS,
  ConductSettingsFormSchema,
  conductSettingsFieldErrors,
  isConductSettingsField,
  pickConductFormValues,
  useConductSettings,
  usePatchConductSettings,
  type ConductSettingsField,
  type ConductSettingsForm,
  type ConductSettingsValues,
} from '~/features/conduct';
import { useOrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';

const log = getLogger('ConductSection');

type NumberField = {
  [K in ConductSettingsField]: ConductSettingsValues[K] extends number
    ? K
    : never;
}[ConductSettingsField];
type ToggleField = {
  [K in ConductSettingsField]: ConductSettingsValues[K] extends boolean
    ? K
    : never;
}[ConductSettingsField];

const ENFORCEMENT_TOGGLES: readonly ToggleField[] = [
  'back_of_line_enabled',
  'require_approval_enabled',
  'block_enabled',
];

const ENFORCEMENT_FIELDS: ReadonlySet<ConductSettingsField> = new Set([
  ...ENFORCEMENT_TOGGLES,
  'back_of_line_below',
  'require_approval_below',
  'block_below',
  'enforce_on_new_members',
]);

const SECTION_ID = 'conduct';

export function useConductSection(
  organizationId: number,
  enabled: boolean,
  sectionsRef: RefObject<SettingsDialogHandle<string> | null>,
): { content: ReactNode; unit: SettingsFormUnit } {
  const { organization } = useOrganization(
    enabled ? organizationId : undefined,
  );
  const access = useOrgFeatureAccess(organization ?? undefined);
  const { data, isLoading, isError, error } = useConductSettings(
    organizationId,
    access,
    enabled,
  );
  const form = useForm<ConductSettingsForm>({
    resolver: zodResolver(ConductSettingsFormSchema),
    defaultValues: data ? pickConductFormValues(data) : undefined,
  });
  const [enforcementOpen, setEnforcementOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (!data) return;
    if (!form.formState.isDirty) form.reset(pickConductFormValues(data));
    if (hydrated) return;
    setEnforcementOpen(ENFORCEMENT_TOGGLES.some((f) => data[f]));
    setHydrated(true);
  }, [data, form, hydrated]);

  const mutation = usePatchConductSettings(organizationId, access);

  const revealEnforcement = (fields: Iterable<string>) => {
    for (const field of fields) {
      if (isConductSettingsField(field) && ENFORCEMENT_FIELDS.has(field)) {
        setEnforcementOpen(true);
        return;
      }
    }
  };

  const onSubmit =
    (select: boolean) =>
    async (values: ConductSettingsForm): Promise<boolean> => {
      const changes: Partial<ConductSettingsForm> = {};
      for (const field of CONDUCT_SETTINGS_FIELDS) {
        if (form.getFieldState(field).isDirty) {
          Object.assign(changes, { [field]: values[field] });
        }
      }
      try {
        const saved = await mutation.mutateAsync(changes);
        form.reset(pickConductFormValues(saved));
        return true;
      } catch (err) {
        log.error('Failed to save conduct settings', { organizationId, err });
        const fieldErrors = conductSettingsFieldErrors(err);
        for (const [field, message] of fieldErrors) {
          form.setError(field, { message });
        }
        revealEnforcement(fieldErrors.map(([field]) => field));
        if (fieldErrors.length === 0) {
          toast.error(
            extractApiError(err) ?? 'Could not save conduct settings',
          );
        } else if (select) {
          sectionsRef.current?.selectSection(SECTION_ID);
        }
        return false;
      }
    };

  const onInvalid =
    (select: boolean) =>
    (errors: FieldErrors<ConductSettingsForm>): void => {
      revealEnforcement(Object.keys(errors));
      if (select) sectionsRef.current?.selectSection(SECTION_ID);
      toast.error('Please fix the highlighted fields');
    };

  const unit: SettingsFormUnit = {
    id: SECTION_ID,
    isDirty: enabled && form.formState.isDirty,
    save: (opts) => {
      const select = opts?.select !== false;
      return submitForm(form, onSubmit(select), onInvalid(select));
    },
    discard: () => {
      if (data) form.reset(pickConductFormValues(data));
    },
  };

  // Memoized: dirty and error changes re-render the dialog, not these fields.
  const content = useMemo(
    () => (
      <section
        data-testid="org-settings-conduct"
        className="rounded-lg border border-border p-6"
      >
        <h2 className="text-lg font-semibold">Conduct</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          How attendance is scored, who sees the ranking, and whether a low show
          rate limits sign-ups.
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
            data-testid="conduct-settings-error"
          >
            {extractApiError(error) ?? 'Failed to load conduct settings'}
          </p>
        )}
        {data && hydrated && (
          <ConductSettingsFields
            form={form}
            defaults={data.defaults}
            enforcementOpen={enforcementOpen}
            onEnforcementOpenChange={setEnforcementOpen}
          />
        )}
      </section>
    ),
    [isLoading, isError, error, data, hydrated, form, enforcementOpen],
  );

  return { content, unit };
}

function ConductSettingsFields({
  form,
  defaults,
  enforcementOpen,
  onEnforcementOpenChange,
}: {
  form: UseFormReturn<ConductSettingsForm>;
  defaults: ConductSettingsValues;
  enforcementOpen: boolean;
  onEnforcementOpenChange: (open: boolean) => void;
}) {
  const control = form.control;
  const common = { control, defaults, setValue: form.setValue };

  return (
    <Form {...form}>
      <div className="mt-4 flex flex-col gap-6">
        <SettingsGroup title="Scoring">
          <NumberSetting
            {...common}
            name="prior_show_rate"
            label="Prior show rate"
            help="Assumed show rate for a member with little history (0.05 to 1)."
            step={0.01}
          />
          <NumberSetting
            {...common}
            name="prior_strength"
            label="Prior strength"
            help="How many events the prior counts as (0 to 20)."
            step={0.01}
          />
          <NumberSetting
            {...common}
            name="half_life_days"
            label="Half-life (days)"
            help="An event this many days old counts half as much (7 to 730)."
            step={1}
          />
          <NumberSetting
            {...common}
            name="max_age_days"
            label="Max age (days)"
            help="Events older than this are ignored (30 to 1095, at least the half-life)."
            step={1}
          />
          <NumberSetting
            {...common}
            name="min_events"
            label="Minimum events"
            help="Members with fewer counted events are listed as new (1 to 20)."
            step={1}
          />
        </SettingsGroup>

        <SettingsGroup title="Late cancel">
          <NumberSetting
            {...common}
            name="late_cancel_hours"
            label="Late cancel window (hours)"
            help="Cancelling this close to the start counts as a late cancel. 0 counts only cancels after the start (0 to 168)."
            step={1}
          />
          <NumberSetting
            {...common}
            name="late_cancel_weight"
            label="Late cancel weight"
            help="How much a late cancel counts against the show rate (0 to 1)."
            step={0.01}
          />
        </SettingsGroup>

        <SettingsGroup title="Visibility">
          <ToggleSetting
            {...common}
            name="leaderboard_public"
            label="Public ranking"
            help="Members see the attendance ranking. When off, only staff see it; members still see their own history."
          />
        </SettingsGroup>

        <Collapsible
          open={enforcementOpen}
          onOpenChange={onEnforcementOpenChange}
        >
          <fieldset
            data-testid="conduct-settings-enforcement"
            className="flex flex-col gap-4"
          >
            <legend className="flex w-full items-center justify-between gap-3 text-sm font-semibold">
              Enforcement
              <CollapsibleTrigger asChild>
                <SecondaryButton
                  type="button"
                  size="sm"
                  data-testid="conduct-settings-enforcement-toggle"
                  aria-label={
                    enforcementOpen ? 'Hide enforcement' : 'Show enforcement'
                  }
                >
                  {enforcementOpen ? 'Hide' : 'Show'}
                  <ChevronDown
                    data-icon="inline-end"
                    className={cn(
                      'transition-transform',
                      enforcementOpen && 'rotate-180',
                    )}
                  />
                </SecondaryButton>
              </CollapsibleTrigger>
            </legend>
            <p className="text-sm text-muted-foreground">
              Off by default. When several modes apply, the strictest wins.
            </p>
            <CollapsibleContent className="flex flex-col gap-4">
              <ToggleSetting
                {...common}
                name="back_of_line_enabled"
                label="Back of the line"
                help="Members below the threshold are promoted from the waitlist last."
              />
              <NumberSetting
                {...common}
                name="back_of_line_below"
                label="Back of the line below"
                help="Show rate threshold (0 to 1)."
                step={0.01}
              />
              <ToggleSetting
                {...common}
                name="require_approval_enabled"
                label="Require approval"
                help="Sign-ups from members below the threshold wait for staff approval."
              />
              <NumberSetting
                {...common}
                name="require_approval_below"
                label="Require approval below"
                help="Show rate threshold (0 to 1)."
                step={0.01}
              />
              <ToggleSetting
                {...common}
                name="block_enabled"
                label="Block self sign-up"
                help="Members below the threshold cannot sign themselves up; an organizer can still add them."
              />
              <NumberSetting
                {...common}
                name="block_below"
                label="Block below"
                help="Show rate threshold (0 to 1)."
                step={0.01}
              />
              <ToggleSetting
                {...common}
                name="enforce_on_new_members"
                label="Apply to new members"
                help="Also enforce on members with fewer than the minimum events."
              />
            </CollapsibleContent>
          </fieldset>
        </Collapsible>
      </div>
    </Form>
  );
}

function SettingsGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="flex flex-col gap-4">
      <legend className="mb-4 text-sm font-semibold">{title}</legend>
      {children}
    </fieldset>
  );
}

interface SettingProps<N extends ConductSettingsField> {
  control: Control<ConductSettingsForm>;
  defaults: ConductSettingsValues;
  setValue: UseFormSetValue<ConductSettingsForm>;
  name: N;
  label: string;
  help: string;
}

function DefaultControls<N extends ConductSettingsField>({
  control,
  defaults,
  setValue,
  name,
  label,
}: Omit<SettingProps<N>, 'help'>) {
  const value = useWatch({ control, name });
  const isDefault = value === defaults[name];
  return (
    <div className="flex items-center gap-2">
      {isDefault && (
        <Badge
          variant="outline"
          data-testid={`conduct-setting-${name}-default`}
        >
          Default
        </Badge>
      )}
      <SecondaryButton
        type="button"
        size="sm"
        data-testid={`conduct-setting-${name}-reset`}
        aria-label={`Reset ${label} to default`}
        disabled={isDefault}
        onClick={() =>
          setValue(name, defaults[name] as PathValue<ConductSettingsForm, N>, {
            shouldDirty: true,
            shouldValidate: true,
          })
        }
      >
        <RotateCcw data-icon="inline-start" />
        Reset
      </SecondaryButton>
    </div>
  );
}

function NumberSetting({
  step,
  ...props
}: SettingProps<NumberField> & { step: number }) {
  const { control, name, label, help } = props;
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FormLabel>{label}</FormLabel>
            <DefaultControls {...props} />
          </div>
          <FormControl>
            <Input
              type="number"
              inputMode="decimal"
              step={step}
              data-testid={`conduct-setting-${name}`}
              className="w-full sm:w-40"
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              value={Number.isNaN(field.value) ? '' : field.value}
              onChange={(e) =>
                field.onChange(
                  e.target.value === '' ? Number.NaN : Number(e.target.value),
                )
              }
            />
          </FormControl>
          <FormDescription>{help}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function ToggleSetting(props: SettingProps<ToggleField>) {
  const { control, name, label, help } = props;
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-3">
              <FormControl>
                <Switch
                  data-testid={`conduct-setting-${name}`}
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  onBlur={field.onBlur}
                  ref={field.ref}
                />
              </FormControl>
              <FormLabel>{label}</FormLabel>
            </div>
            <DefaultControls {...props} />
          </div>
          <FormDescription>{help}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
