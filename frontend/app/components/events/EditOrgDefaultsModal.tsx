import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
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
  eventFieldTestIds,
  EventFormDialog,
  EventTournamentFields,
  TimezoneField,
} from './form';
import { DISCORD_CONFIG_DEFAULTS, discordConfigSchema } from './schemas';

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
    auto_confirm: z.boolean(),
  })
  .merge(discordConfigSchema)
  .merge(DraftSettingsFormSchema);

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

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<
    z.input<typeof orgDefaultsSchema>,
    unknown,
    OrgDefaultsInput
  >({
    resolver: zodResolver(orgDefaultsSchema),
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
      auto_confirm: false,
      ...DISCORD_CONFIG_DEFAULTS,
      ...draftSettingsToFormInput(null),
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
        auto_confirm: defaults.auto_confirm,
        discord_create_event: defaults.discord_create_event,
        discord_sync_signups: defaults.discord_sync_signups,
        discord_event_title: defaults.discord_event_title,
        discord_event_description: defaults.discord_event_description,
        discord_event_info: defaults.discord_event_info,
        discord_signup_reminder: defaults.discord_signup_reminder,
        discord_signup_reminder_hours: defaults.discord_signup_reminder_hours,
        discord_confirm_attendance: defaults.discord_confirm_attendance,
        discord_confirm_attendance_hours:
          defaults.discord_confirm_attendance_hours,
        discord_profile_reminder: defaults.discord_profile_reminder,
        discord_profile_reminder_hours: defaults.discord_profile_reminder_hours,
        discord_mark_interested: defaults.discord_mark_interested,
        discord_post_signups: defaults.discord_post_signups,
        discord_post_signups_channel_id:
          defaults.discord_post_signups_channel_id,
        discord_announcement: defaults.discord_announcement,
        discord_announcement_channel_id:
          defaults.discord_announcement_channel_id,
        discord_announcement_hours: defaults.discord_announcement_hours,
        discord_require_rank_screenshot:
          defaults.discord_require_rank_screenshot ?? false,
        discord_require_battlecup_screenshot:
          defaults.discord_require_battlecup_screenshot ?? false,
        min_mmr: defaults.min_mmr ?? null,
        allow_active_mmr: defaults.allow_active_mmr ?? true,
        allow_previous_rank: defaults.allow_previous_rank ?? true,
        allow_battlecup_rating: defaults.allow_battlecup_rating ?? true,
        // Approval rule flags — see CreateEventModal for the regression note.
        require_steam_id: defaults.require_steam_id ?? false,
        require_mmr_verified: defaults.require_mmr_verified ?? false,
        require_profile_complete: defaults.require_profile_complete ?? false,
        ...eventFieldsToDraftSettingsFormInput(defaults),
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
                      [
                        'auto_confirm',
                        'Auto-confirm signups',
                        'org-defaults-auto-confirm-checkbox',
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
      ]}
    />
  );
}
