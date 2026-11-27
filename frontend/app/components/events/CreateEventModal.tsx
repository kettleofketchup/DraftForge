import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import { getOrgEventDefaults } from '~/components/api/api';
import {
  lobbyPasswordPayload,
  refineLobbyPassword,
} from '~/components/lobby/password';
import {
  DraftSettingsFormSchema,
  draftSettingsFormToEventFields,
  draftSettingsToFormInput,
  eventFieldsToDraftSettingsFormInput,
} from '~/components/teamdraft/schemas';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import {
  useCreateEventMutation,
  useCreateEventRepeaterMutation,
} from '~/hooks/useEvent';
import { ApprovalConfigSection } from './ApprovalConfigSection';
import {
  openSignupsFromForm,
  toRepeaterCreatePayload,
} from './createEventPayload';
import {
  discordResetValues,
  EVENT_TEMPLATE_DEFAULTS,
  eventFieldTestIds,
  EventFormDialog,
  EventIdentityFields,
  EventLobbyFields,
  EventTournamentFields,
  OneOffScheduleFields,
  readyCheckResetValues,
  SeriesScheduleFields,
  TimezoneField,
} from './form';
import { ReadyCheckConfigSection } from './ReadyCheckConfigSection';
import {
  createEventInputSchema,
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  Frequency,
  localToUTC,
  READY_CHECK_CONFIG_DEFAULTS,
  READY_CHECK_PREFILL_KEYS,
  refineEventEnd,
  refineReadyCheck,
  SIGNUP_OPEN_DEFAULTS,
  type ReadyCheckFields,
} from './schemas';
import { ScopedDiscordConfigSection as DiscordConfigSection } from './ScopedDiscordConfigSection';
import { signupOpenFrom } from './signupOpen';
import { SERIES_IMMEDIATE_HELP, SignupOpenSection } from './SignupOpenSection';
import { signupRulesFrom } from './signupRules';
import { SignupRulesSection } from './SignupRulesSection';

const ids = eventFieldTestIds('event');

// Refined here, not on the shared schema, because createSeriesEventInputSchema .omit()s from it.
const createEventFormSchema = createEventInputSchema
  .merge(DraftSettingsFormSchema)
  .superRefine((values, ctx) => {
    refineLobbyPassword(values, ctx);
    if (!values.is_recurring) refineEventEnd(values, ctx);
    refineReadyCheck(values, ctx);
  });
type CreateEventFormOutput = z.output<typeof createEventFormSchema>;

interface CreateEventModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organizationId: number;
}

