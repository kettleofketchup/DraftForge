import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';
import {
  createSeriesOneOffEvent,
  type EventRepeaterType,
} from '~/components/api/api';
import {
  lobbyPasswordPayload,
  refineLobbyPassword,
} from '~/components/lobby/password';
import { repeaterKeys } from '~/hooks/useEvent';
import { useRepeaterLobbyPassword } from '~/hooks/useLobbyPassword';
import { ApprovalConfigSection } from './ApprovalConfigSection';
import { DiscordConfigSection } from './DiscordConfigSection';
import {
  discordResetValues,
  dotaLobbyResetValues,
  eventFieldTestIds,
  EventFormDialog,
  EventIdentityFields,
  EventLobbyFields,
  EventTournamentFields,
  OneOffScheduleFields,
  readyCheckResetValues,
  TimezoneField,
  type EventFormDialogHandle,
} from './form';
import { ReadyCheckConfigSection } from './ReadyCheckConfigSection';
import {
  createSeriesEventInputSchema,
  localToUTC,
  refineReadyCheck,
  type CreateSeriesEventInput,
} from './schemas';
import { signupLineFrom } from './signupLine';
import { signupOpenFrom } from './signupOpen';
import { SignupOpenSection } from './SignupOpenSection';
import { signupRulesFrom } from './signupRules';
import { SignupRulesSection } from './SignupRulesSection';

const ids = eventFieldTestIds('one-off');

const createSeriesEventFormSchema =
  createSeriesEventInputSchema.superRefine(refineLobbyPassword);

interface CreateSeriesEventModalProps {
  repeater: EventRepeaterType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Adds a single "one-off" event to an existing series. Every config field is
 * prefilled from the series, so an untouched submit reproduces the series'
 * own settings at a caller-chosen instant.
 */
export function CreateSeriesEventModal({
  repeater,
  open,
  onOpenChange,
}: CreateSeriesEventModalProps) {
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const tabs = useRef<EventFormDialogHandle>(null);
  const schema = useMemo(
    () =>
      createSeriesEventFormSchema.superRefine((values, ctx) =>
        refineReadyCheck(values, ctx, {
          baseline: readyCheckResetValues(repeater),
        }),
      ),
    [repeater],
  );

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  const form = useForm<
    z.input<typeof createSeriesEventFormSchema>,
    unknown,
    CreateSeriesEventInput
  >({
    resolver: zodResolver(schema),
  });
  const { data: seriesPassword } = useRepeaterLobbyPassword(repeater.id, open);

  // Every key the schema keeps is named here; a partial reset leaves the
  // missing key `undefined` and zod rejects the submit with no visible error.
  useEffect(() => {
    if (!open) return;
    form.reset({
      name: repeater.name,
      description: repeater.description,
      scheduled_at: '',
      tournament_name: repeater.tournament_name,
      tournament_league: repeater.tournament_league ?? null,
      tournament_type: repeater.tournament_type,
      game_type: repeater.game_type,
      draft_type: repeater.draft_type,
      game_mode: repeater.game_mode,
      custom_game_name: repeater.custom_game_name,
      captains_draft_time: repeater.captains_draft_time,
      lobby_steam_league_id: repeater.lobby_steam_league_id,
      people_per_team: repeater.people_per_team,
      number_of_teams: repeater.number_of_teams,
      timezone: repeater.timezone,
      // A one-off has a repeater, so the subscriber reminder is valid here —
      // unlike CreateEventModal's repeater-less branch, which forces it off.
      ...discordResetValues(repeater),
      ...signupRulesFrom(repeater),
      ...signupLineFrom(repeater),
      ...signupOpenFrom(repeater),
      ...dotaLobbyResetValues(repeater, { savedFromMode: false }),
      ...readyCheckResetValues(repeater),
    });
  }, [repeater, open]);

  // Start from the series' fixed password, which is write-only on the series.
  useEffect(() => {
    if (
      open &&
      seriesPassword?.mode === 'fixed' &&
      !form.getFieldState('dota_lobby_password').isDirty
    ) {
      form.setValue('dota_lobby_password', seriesPassword.password ?? '');
    }
  }, [seriesPassword, open]);

  async function onSubmit(data: CreateSeriesEventInput) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const {
        dota_lobby_password_mode,
        dota_lobby_password,
        dota_lobby_password_saved: _saved,
        ...rest
      } = data;
      await createSeriesOneOffEvent(repeater.id, {
        ...rest,
        ...lobbyPasswordPayload({
          game_type: data.game_type,
          dota_lobby_password_mode,
          dota_lobby_password,
        }),
        tournament_league: data.tournament_league ?? null,
        open_signups: data.signup_open_mode === 'immediate',
        scheduled_at: data.scheduled_at
          ? localToUTC(data.scheduled_at, data.timezone)
          : data.scheduled_at,
      });
      toast.success('One-off event created');
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({
        queryKey: repeaterKeys.detail(repeater.id),
      });
      queryClient.invalidateQueries({ queryKey: repeaterKeys.lists() });
      onOpenChange(false);
    } catch (err) {
      const response = (
        err as {
          response?: { status?: number; data?: Record<string, unknown> };
        }
      ).response;
      if (response?.status === 409) {
        toast.error(
          String(response.data?.detail ?? 'That time is already taken'),
        );
      } else if (response?.data?.tournament_league) {
        const message = String(response.data.tournament_league);
        form.setError('tournament_league', { type: 'server', message });
        tabs.current?.selectTab('tournament');
        toast.error(message);
      } else {
        toast.error('Failed to create one-off event');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <EventFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add one-off event"
      description="Creates a single extra event in this series, inheriting its settings."
      submitLabel="Create"
      form={form}
      onValid={onSubmit}
      isSubmitting={isSubmitting}
      tabTestIdPrefix="one-off"
      tabRef={tabs}
      data-testid="create-one-off-modal"
      tabs={[
        {
          value: 'event',
          content: (
            <>
              <EventIdentityFields control={form.control} testIds={ids} />
              <OneOffScheduleFields
                control={form.control}
                testIds={ids}
                showEndsAt={false}
                scheduledDescription="Must not fall on one of this series' scheduled occurrences."
              />
              <TimezoneField
                control={form.control}
                description="Inherited from the series"
                triggerTestId="one-off-timezone-input"
              />
              <SignupOpenSection control={form.control} />
            </>
          ),
        },
        {
          value: 'tournament',
          content: (
            <EventTournamentFields
              control={form.control}
              testIds={ids}
              league={{ organizationId: repeater.organization }}
              draftTypeTestId={ids.draftType}
              draftSettings={false}
            />
          ),
        },
        {
          value: 'lobby',
          content: <EventLobbyFields control={form.control} scope="event" />,
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
              isRepeater
              showNotifyNewEvents={false}
              organizationId={repeater.organization}
              previewContext={{
                type: 'series_one_off',
                repeaterId: repeater.id,
              }}
            />
          ),
        },
        {
          value: 'ready',
          content: (
            <ReadyCheckConfigSection
              control={form.control}
              setValue={form.setValue}
              organizationId={repeater.organization}
            />
          ),
        },
      ]}
    />
  );
}
