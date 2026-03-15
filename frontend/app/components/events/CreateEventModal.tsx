import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { createEvent, createEventRepeater, getOrgEventDefaults } from '~/components/api/api';
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
import { Textarea } from '~/components/ui/textarea';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { LobbyConfigSection } from './LobbyConfigSection';
import { createEventInputSchema, GameType, GameMode, Frequency, FREQUENCY_LABELS, DAY_LABELS, DISCORD_CONFIG_DEFAULTS, type CreateEventInput } from './schemas';
import type { LeagueType } from '~/components/league';

interface CreateEventModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organizationId: number;
  leagues: LeagueType[];
}

export function CreateEventModal({
  open,
  onOpenChange,
  organizationId,
  leagues,
}: CreateEventModalProps) {
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [defaultsApplied, setDefaultsApplied] = useState(false);

  const { data: orgDefaults } = useQuery({
    queryKey: ['org-event-defaults', organizationId],
    queryFn: () => getOrgEventDefaults(organizationId),
    staleTime: 5 * 60 * 1000,
  });

  const form = useForm<CreateEventInput>({
    resolver: zodResolver(createEventInputSchema),
    defaultValues: {
      name: '',
      description: '',
      scheduled_at: '',
      organization: organizationId,
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
      discord_notify_new_events: true,
      ...DISCORD_CONFIG_DEFAULTS,
      is_recurring: false,
      frequency: Frequency.WEEKLY,
      generate_days_ahead: 7,
    },
  });

  useEffect(() => {
    if (orgDefaults && open && !defaultsApplied) {
      form.reset({
        name: '',
        description: '',
        scheduled_at: '',
        organization: organizationId,
        tournament_name: orgDefaults.tournament_name || '',
        tournament_league: orgDefaults.tournament_league ?? undefined,
        tournament_type: orgDefaults.tournament_type,
        game_type: orgDefaults.game_type,
        draft_type: orgDefaults.draft_type,
        game_mode: orgDefaults.game_mode,
        custom_game_name: orgDefaults.custom_game_name,
        captains_draft_time: orgDefaults.captains_draft_time,
        lobby_steam_league_id: orgDefaults.lobby_steam_league_id,
        people_per_team: orgDefaults.people_per_team,
        number_of_teams: orgDefaults.number_of_teams,
        discord_notify_new_events: true,
        discord_create_event: orgDefaults.discord_create_event,
        discord_sync_signups: orgDefaults.discord_sync_signups,
        discord_event_title: orgDefaults.discord_event_title,
        discord_event_description: orgDefaults.discord_event_description,
        discord_event_info: orgDefaults.discord_event_info,
        discord_signup_reminder: orgDefaults.discord_signup_reminder,
        discord_signup_reminder_hours: orgDefaults.discord_signup_reminder_hours,
        discord_confirm_attendance: orgDefaults.discord_confirm_attendance,
        discord_confirm_attendance_hours: orgDefaults.discord_confirm_attendance_hours,
        discord_profile_reminder: orgDefaults.discord_profile_reminder,
        discord_profile_reminder_hours: orgDefaults.discord_profile_reminder_hours,
        discord_mark_interested: orgDefaults.discord_mark_interested,
        discord_post_signups: orgDefaults.discord_post_signups,
        discord_post_signups_channel_id: orgDefaults.discord_post_signups_channel_id,
        discord_announcement: orgDefaults.discord_announcement,
        discord_announcement_channel_id: orgDefaults.discord_announcement_channel_id,
        discord_announcement_hours: orgDefaults.discord_announcement_hours,
        is_recurring: false,
        frequency: Frequency.WEEKLY,
        generate_days_ahead: 7,
      });
      setDefaultsApplied(true);
    }
  }, [orgDefaults, open, defaultsApplied]);

  useEffect(() => {
    if (!open) setDefaultsApplied(false);
  }, [open]);

  const isRecurring = form.watch('is_recurring');

  async function onSubmit(data: CreateEventInput) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const { is_recurring, frequency, day_of_week, time_of_day, starts_at, ends_at, generate_days_ahead, scheduled_at, discord_notify_new_events, ...shared } = data;

      if (is_recurring) {
        await createEventRepeater({
          ...shared,
          discord_notify_new_events: discord_notify_new_events ?? false,
          frequency,
          day_of_week: day_of_week ?? null,
          time_of_day: time_of_day || '19:00',
          starts_at: starts_at || new Date().toISOString().slice(0, 10),
          ends_at: ends_at || null,
          generate_days_ahead,
        });
        toast.success('Recurring event created');
      } else {
        await createEvent({
          ...shared,
          scheduled_at,
        });
        toast.success('Event created');
      }

      queryClient.invalidateQueries({ queryKey: ['events'] });
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
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isRecurring ? 'Create Recurring Event' : 'Create Event'}
      submitLabel="Create"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="lg"
    >
      <Form {...form}>
        <Tabs defaultValue="event">
          <TabsList className="w-full">
            <TabsTrigger value="event">Event</TabsTrigger>
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
                <Input data-testid="event-name-input" placeholder="Weekly inhouse" {...field} />
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
                <Textarea data-testid="event-description-input" placeholder="Event description" rows={2} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="tournament_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Tournament Name</FormLabel>
                <FormControl>
                  <Input data-testid="event-tournament-name-input" placeholder="Inhouse #1" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="tournament_league"
            render={({ field }) => (
              <FormItem>
                <FormLabel>League</FormLabel>
                <Select
                  onValueChange={(val) => field.onChange(parseInt(val, 10))}
                  value={field.value?.toString()}
                >
                  <FormControl>
                    <SelectTrigger data-testid="event-league-select" className="w-full">
                      <SelectValue placeholder="Select league" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {leagues.map((league) => (
                      <SelectItem key={league.pk} value={String(league.pk)}>
                        {league.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                    // Update people_per_team default when switching games
                    form.setValue('people_per_team', gameType === GameType.DEADLOCK ? 6 : 5);
                    // Reset Dota-only fields when switching to non-Dota
                    const currentMode = form.getValues('game_mode');
                    if (gameType !== GameType.DOTA2) {
                      if (currentMode === GameMode.CAPTAINS_MODE || currentMode === GameMode.TURBO) {
                        form.setValue('game_mode', GameMode.NORMAL);
                      }
                      form.setValue('lobby_steam_league_id', null);
                    }
                  }}
                  value={field.value?.toString()}
                >
                  <FormControl>
                    <SelectTrigger data-testid="event-game-select" className="w-full">
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
                    data-testid="event-people-per-team-input"
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
                      data-testid="event-max-teams-input"
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
                      data-testid="event-unlimited-checkbox"
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
                    <SelectTrigger data-testid="event-draft-select" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="shuffle">Shuffle — MMR point buy draft</SelectItem>
                    <SelectItem value="snake">Snake Draft — Captains pick in snake order</SelectItem>
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
                    <SelectTrigger data-testid="event-bracket-select" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="double_elimination">Double Elimination</SelectItem>
                    <SelectItem value="single_elimination">Single Elimination</SelectItem>
                    <SelectItem value="swiss">Swiss Bracket</SelectItem>
                  </SelectContent>
                </Select>
                <FormDescription>
                  Double elimination works best with teams that are a power of 2 (2, 4, 8, 16)
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <LobbyConfigSection control={form.control} watch={form.watch} />

        {/* Recurring toggle */}
        <FormField
          control={form.control}
          name="is_recurring"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3 rounded-md border border-border p-3">
              <FormControl>
                <input
                  data-testid="event-recurring-checkbox"
                  type="checkbox"
                  checked={field.value}
                  onChange={field.onChange}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm font-medium cursor-pointer">
                  Recurring Event (Event Repeater)
                </FormLabel>
                <FormDescription>Automatically generates events on a schedule</FormDescription>
              </div>
            </FormItem>
          )}
        />

        {isRecurring ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="frequency"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Frequency</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="event-frequency-select" className="w-full">
                          <SelectValue placeholder="Select frequency" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {Object.entries(FREQUENCY_LABELS).map(([val, label]) => (
                          <SelectItem key={val} value={val}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="day_of_week"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Day of Week</FormLabel>
                    <Select
                      onValueChange={(val) => field.onChange(parseInt(val, 10))}
                      value={field.value?.toString()}
                    >
                      <FormControl>
                        <SelectTrigger data-testid="event-day-select" className="w-full">
                          <SelectValue placeholder="Select day" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {DAY_LABELS.map((label, idx) => (
                          <SelectItem key={idx} value={String(idx)}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <FormField
                control={form.control}
                name="time_of_day"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Time</FormLabel>
                    <FormControl>
                      <Input data-testid="event-time-input" type="time" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="starts_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Starts</FormLabel>
                    <FormControl>
                      <Input data-testid="event-starts-input" type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="ends_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Ends (optional)</FormLabel>
                    <FormControl>
                      <Input data-testid="event-ends-input" type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="generate_days_ahead"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Generate Days Ahead</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="event-generate-days-input"
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      {...field}
                      value={field.value?.toString() ?? ''}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 7)}
                    />
                  </FormControl>
                  <FormDescription>How many days in advance to generate events</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </>
        ) : (
          <FormField
            control={form.control}
            name="scheduled_at"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Scheduled Date & Time</FormLabel>
                <FormControl>
                  <Input data-testid="event-scheduled-input" type="datetime-local" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

          </TabsContent>

          <TabsContent value="discord" className="space-y-4">
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater={isRecurring}
              organizationId={organizationId}
            />
          </TabsContent>
        </Tabs>
      </Form>
    </FormDialog>
  );
}