export function CreateEventModal({
  open,
  onOpenChange,
  organizationId,
}: CreateEventModalProps) {
  const createEventMutation = useCreateEventMutation();
  const createRepeater = useCreateEventRepeaterMutation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [defaultsApplied, setDefaultsApplied] = useState(false);

  const { data: orgDefaults, isLoading: orgDefaultsLoading } = useQuery({
    queryKey: ['org-event-defaults', organizationId],
    queryFn: () => getOrgEventDefaults(organizationId),
    staleTime: 5 * 60 * 1000,
  });

  // Hide form fields until orgDefaults are applied so the user can't start
  // typing before form.reset() fires and clobbers their input. The query
  // may also fail (network down, 5xx); in that case defaults stay at the
  // hardcoded useForm values and we show the form anyway after isLoading clears.
  const formReady =
    !orgDefaultsLoading && (orgDefaults == null || defaultsApplied);

  // RHF 7.55+ split the form's internal field-values type from the
  // transformed-on-submit type. @hookform/resolvers v5 + zod 4 always returns
  // Resolver<z.input<T>, _, z.output<T>>, so we need both generics aligned:
  // TFieldValues = z.input<S> (matches resolver's first arg)
  // TTransformedValues = z.output<S> (what onSubmit receives after parse)
  // For schemas without transforms these are structurally identical but
  // TypeScript still treats them as distinct due to zod 4 type branding.
  const form = useForm<
    z.input<typeof createEventFormSchema>,
    unknown,
    CreateEventFormOutput
  >({
    resolver: zodResolver(createEventFormSchema),
    defaultValues: {
      ...EVENT_TEMPLATE_DEFAULTS,
      scheduled_at: '',
      event_ends_at: '',
      organization: organizationId,
      timezone: '',
      discord_notify_new_events: true,
      ...DISCORD_CONFIG_DEFAULTS,
      ...DOTA_LOBBY_CONFIG_DEFAULTS,
      ...READY_CHECK_CONFIG_DEFAULTS,
      ...SIGNUP_OPEN_DEFAULTS,
      is_recurring: false,
      frequency: Frequency.WEEKLY,
      generate_days_ahead: 7,
      ...draftSettingsToFormInput(null),
    },
  });

  useEffect(() => {
    if (orgDefaults && open && !defaultsApplied) {
      form.reset({
        name: '',
        description: '',
        scheduled_at: '',
        event_ends_at: '',
        organization: organizationId,
        tournament_name: orgDefaults.tournament_name || '',
        tournament_league: orgDefaults.tournament_league ?? null,
        tournament_type: orgDefaults.tournament_type,
        game_type: orgDefaults.game_type,
        draft_type: orgDefaults.draft_type,
        game_mode: orgDefaults.game_mode,
        custom_game_name: orgDefaults.custom_game_name,
        captains_draft_time: orgDefaults.captains_draft_time,
        lobby_steam_league_id: orgDefaults.lobby_steam_league_id,
        people_per_team: orgDefaults.people_per_team,
        number_of_teams: orgDefaults.number_of_teams,
        timezone: orgDefaults.timezone,
        discord_notify_new_events: true,
        ...signupOpenFrom(orgDefaults),
        ...discordResetValues(orgDefaults),
        ...signupRulesFrom(orgDefaults),
        is_recurring: false,
        frequency: Frequency.WEEKLY,
        generate_days_ahead: 7,
        // Org defaults have no lobby settings: new events start with lobbies
        // off and a random password.
        ...DOTA_LOBBY_CONFIG_DEFAULTS,
        ...eventFieldsToDraftSettingsFormInput(orgDefaults),
        ...readyCheckResetValues(
          Object.fromEntries(
            READY_CHECK_PREFILL_KEYS.map((key) => [key, orgDefaults[key]]),
          ) as Partial<ReadyCheckFields>,
        ),
      });
      setDefaultsApplied(true);
    }
  }, [orgDefaults, open, defaultsApplied]);

  useEffect(() => {
    if (!open) setDefaultsApplied(false);
  }, [open]);

  const isRecurring = form.watch('is_recurring');

  async function onSubmit(data: CreateEventFormOutput) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const {
        is_recurring,
        frequency: _frequency,
        day_of_week: _dayOfWeek,
        time_of_day: _timeOfDay,
        starts_at: _startsAt,
        ends_at: _endsAt,
        generate_days_ahead: _generateDaysAhead,
        scheduled_at: rawScheduledAt,
        event_ends_at: rawEndsAt,
        discord_notify_new_events: _notifyNewEvents,
        dota_lobby_password_mode,
        dota_lobby_password,
        dota_lobby_password_saved: _saved,
        draft_timer_enabled,
        draft_grace_time_s,
        draft_reserve_time_s,
        draft_timeout_action,
        hero_timer_enabled,
        hero_grace_time_s,
        hero_reserve_time_s,
        ...rest
      } = data;
      const shared = {
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
        }),
      };
      // Convert naive datetime-local to UTC using the selected timezone
      const scheduled_at = rawScheduledAt
        ? localToUTC(rawScheduledAt, data.timezone)
        : rawScheduledAt;

      if (is_recurring) {
        await createRepeater.mutateAsync({
          ...shared,
          tournament_league: shared.tournament_league ?? null,
          ...toRepeaterCreatePayload(data),
        });
        toast.success('Recurring event created');
      } else {
        // Single events have no subscriber list — force signup_reminder
        // off regardless of org defaults so the backend validator (which
        // rejects discord_signup_reminder=true on single events) doesn't
        // 400 a submission whose default carried over from a repeater-
        // oriented org config.
        await createEventMutation.mutateAsync({
          payload: {
            ...shared,
            tournament_league: shared.tournament_league ?? null,
            scheduled_at,
            ends_at: rawEndsAt ? localToUTC(rawEndsAt, data.timezone) : null,
            discord_signup_reminder: false,
          },
          openSignups: openSignupsFromForm(data),
        });

        const modeMessages = {
          immediate: 'Event created with signups open',
          scheduled: 'Event created — signups open on schedule',
          manual: 'Event created',
        };
        toast.success(modeMessages[data.signup_open_mode]);
      }

      onOpenChange(false);
      form.reset();
      setDefaultsApplied(false);
    } catch {
      toast.error('Failed to create event');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <EventFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isRecurring ? 'Create Recurring Event' : 'Create Event'}
      submitLabel="Create"
      form={form}
      onValid={onSubmit}
      isSubmitting={isSubmitting || !formReady}
      tabTestIdPrefix="event-modal"
      data-testid="create-event-modal"
      loading={
        !formReady ? (
          <div
            className="py-12 text-center text-muted-foreground"
            data-testid="create-event-loading"
          >
            Loading defaults…
          </div>
        ) : undefined
      }
      tabs={[
        {
          value: 'event',
          content: (
            <>
              <EventIdentityFields
                control={form.control}
                testIds={ids}
                namePlaceholder="Weekly inhouse"
                descriptionPlaceholder="Event description"
              />

              <SignupOpenSection
                control={form.control}
                helpText={isRecurring ? SERIES_IMMEDIATE_HELP : undefined}
              />

              <FormField
                control={form.control}
                name="is_recurring"
                render={({ field }) => (
                  <FormItem className="flex items-start gap-3 space-y-0 rounded-md border border-border p-3">
                    <FormControl>
                      <input
                        data-testid="event-recurring-checkbox"
                        type="checkbox"
                        checked={field.value}
                        onChange={field.onChange}
                        className="mt-0.5 h-4 w-4 shrink-0 rounded border-border accent-primary"
                      />
                    </FormControl>
                    <div>
                      <FormLabel className="cursor-pointer text-sm font-medium">
                        Recurring Event (Event Repeater)
                      </FormLabel>
                      <FormDescription>
                        Automatically generates events on a schedule
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />

              {isRecurring ? (
                <SeriesScheduleFields
                  control={form.control}
                  testIdPrefix="event"
                  showStartsAt
                />
              ) : (
                <OneOffScheduleFields
                  control={form.control}
                  testIds={ids}
                  showEndsAt
                />
              )}

              <TimezoneField
                control={form.control}
                description="Inherited from org defaults"
                triggerTestId="event-timezone-input"
              />
            </>
          ),
        },
        {
          value: 'tournament',
          content: (
            <EventTournamentFields
              control={form.control}
              testIds={ids}
              league={{ organizationId }}
              tournamentName={{ placeholder: 'Inhouse #1' }}
              draftTypeTestId={ids.draftType}
            />
          ),
        },
        {
          value: 'lobby',
          content: (
            <EventLobbyFields
              control={form.control}
              scope={isRecurring ? 'series' : 'event'}
            />
          ),
        },
        {
          value: 'approval',
          content: (
            <div className="space-y-6">
              <ApprovalConfigSection control={form.control} />
              <SignupRulesSection control={form.control} />
            </div>
          ),
        },
        {
          value: 'discord',
          lazy: true,
          content: (
            <DiscordConfigSection
              control={form.control}
              isRepeater={isRecurring}
              organizationId={organizationId}
              previewContext={
                isRecurring
                  ? { type: 'new_repeater', organizationId }
                  : { type: 'new_event', organizationId }
              }
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
            />
          ),
        },
      ]}
    />
  );
}
