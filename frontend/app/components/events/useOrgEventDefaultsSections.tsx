import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { useForm, type FieldErrors, type UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import { getOrgEventDefaults } from '~/components/api/api';
import type {
  SettingsDialogHandle,
  SettingsSection,
} from '~/components/patterns/SettingsDialog';
import {
  submitForm,
  type SettingsFormUnit,
} from '~/components/patterns/settingsSaveBar';
import {
  DraftSettingsFormSchema,
  draftSettingsFormToEventFields,
  draftSettingsToFormInput,
  eventFieldsToDraftSettingsFormInput,
} from '~/components/teamdraft/schemas';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Skeleton } from '~/components/ui/skeleton';
import { useUpdateOrgDefaultsMutation } from '~/hooks/useEvent';
import { extractApiError } from '~/lib/apiError';
import { DiscordConfigSection } from './DiscordConfigSection';
import {
  discordResetValues,
  EVENT_TAB_META,
  eventFieldTestIds,
  eventTabForField,
  EventTournamentFields,
  readyCheckResetValues,
  TimezoneField,
  type EventFormTabValue,
} from './form';
import { EVENT_SECTION_FIELDS } from './form/settingsFields';
import { ReadyCheckConfigSection } from './ReadyCheckConfigSection';
import {
  DISCORD_CONFIG_DEFAULTS,
  discordConfigSchema,
  READY_CHECK_CONFIG_DEFAULTS,
  readyCheckConfigSchema,
  refineReadyCheck,
  SIGNUP_OPEN_DEFAULTS,
  signupOpenSchema,
} from './schemas';
import { signupOpenFrom } from './signupOpen';
import { SignupOpenSection } from './SignupOpenSection';
import { signupRulesFrom } from './signupRules';
import { SignupRulesSection } from './SignupRulesSection';

const ids = eventFieldTestIds('org-defaults');

const GROUP = 'New Event Defaults';

type DefaultsTab = Extract<
  EventFormTabValue,
  'event' | 'tournament' | 'lobby' | 'discord' | 'ready'
>;

const TABS: readonly DefaultsTab[] = [
  'event',
  'tournament',
  'lobby',
  'discord',
  'ready',
];

const DEFAULTS_SECTIONS = TABS.map((t) => `defaults-${t}`);

const orgDefaultsSchema = z
  .object({
    // Tournament defaults
    tournament_name: z.string(),
    tournament_type: z.string(),
    game_type: z.number(),
    draft_type: z.string(),
    people_per_team: z.number().int().min(1),
    number_of_teams: z.number().int().min(2).nullable(),
    // EventConfig
    timezone: z.string(),
    game_mode: z.string(),
    max_players: z.number().int().min(1).nullable(),
    auto_approve: z.boolean(),
  })
  .merge(discordConfigSchema)
  .merge(DraftSettingsFormSchema)
  .merge(readyCheckConfigSchema)
  .merge(signupOpenSchema);

type OrgDefaultsInput = z.infer<typeof orgDefaultsSchema>;
type OrgDefaultsFormInput = z.input<typeof orgDefaultsSchema>;
type OrgDefaults = Awaited<ReturnType<typeof getOrgEventDefaults>>;

const FORM_DEFAULTS: OrgDefaultsFormInput = {
  tournament_name: '',
  tournament_type: 'double_elimination',
  game_type: 1,
  draft_type: 'shuffle',
  people_per_team: 5,
  number_of_teams: null,
  timezone: 'America/New_York',
  game_mode: 'normal',
  max_players: null,
  auto_approve: false,
  ...DISCORD_CONFIG_DEFAULTS,
  ...draftSettingsToFormInput(null),
  ...READY_CHECK_CONFIG_DEFAULTS,
  ...SIGNUP_OPEN_DEFAULTS,
};

