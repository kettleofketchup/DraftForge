import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { createEvent, createEventRepeater } from '~/components/api/api';
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
import { useQueryClient } from '@tanstack/react-query';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { DiscordConfigSection, DiscordIcon } from './DiscordConfigSection';
import { createEventInputSchema, Frequency, FREQUENCY_LABELS, DAY_LABELS, DISCORD_CONFIG_DEFAULTS, type CreateEventInput } from './schemas';
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

  const form = useForm<CreateEventInput>({
    resolver: zodResolver(createEventInputSchema),
    defaultValues: {
      name: '',
      description: '',
      scheduled_at: '',
      organization: organizationId,
      tournament_name: '',
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'snake',
      people_per_team: 5,
      number_of_teams: null,
      discord_notify_new_events: false,
      ...DISCORD_CONFIG_DEFAULTS,
      is_recurring: false,
      frequency: Frequency.WEEKLY,
      generate_days_ahead: 7,
    },
  });

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
                <Input placeholder="Weekly inhouse" {...field} />
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
                <Textarea placeholder="Event description" rows={2} {...field} />
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
                  <Input placeholder="Inhouse #1" {...field} />
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
                    <SelectTrigger className="w-full">
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
                    form.setValue('people_per_team', gameType === 2 ? 6 : 5);
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
                    <SelectItem value="snake">Snake Draft</SelectItem>
                    <SelectItem value="shuffle">Shuffle</SelectItem>
                    <SelectItem value="normal">Manual</SelectItem>
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
                    <SelectItem value="single_elimination">Single Elimination</SelectItem>
                    <SelectItem value="double_elimination">Double Elimination</SelectItem>
                    <SelectItem value="swiss">Swiss Bracket</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {/* Recurring toggle */}
        <FormField
          control={form.control}
          name="is_recurring"
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
                        <SelectTrigger className="w-full">
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
                name="starts_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Starts</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
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
                      <Input type="date" {...field} />
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
                  <Input type="datetime-local" {...field} />
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
