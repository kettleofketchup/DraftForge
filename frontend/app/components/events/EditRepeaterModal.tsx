import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import type { EventRepeaterType } from '~/components/api/api';
import {
  lobbyPasswordPayload,
  refineLobbyPassword,
} from '~/components/lobby/password';
import {
  DraftSettingsFormSchema,
  draftSettingsFormToEventFields,
  draftSettingsToFormInput,
  eventFieldsToDraftSettingsFormInput,
  toDraftStyle,
} from '~/components/teamdraft/schemas';
import { useUpdateEventRepeaterMutation } from '~/hooks/useEvent';
import { useRepeaterLobbyPassword } from '~/hooks/useLobbyPassword';
import { DiscordConfigSection } from './DiscordConfigSection';
import {
  discordResetValues,
  dotaLobbyResetValues,
  EVENT_TEMPLATE_DEFAULTS,
  eventFieldTestIds,
  EventFormDialog,
  EventIdentityFields,
  EventLobbyFields,
  EventTournamentFields,
  SeriesScheduleFields,
  TimezoneField,
} from './form';
import {
  DISCORD_CONFIG_DEFAULTS,
  discordConfigSchema,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  dotaLobbyConfigSchema,
  eventIdentitySchema,
  eventTemplateSchema,
  Frequency,
} from './schemas';

const editRepeaterSchema = eventIdentitySchema
  .merge(eventTemplateSchema)
  .extend({
    frequency: z.string(),
    day_of_week: z.number().int().min(0).max(6).optional(),
    time_of_day: z.string(),
    ends_at: z.string().optional(),
    generate_days_ahead: z.number().int().min(1),
    discord_notify_new_events: z.boolean(),
  })
  .merge(discordConfigSchema)
  .merge(dotaLobbyConfigSchema)
  .merge(DraftSettingsFormSchema)
  .superRefine(refineLobbyPassword);

const ids = eventFieldTestIds('edit-series');

type EditRepeaterInput = z.infer<typeof editRepeaterSchema>;

interface EditRepeaterModalProps {
  repeater: EventRepeaterType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditRepeaterModal({
  repeater,
  open,
  onOpenChange,
}: EditRepeaterModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const mutation = useUpdateEventRepeaterMutation(repeater?.id ?? 0);
  const { data: savedPassword } = useRepeaterLobbyPassword(repeater?.id, open);

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<
    z.input<typeof editRepeaterSchema>,
    unknown,
    EditRepeaterInput
  >({
    resolver: zodResolver(editRepeaterSchema),
    defaultValues: {
      ...EVENT_TEMPLATE_DEFAULTS,
      frequency: Frequency.WEEKLY,
      day_of_week: undefined,
      time_of_day: '19:00',
      ends_at: '',
      generate_days_ahead: 7,
      timezone: '',
      discord_notify_new_events: true,
      ...DISCORD_CONFIG_DEFAULTS,
      ...DOTA_LOBBY_CONFIG_DEFAULTS,
      ...draftSettingsToFormInput(null),
    },
  });

  useEffect(() => {
    if (repeater && open) {
      form.reset({
        name: repeater.name,
        description: repeater.description,
        tournament_name: repeater.tournament_name,
        tournament_type: repeater.tournament_type,
        game_type: repeater.game_type,
        draft_type: toDraftStyle(repeater.draft_type),
        ...eventFieldsToDraftSettingsFormInput(repeater),
        game_mode: repeater.game_mode,
        custom_game_name: repeater.custom_game_name,
        captains_draft_time: repeater.captains_draft_time,
        lobby_steam_league_id: repeater.lobby_steam_league_id,
        people_per_team: repeater.people_per_team,
        number_of_teams: repeater.number_of_teams,
        frequency: repeater.frequency,
        day_of_week: repeater.day_of_week ?? undefined,
        time_of_day: repeater.time_of_day?.slice(0, 5) ?? '19:00',
        ends_at: repeater.ends_at ?? '',
        generate_days_ahead: repeater.generate_days_ahead,
        timezone: repeater.timezone,
        discord_notify_new_events: repeater.discord_notify_new_events,
        ...discordResetValues(repeater),
        ...dotaLobbyResetValues(repeater, { savedFromMode: true }),
      });
    }
  }, [repeater, open]);

  // The fixed password is write-only on the series: prefill it from the
  // staff-only endpoint unless staff already typed one. Runs after the reset
  // above, so a reset never leaves it empty. Left empty (the endpoint failed
  // or is still loading), the saved password is kept.
  useEffect(() => {
    if (
      open &&
      savedPassword?.mode === 'fixed' &&
      !form.getFieldState('dota_lobby_password').isDirty
    ) {
      form.setValue('dota_lobby_password', savedPassword.password ?? '');
    }
  }, [savedPassword, repeater, open]);

  async function onSubmit(data: EditRepeaterInput) {
    if (isSubmitting || !repeater) return;
    setIsSubmitting(true);
    try {
      const {
        dota_lobby_password_mode,
        dota_lobby_password,
        dota_lobby_password_saved,
        draft_timer_enabled,
        draft_grace_time_s,
        draft_reserve_time_s,
        draft_timeout_action,
        hero_timer_enabled,
        hero_grace_time_s,
        hero_reserve_time_s,
        ...rest
      } = data;
      await mutation.mutateAsync({
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
        ...lobbyPasswordPayload({
          game_type: data.game_type,
          dota_lobby_password_mode,
          dota_lobby_password,
          dota_lobby_password_saved,
        }),
        day_of_week: data.day_of_week ?? null,
        ends_at: data.ends_at || null,
      });
      toast.success('Series updated — upcoming events have been synced');
      onOpenChange(false);
    } catch {
      toast.error('Failed to update repeating event');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <EventFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit Repeating Event"
      description="Changes apply to future generated events only."
      submitLabel="Save"
      form={form}
      onValid={onSubmit}
      isSubmitting={isSubmitting}
      tabTestIdPrefix="edit-series"
      data-testid="edit-series-modal"
      tabs={[
        {
          value: 'event',
          content: (
            <>
              <EventIdentityFields control={form.control} testIds={ids} />
              <SeriesScheduleFields
                control={form.control}
                testIdPrefix="edit-series"
                showStartsAt={false}
              />
              <TimezoneField
                control={form.control}
                triggerTestId={ids.timezone}
              />
            </>
          ),
        },
        {
          value: 'tournament',
          content: (
            <EventTournamentFields control={form.control} testIds={ids} />
          ),
        },
        {
          value: 'lobby',
          content: (
            <EventLobbyFields
              control={form.control}
              watch={form.watch}
              scope="series"
              saved={savedPassword}
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
              isRepeater={true}
              organizationId={repeater?.organization ?? 0}
            />
          ),
        },
      ]}
    />
  );
}