function valuesFrom(defaults: OrgDefaults): OrgDefaultsFormInput {
  return {
    tournament_name: defaults.tournament_name || '',
    tournament_type: defaults.tournament_type,
    game_type: defaults.game_type,
    draft_type: defaults.draft_type,
    people_per_team: defaults.people_per_team,
    number_of_teams: defaults.number_of_teams,
    timezone: defaults.timezone,
    game_mode: defaults.game_mode,
    max_players: defaults.max_players,
    auto_approve: defaults.auto_approve,
    ...discordResetValues(defaults),
    ...signupRulesFrom(defaults),
    ...eventFieldsToDraftSettingsFormInput(defaults),
    ...readyCheckResetValues(defaults),
    ...signupOpenFrom(defaults),
  };
}

/**
 * The organization's new-event defaults as settings sections sharing one form,
 * exposed as a save-bar unit.
 */
export function useOrgEventDefaultsSections(
  organizationId: number,
  sectionsRef: RefObject<SettingsDialogHandle<string> | null>,
  enabled: boolean,
): { sections: SettingsSection[]; unit: SettingsFormUnit } {
  const mutation = useUpdateOrgDefaultsMutation(organizationId);

  const {
    data: defaults,
    isError,
    error,
  } = useQuery({
    queryKey: ['org-event-defaults', organizationId],
    queryFn: () => getOrgEventDefaults(organizationId),
    enabled: enabled && !!organizationId,
  });
  const schema = useMemo(
    () =>
      orgDefaultsSchema.superRefine((values, ctx) =>
        refineReadyCheck(values, ctx, {
          baseline: readyCheckResetValues(defaults),
          autoConfirmVisible: true,
        }),
      ),
    [defaults],
  );

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<OrgDefaultsFormInput, unknown, OrgDefaultsInput>({
    resolver: zodResolver(schema),
    defaultValues: FORM_DEFAULTS,
  });

  // Fields mount only after the form holds the loaded values: Radix Select's
  // hidden native select emits onChange('') when its value changes after mount.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (!defaults || !enabled) return;
    if (!form.formState.isDirty) form.reset(valuesFrom(defaults));
    setHydrated(true);
  }, [defaults, enabled, form]);

  const sectionFor = (field: string): string => {
    const mapped = sectionsRef.current?.sectionOfField(
      field,
      DEFAULTS_SECTIONS,
    );
    if (mapped) return mapped;
    const tab = eventTabForField(field);
    return (TABS as readonly string[]).includes(tab)
      ? `defaults-${tab}`
      : 'defaults-event';
  };

  async function onSubmit(data: OrgDefaultsInput): Promise<boolean> {
    if (!defaults) return false;
    const {
      draft_timer_enabled,
      draft_grace_time_s,
      draft_reserve_time_s,
      draft_timeout_action,
      hero_timer_enabled,
      hero_grace_time_s,
      hero_reserve_time_s,
      ...rest
    } = data;
    const payload = {
      ...rest,
      ...draftSettingsFormToEventFields({
        draft_timer_enabled,
        draft_grace_time_s,
        draft_reserve_time_s,
        draft_timeout_action,
        hero_timer_enabled,
        hero_grace_time_s,
        hero_reserve_time_s,
      }),
    };
    try {
      await mutation.mutateAsync({ id: defaults.id, data: payload });
      form.reset(data);
      return true;
    } catch {
      toast.error('Failed to update defaults');
      return false;
    }
  }

  const onInvalid =
    (select: boolean) => (errors: FieldErrors<OrgDefaultsFormInput>) => {
      const [key, error] = Object.entries(errors)[0] ?? [];
      if (!key) return;
      if (select) sectionsRef.current?.selectSection(sectionFor(key));
      toast.error('Please fix the highlighted fields', {
        description:
          typeof error?.message === 'string' ? error.message : undefined,
      });
    };

  const unit: SettingsFormUnit = {
    id: 'org-event-defaults',
    isDirty: form.formState.isDirty,
    save: (opts) =>
      submitForm(form, onSubmit, onInvalid(opts?.select !== false)),
    discard: () => form.reset(defaults ? valuesFrom(defaults) : FORM_DEFAULTS),
  };

  // Memoized: dirty and error changes re-render the dialog, not these fields.
  const ready = !!defaults && hydrated;
  const content = useMemo(
    () => defaultsContent({ form, organizationId, ready, isError, error }),
    [form, organizationId, ready, isError, error],
  );

  const errorKeys = Object.keys(form.formState.errors).filter(
    (k) => k !== 'root',
  );
  const sections: SettingsSection[] = TABS.map((tab) => {
    const value = `defaults-${tab}`;
    return {
      value,
      ...EVENT_TAB_META[tab],
      group: GROUP,
      lazy: tab === 'discord',
      fields: EVENT_SECTION_FIELDS[tab],
      content: content[tab],
      invalid: errorKeys.some((k) => sectionFor(k) === value),
    };
  });

  return { sections, unit };
}

