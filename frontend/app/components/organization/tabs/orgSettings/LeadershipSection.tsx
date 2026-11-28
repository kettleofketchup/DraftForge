import { zodResolver } from '@hookform/resolvers/zod';
import { TriangleAlert } from 'lucide-react';
import { useEffect, useState, type ReactNode, type RefObject } from 'react';
import {
  useForm,
  useWatch,
  type FieldErrors,
  type UseFormReturn,
} from 'react-hook-form';
import { toast } from 'sonner';

import { useOrganization } from '~/components/organization/hooks/useOrganization';
import { LeadershipTraitEditor } from '~/components/organization/tabs/orgSettings/LeadershipTraitEditor';
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
import { Alert, AlertDescription } from '~/components/ui/alert';
import { Form } from '~/components/ui/form';
import { Skeleton } from '~/components/ui/skeleton';
import {
  leadershipAccess,
  LeadershipSettingsFormSchema,
  TraitFormSchema,
  useLeadershipSettings,
  useLeadershipTraits,
  usePatchLeadershipSettings,
  usePutTraits,
  type LeadershipSettings,
  type LeadershipSettingsForm,
  type TraitForm,
} from '~/features/leadership';
import { refusalCode, refusalMessage } from '~/features/leadership/errors';
import {
  leadershipSettingsFieldErrors,
  leadershipSettingsPatch,
  pickLeadershipFormValues,
} from '~/features/leadership/settingsForm';
import {
  toTraitForm,
  toTraitPut,
  traitFieldErrors,
} from '~/features/leadership/traitForm';
import { useOrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

const log = getLogger('LeadershipSection');

const SECTION_ID = 'leadership';

type NumberField = Exclude<
  keyof LeadershipSettingsForm,
  | 'leaderboard_public'
  | 'require_staff_release'
  | 'auto_release_after_hours'
  | 'review_dms_enabled'
  | 'captain_feedback_visible'
  | 'points'
>;

const SELF_RELEASE_CODE = 'would_release_own_results';

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
  const traitsQuery = useLeadershipTraits(
    organizationId,
    access,
    enabled && leadershipAccess(access).canManage,
  );
  const settings = settingsQuery.data;
  const traits = traitsQuery.data;

  const form = useForm<LeadershipSettingsForm>({
    resolver: zodResolver(LeadershipSettingsFormSchema),
    defaultValues: settings ? pickLeadershipFormValues(settings) : undefined,
  });
  const traitForm = useForm<TraitForm>({
    resolver: zodResolver(TraitFormSchema),
    defaultValues: traits ? toTraitForm(traits) : undefined,
  });
  const [hydrated, setHydrated] = useState(false);
  const [releaseRefusal, setReleaseRefusal] = useState<string | null>(null);

  useEffect(() => {
    if (settings && !form.formState.isDirty) {
      form.reset(pickLeadershipFormValues(settings));
    }
  }, [settings, form]);
  useEffect(() => {
    if (traits && !traitForm.formState.isDirty) {
      traitForm.reset(toTraitForm(traits));
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
      setReleaseRefusal(null);
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
        if (refusalCode(err) === SELF_RELEASE_CODE) {
          setReleaseRefusal(refusalMessage(err, 'settings'));
          select(sel);
          return false;
        }
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
        const saved = await put.mutateAsync(toTraitPut(values));
        traitForm.reset(toTraitForm(saved));
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
      const [settingsValid, traitsValid] = await Promise.all([
        form.trigger(),
        traitForm.trigger(),
      ]);
      if (!settingsValid || !traitsValid) {
        onInvalid(sel)({});
        return false;
      }
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
      setReleaseRefusal(null);
      if (settings) form.reset(pickLeadershipFormValues(settings));
      if (traits) traitForm.reset(toTraitForm(traits));
    },
  };

  const error = settingsQuery.error ?? traitsQuery.error;
  const content = (
    <section
      data-testid="org-settings-leadership"
      className="rounded-lg border border-border p-6"
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
          <LeadershipSettingsFields
            form={form}
            settings={settings}
            releaseRefusal={releaseRefusal}
          />
          <LeadershipTraitEditor
            form={traitForm}
            orgId={organizationId}
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

const REVIEW_WINDOW_FIELD: NumberFieldSpec = {
  name: 'review_window_hours',
  label: 'Review window (hours)',
  help: 'How long teammates can rate their captain after the event (1 to 336).',
  step: 1,
};

const REVIEW_FIELDS: NumberFieldSpec[] = [
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

function ReleaseWarning({
  testId,
  children,
}: {
  testId: string;
  children: ReactNode;
}) {
  return (
    <Alert className="border-warning/40 text-warning" data-testid={testId}>
      <TriangleAlert />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}

function ReleaseSettings({
  form,
  settings,
  releaseRefusal,
  shared,
}: {
  form: UseFormReturn<LeadershipSettingsForm>;
  settings: LeadershipSettings;
  releaseRefusal: string | null;
  shared: {
    control: UseFormReturn<LeadershipSettingsForm>['control'];
    setValue: UseFormReturn<LeadershipSettingsForm>['setValue'];
    testIdPrefix: string;
  };
}) {
  const gateOn = useWatch({
    control: form.control,
    name: 'require_staff_release',
  });
  const hours = useWatch({
    control: form.control,
    name: 'auto_release_after_hours',
  });
  return (
    <SettingsGroup title="Release">
      <ToggleSetting
        {...shared}
        name="require_staff_release"
        label="Require staff release"
        help="Results stay hidden after the window closes until a moderator releases them."
        defaultValue={settings.defaults.require_staff_release}
      />
      <NumberSetting
        {...shared}
        name="auto_release_after_hours"
        label="Auto-release after (hours)"
        help="Leave empty to wait for a moderator (a fallback is recommended). Shortening this releases waiting results now."
        step={1}
        nullable
        disabled={!gateOn}
        defaultValue={settings.defaults.auto_release_after_hours}
      />
      {settings.require_staff_release && !gateOn && (
        <ReleaseWarning testId="leadership-release-off-warning">
          Turning this off releases every result that is waiting.
        </ReleaseWarning>
      )}
      {gateOn && hours == null && (
        <ReleaseWarning testId="leadership-release-fallback-warning">
          {settings.moderator_count === 1
            ? 'You are the only moderator. Set a fallback, or your own results are never released.'
            : "Moderators cannot release their own results. With no fallback, a moderator's results wait for another moderator or site staff."}
        </ReleaseWarning>
      )}
      {releaseRefusal && (
        <Alert variant="destructive" data-testid="leadership-release-refusal">
          <TriangleAlert />
          <AlertDescription>{releaseRefusal}</AlertDescription>
        </Alert>
      )}
    </SettingsGroup>
  );
}

function LeadershipSettingsFields({
  form,
  settings,
  releaseRefusal,
}: {
  form: UseFormReturn<LeadershipSettingsForm>;
  settings: LeadershipSettings;
  releaseRefusal: string | null;
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
        {numberSettings([REVIEW_WINDOW_FIELD])}
        <ToggleSetting
          {...shared}
          name="review_dms_enabled"
          label="Send review DMs"
          help="When a review window opens, each teammate gets a Discord DM with buttons to score their captain. Applies to windows opened after you turn it on. Re-closing an event doesn't send new DMs."
          defaultValue={settings.defaults.review_dms_enabled}
        />
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
      <ReleaseSettings
        form={form}
        settings={settings}
        releaseRefusal={releaseRefusal}
        shared={shared}
      />
      <SettingsGroup title="Visibility">
        <ToggleSetting
          {...shared}
          name="leaderboard_public"
          label="Public ranking"
          help="Members see the leadership ranking. When off, only staff see it."
          defaultValue={settings.defaults.leaderboard_public}
        />
        <ToggleSetting
          {...shared}
          name="captain_feedback_visible"
          label="Show captains their feedback"
          help="When off, captains can't see their own rating, trait scores or rating points. Staff and the ranking are unaffected."
          defaultValue={settings.defaults.captain_feedback_visible}
        />
      </SettingsGroup>
    </Form>
  );
}
