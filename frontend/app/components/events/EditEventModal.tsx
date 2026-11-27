import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import { lobbyPasswordPayload } from '~/components/lobby/password';
import {
  draftSettingsFormToEventFields,
  draftSettingsToFormInput,
  eventFieldsToDraftSettingsFormInput,
  toDraftStyle,
} from '~/components/teamdraft/schemas';
import { useUpdateEventMutation } from '~/hooks/useEvent';
import {
  useEventLobbyPassword,
  useRegenerateEventLobbyPassword,
} from '~/hooks/useLobbyPassword';
import { ApprovalConfigSection } from './ApprovalConfigSection';
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
  OneOffScheduleFields,
  readyCheckResetValues,
  TimezoneField,
} from './form';
import { ReadyCheckConfigSection } from './ReadyCheckConfigSection';
import type { EditEventFormInput, EventType } from './schemas';
import {
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  editEventFormSchema,
  EventState,
  localToUTC,
  READY_CHECK_CONFIG_DEFAULTS,
  refineReadyCheck,
  SIGNUP_OPEN_DEFAULTS,
  utcToLocalInput,
} from './schemas';
import { signupLineFrom } from './signupLine';
import { SignupLineConfigSection } from './SignupLineConfigSection';
import { signupOpenFrom } from './signupOpen';
import {
  SERIES_EVENT_POLICY_HELP,
  SignupOpenSection,
} from './SignupOpenSection';
import { signupRulesFrom } from './signupRules';
import { SignupRulesSection } from './SignupRulesSection';

const ids = eventFieldTestIds('edit-event', {
  scheduled: 'event-scheduled-input',
  endsAt: 'event-end-datetime-input',
  league: {
    trigger: 'edit-event-tournament-league',
    itemPrefix: 'league-option-',
  },
});

function formatOpenAt(iso: string | null, timeZone: string): string {
  if (!iso) return 'Not scheduled';
  try {
    return `${new Date(iso).toLocaleString(undefined, { timeZone })} (${timeZone})`;
  } catch {
    return new Date(iso).toLocaleString();
  }
}

