import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';
import { createSeriesOneOffEvent, type EventRepeaterType } from '~/components/api/api';
import { GAME_TYPE } from '~/components/game/constants';
import { LeagueCombobox } from '~/components/league/LeagueCombobox';
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
import { ApprovalConfigSection } from './ApprovalConfigSection';
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { LobbyConfigSection } from './LobbyConfigSection';
import {
  COMMON_TIMEZONES,
  createSeriesEventInputSchema,
  GameMode,
  localToUTC,
  type CreateSeriesEventInput,
} from './schemas';

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

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  const form = useForm<
    z.input<typeof createSeriesEventInputSchema>,
    unknown,
    CreateSeriesEventInput
  >({
    resolver: zodResolver(createSeriesEventInputSchema),
  });

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
      open_signups: false,
      discord_create_event: repeater.discord_create_event,
      discord_sync_signups: repeater.discord_sync_signups,
      discord_event_title: repeater.discord_event_title,
      discord_event_description: repeater.discord_event_description,
      discord_event_info: repeater.discord_event_info,
      // A one-off has a repeater, so the subscriber reminder is valid here —
      // unlike CreateEventModal's repeater-less branch, which forces it off.
      discord_signup_reminder: repeater.discord_signup_reminder,
      discord_signup_reminder_hours: repeater.discord_signup_reminder_hours,
      discord_confirm_attendance: repeater.discord_confirm_attendance,
      discord_confirm_attendance_hours: repeater.discord_confirm_attendance_hours,
      discord_profile_reminder: repeater.discord_profile_reminder,
      discord_profile_reminder_hours: repeater.discord_profile_reminder_hours,
      discord_mark_interested: repeater.discord_mark_interested,
      discord_post_signups: repeater.discord_post_signups,
      discord_post_signups_channel_id: repeater.discord_post_signups_channel_id,
      discord_announcement: repeater.discord_announcement,
      discord_announcement_channel_id: repeater.discord_announcement_channel_id,
      discord_announcement_hours: repeater.discord_announcement_hours,
      discord_announcement_role_ids: repeater.discord_announcement_role_ids ?? [],
      discord_signup_role_ids: repeater.discord_signup_role_ids ?? [],
      discord_require_rank_screenshot: repeater.discord_require_rank_screenshot ?? false,
      discord_require_battlecup_screenshot:
        repeater.discord_require_battlecup_screenshot ?? false,
      min_mmr: repeater.min_mmr ?? null,
      allow_active_mmr: repeater.allow_active_mmr ?? true,
      allow_previous_rank: repeater.allow_previous_rank ?? true,
      allow_battlecup_rating: repeater.allow_battlecup_rating ?? true,
      require_steam_id: repeater.require_steam_id ?? false,
      require_mmr_verified: repeater.require_mmr_verified ?? false,
      require_profile_complete: repeater.require_profile_complete ?? false,
    });
  }, [repeater, open]);

  async function onSubmit(data: CreateSeriesEventInput) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await createSeriesOneOffEvent(repeater.id, {
        ...data,
        tournament_league: data.tournament_league ?? null,
        scheduled_at: data.scheduled_at
          ? localToUTC(data.scheduled_at, data.timezone)
          : data.scheduled_at,
      });
      toast.success('One-off event created');
      queryClient.invalidateQueries({ queryKey: ['repeater-events', repeater.id] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['repeater', repeater.id] });
      onOpenChange(false);
    } catch (err) {
      const response = (
        err as { response?: { status?: number; data?: Record<string, unknown> } }
      ).response;
      if (response?.status === 409) {
        toast.error(String(response.data?.detail ?? 'That time is already taken'));
      } else if (response?.data?.tournament_league) {
        toast.error(String(response.data.tournament_league));
      } else {
        toast.error('Failed to create one-off event');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add one-off event"
      description="Creates a single extra event in this series, inheriting its settings."
      submitLabel="Create"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="lg"
      data-testid="create-one-off-modal"
    >
      <Form {...form}>
        <Tabs defaultValue="event">
          <TabsList className="w-full">
            <TabsTrigger value="event" data-testid="one-off-tab-event">
              Event
            </TabsTrigger>
            <TabsTrigger value="approval" data-testid="one-off-tab-approval">
              <ShieldCheck className="h-4 w-4" />
              Approval
            </TabsTrigger>
            <TabsTrigger value="discord" data-testid="one-off-tab-discord">
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
                    <Input data-testid="one-off-name-input" {...field} />
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
                    <Textarea data-testid="one-off-description-input" rows={2} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="scheduled_at"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Scheduled Date &amp; Time</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="one-off-scheduled-input"
                      type="datetime-local"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Must not fall on one of this series&apos; scheduled occurrences.
                  </FormDescription>
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
                      <SelectTrigger data-testid="one-off-timezone-input" className="w-full">
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
                  <FormDescription>Inherited from the series</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="open_signups"
              render={({ field }) => (
                <FormItem className="flex items-center gap-3 rounded-md border border-border p-3">
                  <FormControl>
                    <input
                      data-testid="one-off-open-signups-checkbox"
                      type="checkbox"
                      checked={!!field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      className="h-4 w-4 rounded border-border accent-primary"
                    />
                  </FormControl>
                  <div>
                    <FormLabel>Open signups immediately</FormLabel>
                    <FormDescription>
                      Otherwise the event stays upcoming until you open signups by hand.
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="tournament_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tournament Name</FormLabel>
                    <FormControl>
                      <Input data-testid="one-off-tournament-name-input" {...field} />
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
                        organizationId={repeater.organization}
                        value={field.value ?? null}
                        onChange={(v) => field.onChange(v)}
                        invalid={!!fieldState.error}
                        triggerTestId="one-off-league-select"
                        itemTestIdPrefix="one-off-league-option-"
                        searchTestId="one-off-league-search"
                        clearTestId="one-off-league-clear"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

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
                          gameType === GAME_TYPE.DEADLOCK ? 6 : 5
                        );
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
                        <SelectTrigger data-testid="one-off-game-select" className="w-full">
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
                        data-testid="one-off-people-per-team-input"
                        type="number"
                        min={1}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 1)}
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
                          data-testid="one-off-max-teams-input"
                          type="number"
                          min={2}
                          disabled={field.value === null}
                          value={field.value ?? ''}
                          onChange={(e) => {
                            const v = parseInt(e.target.value, 10);
                            field.onChange(Number.isNaN(v) ? null : Math.max(2, v));
                          }}
                          placeholder="No limit"
                        />
                      </FormControl>
                      <label className="flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap cursor-pointer">
                        <input
                          data-testid="one-off-unlimited-checkbox"
                          type="checkbox"
                          checked={field.value === null}
                          onChange={(e) => field.onChange(e.target.checked ? null : 2)}
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
                        <SelectTrigger data-testid="one-off-draft-select" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="shuffle">Shuffle — MMR point buy draft</SelectItem>
                        <SelectItem value="snake">
                          Snake Draft — Captains pick in snake order
                        </SelectItem>
                        <SelectItem value="normal">Manual — Manually assign players</SelectItem>
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
                        <SelectTrigger data-testid="one-off-bracket-select" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="double_elimination">Double Elimination</SelectItem>
                        <SelectItem value="single_elimination">Single Elimination</SelectItem>
                        <SelectItem value="swiss">Swiss Bracket</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <LobbyConfigSection control={form.control} watch={form.watch} />
          </TabsContent>

          <TabsContent value="approval" className="space-y-4">
            <ApprovalConfigSection control={form.control} watch={form.watch} />
          </TabsContent>

          <TabsContent value="discord" className="space-y-4">
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater
              showNotifyNewEvents={false}
              organizationId={repeater.organization}
            />
          </TabsContent>
        </Tabs>
      </Form>
    </FormDialog>
  );
}
