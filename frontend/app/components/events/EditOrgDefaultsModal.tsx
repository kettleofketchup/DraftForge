import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { z } from 'zod';
import { getOrgEventDefaults } from '~/components/api/api';
import { useUpdateOrgDefaultsMutation } from '~/hooks/useEvent';
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
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { discordConfigSchema, DISCORD_CONFIG_DEFAULTS, GameMode, COMMON_TIMEZONES } from './schemas';
import { GAME_TYPE } from '~/components/game/constants';

const orgDefaultsSchema = z.object({
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
}).merge(discordConfigSchema);

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
  const form = useForm<z.input<typeof orgDefaultsSchema>, undefined, OrgDefaultsInput>({
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
        discord_confirm_attendance_hours: defaults.discord_confirm_attendance_hours,
        discord_profile_reminder: defaults.discord_profile_reminder,
        discord_profile_reminder_hours: defaults.discord_profile_reminder_hours,
        discord_mark_interested: defaults.discord_mark_interested,
        discord_post_signups: defaults.discord_post_signups,
        discord_post_signups_channel_id: defaults.discord_post_signups_channel_id,
        discord_announcement: defaults.discord_announcement,
        discord_announcement_channel_id: defaults.discord_announcement_channel_id,
        discord_announcement_hours: defaults.discord_announcement_hours,
        discord_require_rank_screenshot: defaults.discord_require_rank_screenshot ?? false,
        discord_require_battlecup_screenshot: defaults.discord_require_battlecup_screenshot ?? false,
        min_mmr: defaults.min_mmr ?? null,
        allow_active_mmr: defaults.allow_active_mmr ?? true,
        allow_previous_rank: defaults.allow_previous_rank ?? true,
        allow_battlecup_rating: defaults.allow_battlecup_rating ?? true,
      });
    }
  }, [defaults, open]);

  async function onSubmit(data: OrgDefaultsInput) {
    if (!defaults) return;
    try {
      await mutation.mutateAsync({ id: defaults.id, data });
      toast.success('Event defaults updated');
      onOpenChange(false);
    } catch {
      toast.error('Failed to update defaults');
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Organization Event Defaults"
      description="These defaults are applied when creating new events."
      submitLabel="Save Defaults"
      isSubmitting={mutation.isPending}
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
              name="tournament_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Default Tournament Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Leave blank to use event name" {...field} />
                  </FormControl>
                  <FormDescription>
                    Pre-filled when creating new events. Can be overridden per event.
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
                  <FormDescription>
                    Default timezone for new events
                  </FormDescription>
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
                        form.setValue('people_per_team', gameType === GAME_TYPE.DEADLOCK ? 6 : 5);
                        // Reset Dota-only fields when switching to non-Dota
                        const currentMode = form.getValues('game_mode');
                        if (gameType !== GAME_TYPE.DOTA2) {
                          if (currentMode === GameMode.CAPTAINS_MODE || currentMode === GameMode.TURBO) {
                            form.setValue('game_mode', GameMode.NORMAL);
                          }
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

            <FormField
              control={form.control}
              name="game_mode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Game Mode</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="captains_mode">Captain's Mode</SelectItem>
                      <SelectItem value="turbo">Turbo</SelectItem>
                      <SelectItem value="custom">Custom</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="max_players"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max Players</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        value={field.value ?? ''}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10);
                          field.onChange(Number.isNaN(v) ? null : Math.max(1, v));
                        }}
                        placeholder="No limit"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="space-y-3">
                <FormField
                  control={form.control}
                  name="auto_approve"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-3 rounded-md border border-border p-3">
                      <FormControl>
                        <input
                          type="checkbox"
                          checked={field.value}
                          onChange={field.onChange}
                          className="h-4 w-4 rounded border-border accent-primary"
                        />
                      </FormControl>
                      <FormLabel className="text-sm cursor-pointer">Auto-approve signups</FormLabel>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="auto_confirm"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-3 rounded-md border border-border p-3">
                      <FormControl>
                        <input
                          type="checkbox"
                          checked={field.value}
                          onChange={field.onChange}
                          className="h-4 w-4 rounded border-border accent-primary"
                        />
                      </FormControl>
                      <FormLabel className="text-sm cursor-pointer">Auto-confirm signups</FormLabel>
                    </FormItem>
                  )}
                />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="discord" className="space-y-4">
            <DiscordConfigSection
              control={form.control}
              watch={form.watch}
              isRepeater={false}
              organizationId={organizationId}
            />
          </TabsContent>
        </Tabs>
      </Form>
    </FormDialog>
  );
}
