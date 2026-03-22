import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
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
import { ShieldCheck } from 'lucide-react';
import { useUpdateEventMutation } from '~/hooks/useEvent';
import { ApprovalConfigSection } from './ApprovalConfigSection';
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { LobbyConfigSection } from './LobbyConfigSection';
import { discordConfigSchema, GameType, GameMode, DISCORD_CONFIG_DEFAULTS } from './schemas';
import type { EventType } from './schemas';

const editEventSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  scheduled_at: z.string().min(1, 'Scheduled date is required'),
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
}).merge(discordConfigSchema);

type EditEventInput = z.infer<typeof editEventSchema>;

interface EditEventModalProps {
  event: EventType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function toDatetimeLocal(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function EditEventModal({ event, open, onOpenChange }: EditEventModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const mutation = useUpdateEventMutation(event?.id ?? 0);

  const form = useForm<EditEventInput>({
    resolver: zodResolver(editEventSchema),
    defaultValues: {
      name: '',
      description: '',
      scheduled_at: '',
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
      ...DISCORD_CONFIG_DEFAULTS,
    },
  });

  // Reset form when event changes
  useEffect(() => {
    if (event && open) {
      form.reset({
        name: event.name,
        description: event.description,
        scheduled_at: toDatetimeLocal(event.scheduled_at),
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
        discord_create_event: event.discord_create_event,
        discord_sync_signups: event.discord_sync_signups,
        discord_event_title: event.discord_event_title,
        discord_event_description: event.discord_event_description,
        discord_event_info: event.discord_event_info,
        discord_signup_reminder: event.discord_signup_reminder,
        discord_signup_reminder_hours: event.discord_signup_reminder_hours,
        discord_confirm_attendance: event.discord_confirm_attendance,
        discord_confirm_attendance_hours: event.discord_confirm_attendance_hours,
        discord_profile_reminder: event.discord_profile_reminder,
        discord_profile_reminder_hours: event.discord_profile_reminder_hours,
        discord_mark_interested: event.discord_mark_interested,
        discord_post_signups: event.discord_post_signups,
        discord_post_signups_channel_id: event.discord_post_signups_channel_id,
        discord_announcement: event.discord_announcement,
        discord_announcement_channel_id: event.discord_announcement_channel_id,
        discord_announcement_hours: event.discord_announcement_hours,
        discord_subscriber_dm: event.discord_subscriber_dm,
        discord_subscriber_dm_hours: event.discord_subscriber_dm_hours,
        discord_require_rank_screenshot: event.discord_require_rank_screenshot,
        discord_require_battlecup_screenshot: event.discord_require_battlecup_screenshot,
        min_mmr: event.min_mmr ?? null,
        allow_active_mmr: event.allow_active_mmr,
        allow_previous_rank: event.allow_previous_rank,
        allow_battlecup_rating: event.allow_battlecup_rating,
      });
    }
  }, [event, open]);

  async function onSubmit(data: EditEventInput) {
    if (isSubmitting || !event) return;
    setIsSubmitting(true);
    try {
      const result = await mutation.mutateAsync(data);
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

        <FormField
          control={form.control}
          name="scheduled_at"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Scheduled Date & Time</FormLabel>
              <FormControl>
                <Input type="datetime-local" {...field} />
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

          <TabsContent value="approval" className="space-y-4">
            <ApprovalConfigSection control={form.control} watch={form.watch} />
          </TabsContent>

          <TabsContent value="discord" className="space-y-4">
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater={false}
              organizationId={event?.organization ?? 0}
            />
          </TabsContent>
        </Tabs>
      </Form>
    </FormDialog>
  );
}