function defaultsContent({
  form,
  organizationId,
  ready,
  isError,
  error,
}: {
  form: UseFormReturn<OrgDefaultsFormInput, unknown, OrgDefaultsInput>;
  organizationId: number;
  ready: boolean;
  isError: boolean;
  error: unknown;
}): Record<DefaultsTab, ReactNode> {
  const wrap = (children: ReactNode) => {
    if (isError) {
      return (
        <p
          className="text-sm text-destructive"
          data-testid="org-defaults-error"
        >
          {extractApiError(error) ?? 'Failed to load event defaults'}
        </p>
      );
    }
    return ready ? (
      <Form {...form}>
        <div className="flex flex-col gap-4">{children}</div>
      </Form>
    ) : (
      <Skeleton className="h-40 w-full" />
    );
  };

  return {
    event: wrap(
      <>
        <TimezoneField
          control={form.control}
          description="Default timezone for new events"
          triggerTestId="org-defaults-timezone-input"
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="max_players"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max Players</FormLabel>
                <FormControl>
                  <Input
                    data-testid="org-defaults-max-players-input"
                    type="number"
                    min={1}
                    value={field.value ?? ''}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10);
                      field.onChange(Number.isNaN(v) ? null : Math.max(1, v));
                    }}
                    placeholder="No limit"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="flex flex-col gap-3">
            <FormField
              control={form.control}
              name="auto_approve"
              render={({ field }) => (
                <FormItem className="flex items-center gap-3 space-y-0 rounded-md border border-border p-3">
                  <FormControl>
                    <input
                      data-testid="org-defaults-auto-approve-checkbox"
                      type="checkbox"
                      checked={field.value}
                      onChange={field.onChange}
                      className="h-4 w-4 rounded border-border accent-primary"
                    />
                  </FormControl>
                  <FormLabel className="cursor-pointer text-sm">
                    Auto-approve signups
                  </FormLabel>
                </FormItem>
              )}
            />
          </div>
        </div>
        <SignupOpenSection control={form.control} />
        <SignupRulesSection control={form.control} />
      </>,
    ),
    tournament: wrap(
      <EventTournamentFields
        control={form.control}
        testIds={ids}
        tournamentName={{
          label: 'Default Tournament Name',
          placeholder: 'Leave blank to use event name',
          description:
            'Pre-filled when creating new events. Can be overridden per event.',
        }}
        draftTypeTestId={ids.draftType}
        resetLobbyLeague={false}
      />,
    ),
    lobby: wrap(
      <FormField
        control={form.control}
        name="game_mode"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Game Mode</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger
                  data-testid="org-defaults-game-mode-select"
                  className="w-full"
                >
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value="normal">Normal</SelectItem>
                <SelectItem value="captains_mode">
                  Captain&apos;s Mode
                </SelectItem>
                <SelectItem value="turbo">Turbo</SelectItem>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />,
    ),
    discord: wrap(
      <DiscordConfigSection
        control={form.control}
        isRepeater={false}
        organizationId={organizationId}
      />,
    ),
    ready: wrap(
      <ReadyCheckConfigSection
        control={form.control}
        setValue={form.setValue}
        organizationId={organizationId}
        showAutoConfirm
      />,
    ),
  };
}
