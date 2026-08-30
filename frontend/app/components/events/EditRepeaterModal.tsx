import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import type { EventRepeaterType } from '~/components/api/api';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { useUpdateEventRepeaterMutation } from '~/hooks/useEvent';
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { LobbyConfigSection } from './LobbyConfigSection';
import { discordConfigSchema, GameMode, DISCORD_CONFIG_DEFAULTS, COMMON_TIMEZONES, Frequency, FREQUENCY_LABELS, DAY_LABELS } from './schemas';
import { GAME_TYPE } from '~/components/game/constants';

const editRepeaterSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  tournament_name: z.string().min(1, 'Tournament name is required'),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  game_mode: z.string(),
  custom_game_name: z.string(),
  captains_draft_time: z.number().int().min(1),
  lobby_steam_league_id: z.number().nullable(),
  people_per_team: z.number().int().min(1),
  number_of_teams: z.number().int().min(2).nullable(),
  frequency: z.string(),
  day_of_week: z.number().int().min(0).max(6).optional(),
  time_of_day: z.string(),
  ends_at: z.string().optional(),
  generate_days_ahead: z.number().int().min(1),
  timezone: z.string().min(1, 'Timezone is required'),
  discord_notify_new_events: z.boolean(),
}).merge(discordConfigSchema);

type EditRepeaterInput = z.infer<typeof editRepeaterSchema>;

interface EditRepeaterModalProps {
  repeater: EventRepeaterType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditRepeaterModal({ repeater, open, onOpenChange }: EditRepeaterModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const mutation = useUpdateEventRepeaterMutation(repeater?.id ?? 0);

  // 3-generic useForm to align TFieldValues=z.input and TTransformedValues=z.output
  // — zodResolver returns Resolver<z.input<S>, _, z.output<S>> under zod 4.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<z.input<typeof editRepeaterSchema>, unknown, EditRepeaterInput>({
    resolver: zodResolver(editRepeaterSchema),
    defaultValues: {
      name: '',
      description: '',
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
      frequency: Frequency.WEEKLY,
      day_of_week: undefined,
      time_of_day: '19:00',
      ends_at: '',
      generate_days_ahead: 7,
      timezone: '',
      discord_notify_new_events: true,
      ...DISCORD_CONFIG_DEFAULTS,
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
        draft_type: repeater.draft_type,
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
        discord_create_event: repeater.discord_create_event,
        discord_sync_signups: repeater.discord_sync_signups,
        discord_event_title: repeater.discord_event_title,
        discord_event_description: repeater.discord_event_description,
        discord_event_info: repeater.discord_event_info,
        discord_signup_reminder: repeater.discord_signup_reminder,
        discord_signup_reminder_hours: repeater.discord_signup_reminder_hours,
        discord_confirm_attendance: repeater.discord_confirm_attendance,
        discord_confirm_attendance_hours: repeater.discord_confirm_attendance_hours,
        discord_profile_reminder: repeater.discord_profile_reminder,
        discord_profile_reminder_hours: repeater.discord_profile_reminder_hours,
        discord_notify_new_events: repeater.discord_notify_new_events,
        discord_mark_interested: repeater.discord_mark_interested,
        discord_post_signups: repeater.discord_post_signups,
        discord_post_signups_channel_id: repeater.discord_post_signups_channel_id,
        discord_announcement: repeater.discord_announcement,
        discord_announcement_channel_id: repeater.discord_announcement_channel_id,
        discord_announcement_hours: repeater.discord_announcement_hours,
        discord_announcement_role_ids: repeater.discord_announcement_role_ids ?? [],
        discord_signup_role_ids: repeater.discord_signup_role_ids ?? [],
        discord_require_rank_screenshot: repeater.discord_require_rank_screenshot ?? false,
        discord_require_battlecup_screenshot: repeater.discord_require_battlecup_screenshot ?? false,
        min_mmr: repeater.min_mmr ?? null,
        allow_active_mmr: repeater.allow_active_mmr ?? true,
        allow_previous_rank: repeater.allow_previous_rank ?? true,
        allow_battlecup_rating: repeater.allow_battlecup_rating ?? true,
        // Approval rule flags — see CreateEventModal for the regression note.
        require_steam_id: repeater.require_steam_id ?? false,
        require_mmr_verified: repeater.require_mmr_verified ?? false,
        require_profile_complete: repeater.require_profile_complete ?? false,
      });
    }
  }, [repeater, open]);

  async function onSubmit(data: EditRepeaterInput) {
    if (isSubmitting || !repeater) return;
    setIsSubmitting(true);
    try {
      await mutation.mutateAsync({
        ...data,
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
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit Repeating Event"
      description="Changes apply to future generated events only."
      submitLabel="Save"
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

        {/* Schedule */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="frequency"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Frequency</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue />
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
                    <SelectTrigger className="w-full">
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
                  <Input type="time" {...field} />
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
                      <SelectItem key={tz} value={tz}>{tz.replace(/_/g, ' ')}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                  <Input type="date" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="generate_days_ahead"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Days Ahead</FormLabel>
                <FormControl>
                  <Input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    {...field}
                    value={field.value?.toString() ?? ''}
                    onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 7)}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {/* Tournament config */}
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
                    form.setValue('people_per_team', gameType === GAME_TYPE.DEADLOCK ? 6 : 5);
                    // Reset Dota-only fields when switching to non-Dota
                    const currentMode = form.getValues('game_mode');
                    if (gameType !== GAME_TYPE.DOTA2) {
                      if (currentMode === GameMode.CAPTAINS_MODE || currentMode === GameMode.TURBO) {
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
                    <SelectTrigger className="w-full">
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
                    <SelectTrigger className="w-full">
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

          </TabsContent>

          <TabsContent value="discord" className="space-y-4">
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater={true}
              organizationId={repeater?.organization ?? 0}
            />
          </TabsContent>
        </Tabs>
      </Form>
    </FormDialog>
  );
}
