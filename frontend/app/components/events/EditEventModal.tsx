import { zodResolver } from '@hookform/resolvers/zod';
import { ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import { GAME_TYPE } from '~/components/game/constants';
import { LeagueCombobox } from '~/components/league/LeagueCombobox';
import { lobbyPasswordPayload } from '~/components/lobby/password';
import { FormDialog } from '~/components/ui/dialogs';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Textarea } from '~/components/ui/textarea';
import { useUpdateEventMutation } from '~/hooks/useEvent';
import {
  useEventLobbyPassword,
  useRegenerateEventLobbyPassword,
} from '~/hooks/useLobbyPassword';
import { ApprovalConfigSection } from './ApprovalConfigSection';
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { DotaLobbyEventSettings } from './DotaLobbyEventSettings';
import { LobbyConfigSection } from './LobbyConfigSection';
import type { EditEventFormInput, EventType } from './schemas';
import {
  COMMON_TIMEZONES,
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  editEventFormSchema,
  GameMode,
  localToUTC,
  utcToLocalInput,
} from './schemas';

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

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<
    z.input<typeof editEventFormSchema>,
    unknown,
    EditEventFormInput
  >({
    resolver: zodResolver(editEventFormSchema),
    defaultValues: {
      name: '',
      description: '',
      scheduled_at: '',
      event_ends_at: '',
      tournament_name: '',
      tournament_type: 'double_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      game_mode: 'normal',
      custom_game_name: '',
      captains_draft_time: 10,
      lobby_steam_league_id: null,
      people_per_team: 5,
      number_of_teams: null,
      timezone: '',
      tournament_league: null, // overridden by useEffect when event loads
      ...DISCORD_CONFIG_DEFAULTS,
      ...DOTA_LOBBY_CONFIG_DEFAULTS,
    },
  });

  // Reset form when event changes
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
        draft_type: event.draft_type,
        game_mode: event.game_mode,
        custom_game_name: event.custom_game_name,
        captains_draft_time: event.captains_draft_time,
        lobby_steam_league_id: event.lobby_steam_league_id,
        people_per_team: event.people_per_team,
        number_of_teams: event.number_of_teams || null,
        tournament_league: event.tournament_league,
        discord_create_event: event.discord_create_event,
        discord_sync_signups: event.discord_sync_signups,
        discord_event_title: event.discord_event_title,
        discord_event_description: event.discord_event_description,
        discord_event_info: event.discord_event_info,
        // Single events have no subscriber list — force signup_reminder off
        // for them so the superRefine in eventSchema doesn't reject.
        // Repeater-occurrence events keep the persisted value.
        discord_signup_reminder:
          event.event_repeater != null ? event.discord_signup_reminder : false,
        discord_signup_reminder_hours:
          event.event_repeater != null
            ? event.discord_signup_reminder_hours
            : 24,
        discord_confirm_attendance: event.discord_confirm_attendance,
        discord_confirm_attendance_hours:
          event.discord_confirm_attendance_hours,
        discord_profile_reminder: event.discord_profile_reminder,
        discord_profile_reminder_hours: event.discord_profile_reminder_hours,
        discord_mark_interested: event.discord_mark_interested,
        discord_post_signups: event.discord_post_signups,
        discord_post_signups_channel_id: event.discord_post_signups_channel_id,
        discord_announcement: event.discord_announcement,
        discord_announcement_channel_id: event.discord_announcement_channel_id,
        discord_announcement_hours: event.discord_announcement_hours,
        discord_require_rank_screenshot: event.discord_require_rank_screenshot,
        discord_require_battlecup_screenshot:
          event.discord_require_battlecup_screenshot,
        min_mmr: event.min_mmr ?? null,
        allow_active_mmr: event.allow_active_mmr,
        allow_previous_rank: event.allow_previous_rank,
        allow_battlecup_rating: event.allow_battlecup_rating,
        // Approval rule flags — see CreateEventModal for the regression note.
        require_steam_id: event.require_steam_id ?? false,
        require_mmr_verified: event.require_mmr_verified ?? false,
        require_profile_complete: event.require_profile_complete ?? false,
        dota_lobby_mode: event.dota_lobby_mode,
        dota_lobby_launch: event.dota_lobby_launch,
        dota_lobby_region: event.dota_lobby_region,
        discord_send_lobby_info: event.discord_send_lobby_info,
        dota_lobby_password_mode: event.dota_lobby_password_mode,
        dota_lobby_password: '',
        dota_lobby_password_saved: event.dota_lobby_password_mode === 'fixed',
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
        ...rest
      } = data;
      const payload = {
        ...rest,
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
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit Event"
      submitLabel="Save"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="lg"
      data-testid="edit-event-modal"
    >
      <Form {...form}>
        <Tabs defaultValue="event">
          <TabsList className="w-full">
            <TabsTrigger value="event">Event</TabsTrigger>
            <TabsTrigger value="approval">
              <ShieldCheck className="h-4 w-4" />
              Approval
            </TabsTrigger>
            <TabsTrigger value="discord">
              <DiscordIcon className="h-4 w-4" />
              Discord
            </TabsTrigger>
          </TabsList>

          <TabsContent value="event" className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Event Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea rows={2} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="scheduled_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Scheduled Date & Time</FormLabel>
                    <FormControl>
                      <Input
                        data-testid="event-scheduled-input"
                        type="datetime-local"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="event_ends_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>End Date & Time (optional)</FormLabel>
                    <FormControl>
                      <Input
                        data-testid="event-end-datetime-input"
                        type="datetime-local"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="timezone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Timezone</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select timezone" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {COMMON_TIMEZONES.map((tz) => (
                          <SelectItem key={tz} value={tz}>
                            {tz.replace(/_/g, ' ')}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="tournament_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tournament Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="tournament_league"
              render={({ field, fieldState }) => (
                <FormItem>
                  <FormLabel>League</FormLabel>
                  <FormControl>
                    <LeagueCombobox
                      organizationId={event?.organization}
                      value={field.value ?? null}
                      onChange={(v) => field.onChange(v)}
                      invalid={!!fieldState.error}
                      triggerTestId="edit-event-tournament-league"
                      itemTestIdPrefix="league-option-"
                      searchTestId="edit-event-league-search"
                      clearTestId="edit-event-league-clear"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <FormField
                control={form.control}
                name="game_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Game</FormLabel>
                    <Select
                      onValueChange={(val) => {
                        const gameType = parseInt(val, 10);
                        field.onChange(gameType);
                        form.setValue(
                          'people_per_team',
                          gameType === GAME_TYPE.DEADLOCK ? 6 : 5,
                        );
                        // Reset Dota-only fields when switching to non-Dota
                        const currentMode = form.getValues('game_mode');
                        if (gameType !== GAME_TYPE.DOTA2) {
                          if (
                            currentMode === GameMode.CAPTAINS_MODE ||
                            currentMode === GameMode.TURBO
                          ) {
                            form.setValue('game_mode', GameMode.NORMAL);
                          }
                          form.setValue('lobby_steam_league_id', null);
                        }
                      }}
                      value={field.value?.toString()}
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="1">Dota 2</SelectItem>
                        <SelectItem value="2">Deadlock</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="people_per_team"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>People Per Team</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        {...field}
                        onChange={(e) =>
                          field.onChange(parseInt(e.target.value, 10) || 1)
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="number_of_teams"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max Teams</FormLabel>
                    <div className="flex items-center gap-2">
                      <FormControl>
                        <Input
                          type="number"
                          min={2}
                          disabled={field.value === null}
                          value={field.value ?? ''}
                          onChange={(e) => {
                            const v = parseInt(e.target.value, 10);
                            field.onChange(
                              Number.isNaN(v) ? null : Math.max(2, v),
                            );
                          }}
                          placeholder="No limit"
                        />
                      </FormControl>
                      <label className="flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap cursor-pointer">
                        <input
                          type="checkbox"
                          checked={field.value === null}
                          onChange={(e) =>
                            field.onChange(e.target.checked ? null : 2)
                          }
                          className="h-3.5 w-3.5 rounded border-border accent-primary"
                        />
                        Unlimited
                      </label>
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="draft_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Draft Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="shuffle">
                          Shuffle — MMR point buy draft
                        </SelectItem>
                        <SelectItem value="snake">
                          Snake Draft — Captains pick in snake order
                        </SelectItem>
                        <SelectItem value="normal">
                          Manual — Manually assign players
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="tournament_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Bracket Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="double_elimination">
                          Double Elimination
                        </SelectItem>
                        <SelectItem value="single_elimination">
                          Single Elimination
                        </SelectItem>
                        <SelectItem value="swiss">Swiss Bracket</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Double elimination works best with teams that are a power
                      of 2 (2, 4, 8, 16)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <LobbyConfigSection control={form.control} watch={form.watch} />
            <DotaLobbyEventSettings
              control={form.control}
              watch={form.watch}
              scope="event"
              saved={savedPassword}
              followsSeries={
                event?.event_repeater != null && !event?.is_off_schedule
              }
              onRegenerate={onRegenerate}
              regenerating={regenerate.isPending}
            />
          </TabsContent>

          <TabsContent value="approval" className="space-y-4">
            <ApprovalConfigSection control={form.control} watch={form.watch} />
          </TabsContent>

          <TabsContent value="discord" className="space-y-4">
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater={event?.event_repeater != null}
              organizationId={event?.organization ?? 0}
            />
          </TabsContent>
        </Tabs>
      </Form>
    </FormDialog>
  );
}