interface EditEventModalProps {
  event: EventType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditEventModal({
  event,
  open,
  onOpenChange,
}: EditEventModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const mutation = useUpdateEventMutation(event?.id ?? 0);
  const { data: savedPassword } = useEventLobbyPassword(event?.id, open);
  const regenerate = useRegenerateEventLobbyPassword(event?.id);
  const schema = useMemo(
    () =>
      editEventFormSchema.superRefine((values, ctx) =>
        refineReadyCheck(values, ctx, {
          baseline: readyCheckResetValues(event),
        }),
      ),
    [event],
  );

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<
    z.input<typeof editEventFormSchema>,
    unknown,
    EditEventFormInput
  >({
    resolver: zodResolver(schema),
    defaultValues: {
      ...EVENT_TEMPLATE_DEFAULTS,
      scheduled_at: '',
      event_ends_at: '',
      timezone: '',
      tournament_league: null, // overridden by useEffect when event loads
      ...DISCORD_CONFIG_DEFAULTS,
      ...DOTA_LOBBY_CONFIG_DEFAULTS,
      ...READY_CHECK_CONFIG_DEFAULTS,
      ...draftSettingsToFormInput(null),
      ...SIGNUP_OPEN_DEFAULTS,
    },
  });

  useEffect(() => {
    if (event && open) {
      form.reset({
        name: event.name,
        description: event.description,
        scheduled_at: utcToLocalInput(event.scheduled_at, event.timezone),
        event_ends_at: utcToLocalInput(event.ends_at, event.timezone),
        timezone: event.timezone,
        tournament_name: event.tournament_name,
        tournament_type: event.tournament_type,
        game_type: event.game_type,
        draft_type: toDraftStyle(event.draft_type),
        ...eventFieldsToDraftSettingsFormInput(event),
        game_mode: event.game_mode,
        custom_game_name: event.custom_game_name,
        captains_draft_time: event.captains_draft_time,
        lobby_steam_league_id: event.lobby_steam_league_id,
        people_per_team: event.people_per_team,
        number_of_teams: event.number_of_teams || null,
        tournament_league: event.tournament_league,
        ...discordResetValues(event),
        ...signupRulesFrom(event),
        ...signupLineFrom(event),
        // Single events have no subscriber list — force signup_reminder off
        // for them so the superRefine in eventSchema doesn't reject.
        // Repeater-occurrence events keep the persisted value.
        discord_signup_reminder:
          event.event_repeater != null ? event.discord_signup_reminder : false,
        discord_signup_reminder_hours:
          event.event_repeater != null
            ? event.discord_signup_reminder_hours
            : 24,
        ...signupOpenFrom(event),
        ...dotaLobbyResetValues(event, { savedFromMode: true }),
        ...readyCheckResetValues(event),
      });
    }
  }, [event, open]);

  // The fixed password is write-only on the event: prefill it from the
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
  }, [savedPassword, event, open]);

  async function onRegenerate() {
    try {
      await regenerate.mutateAsync();
      toast.success('New lobby password generated');
    } catch {
      toast.error('Could not regenerate the lobby password');
    }
  }

  const policyEditable = event?.state === EventState.UPCOMING;
  const followsSeries =
    event?.event_repeater != null && !event?.is_off_schedule;

  async function onSubmit(data: EditEventFormInput) {
    if (isSubmitting || !event) return;
    setIsSubmitting(true);
    try {
      // Convert naive datetime-local to UTC using selected timezone
      const {
        dota_lobby_password_mode,
        dota_lobby_password,
        dota_lobby_password_saved,
        event_ends_at,
        draft_timer_enabled,
        draft_grace_time_s,
        draft_reserve_time_s,
        draft_timeout_action,
        hero_timer_enabled,
        hero_grace_time_s,
        hero_reserve_time_s,
        signup_open_mode,
        signups_open_hours_before,
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
        ...(policyEditable && { signup_open_mode, signups_open_hours_before }),
        ...lobbyPasswordPayload({
          game_type: data.game_type,
          dota_lobby_password_mode,
          dota_lobby_password,
          dota_lobby_password_saved,
        }),
        scheduled_at: data.scheduled_at
          ? localToUTC(data.scheduled_at, data.timezone)
          : data.scheduled_at,
        ends_at: event_ends_at
          ? localToUTC(event_ends_at, data.timezone)
          : null,
      };
      const result = await mutation.mutateAsync(payload);
      if (result._warning) {
        toast.warning(result._warning);
      } else {
        toast.success('Event updated');
      }
      onOpenChange(false);
    } catch {
      toast.error('Failed to update event');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <EventFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit Event"
      submitLabel="Save"
      form={form}
      onValid={onSubmit}
      isSubmitting={isSubmitting}
      tabTestIdPrefix="edit-event"
      data-testid="edit-event-modal"
      tabs={[
        {
          value: 'event',
          content: (
            <>
              <EventIdentityFields control={form.control} testIds={ids} />
              <OneOffScheduleFields
                control={form.control}
                testIds={ids}
                showEndsAt
              />
              <TimezoneField
                control={form.control}
                triggerTestId={ids.timezone}
              />

              <SignupOpenSection
                control={form.control}
                disabled={!policyEditable}
                helpText={followsSeries ? SERIES_EVENT_POLICY_HELP : undefined}
              />
              <p className="text-sm text-muted-foreground">
                Signups open:{' '}
                <span className="text-foreground" data-testid="signup-open-at">
                  {formatOpenAt(
                    event?.signups_open_at ?? null,
                    event?.timezone ?? 'UTC',
                  )}
                </span>
              </p>
            </>
          ),
        },
        {
          value: 'tournament',
          content: (
            <EventTournamentFields
              control={form.control}
              testIds={ids}
              league={{ organizationId: event?.organization }}
            />
          ),
        },
        {
          value: 'lobby',
          content: (
            <EventLobbyFields
              control={form.control}
              scope="event"
              saved={savedPassword}
              followsSeries={followsSeries}
              onRegenerate={onRegenerate}
              regenerating={regenerate.isPending}
            />
          ),
        },
        {
          value: 'approval',
          content: (
            <div className="space-y-6">
              <ApprovalConfigSection control={form.control} />
              <SignupRulesSection control={form.control} />
              <SignupLineConfigSection control={form.control} />
            </div>
          ),
        },
        {
          value: 'discord',
          lazy: true,
          content: (
            <DiscordConfigSection
              control={form.control}
              isRepeater={event?.event_repeater != null}
              showNotifyNewEvents={false}
              organizationId={event?.organization ?? 0}
              previewContext={
                event ? { type: 'event', eventId: event.id } : undefined
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
              organizationId={event?.organization ?? null}
            />
          ),
        },
      ]}
    />
  );
}
