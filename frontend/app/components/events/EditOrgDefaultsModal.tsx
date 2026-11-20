import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import { getOrgEventDefaults } from '~/components/api/api';
import {
  DraftSettingsFormSchema,
  draftSettingsFormToEventFields,
  draftSettingsToFormInput,
  eventFieldsToDraftSettingsFormInput,
} from '~/components/teamdraft/schemas';
import {
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
import { useUpdateOrgDefaultsMutation } from '~/hooks/useEvent';
import { DiscordConfigSection } from './DiscordConfigSection';
import {
  discordResetValues,
  eventFieldTestIds,
  EventFormDialog,
  EventTournamentFields,
  readyCheckResetValues,
  TimezoneField,
} from './form';
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

interface EditOrgDefaultsModalProps {
  organizationId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditOrgDefaultsModal({
  organizationId,
  open,
  onOpenChange,
}: EditOrgDefaultsModalProps) {
  const mutation = useUpdateOrgDefaultsMutation(organizationId);

  const { data: defaults } = useQuery({
    queryKey: ['org-event-defaults', organizationId],
    queryFn: () => getOrgEventDefaults(organizationId),
    enabled: open && !!organizationId,
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
  const form = useForm<
    z.input<typeof orgDefaultsSchema>,
    unknown,
    OrgDefaultsInput
  >({
    resolver: zodResolver(schema),
    defaultValues: {
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
    },
  });

  useEffect(() => {
    if (defaults && open) {
      form.reset({
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
      });
    }
  }, [defaults, open]);

  async function onSubmit(data: OrgDefaultsInput) {
    if (!defaults) return;
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
      toast.success('Event defaults updated');
      onOpenChange(false);
    } catch {
      toast.error('Failed to update defaults');
    }
  }

  return (
    <EventFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Organization Event Defaults"
      description="These defaults are applied when creating new events."
      submitLabel="Save Defaults"
      form={form}
      onValid={onSubmit}
      isSubmitting={mutation.isPending}
      tabTestIdPrefix="org-defaults"
      data-testid="org-defaults-modal"
      tabs={[
        {
          value: 'event',
          content: (
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
                            field.onChange(
                              Number.isNaN(v) ? null : Math.max(1, v),
                            );
                          }}
                          placeholder="No limit"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex flex-col gap-3">
                  {(
                    [
                      [
                        'auto_approve',
                        'Auto-approve signups',
                        'org-defaults-auto-approve-checkbox',
                      ],
                    ] as const
                  ).map(([name, label, testId]) => (
                    <FormField
                      key={name}
                      control={form.control}
                      name={name}
                      render={({ field }) => (
                        <FormItem className="flex items-center gap-3 space-y-0 rounded-md border border-border p-3">
                          <FormControl>
                            <input
                              data-testid={testId}
                              type="checkbox"
                              checked={field.value}
                              onChange={field.onChange}
                              className="h-4 w-4 rounded border-border accent-primary"
                            />
                          </FormControl>
                          <FormLabel className="cursor-pointer text-sm">
                            {label}
                          </FormLabel>
                        </FormItem>
                      )}
                    />
                  ))}
                </div>
              </div>
              <SignupOpenSection control={form.control} />
              <SignupRulesSection control={form.control} />
            </>
          ),
        },
        {
          value: 'tournament',
          content: (
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
            />
          ),
        },
        {
          value: 'lobby',
          content: (
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
            />
          ),
        },
        {
          value: 'discord',
          lazy: true,
          content: (
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater={false}
              organizationId={organizationId}
            />
          ),
        },
        {
          value: 'ready',
          content: (
            <ReadyCheckConfigSection
              control={form.control}
              setValue={form.setValue}
              organizationId={organizationId}
              showAutoConfirm
            />
          ),
        },
      ]}
    />
  );
}
