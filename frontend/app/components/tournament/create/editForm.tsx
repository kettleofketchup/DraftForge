import { zodResolver } from '@hookform/resolvers/zod';
import { format, parseISO } from 'date-fns';
import { CalendarIcon, Clock, Globe } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { createTournament, updateTournament } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import { Button } from '~/components/ui/button';
import { Calendar } from '~/components/ui/calendar';
import { DialogClose } from '~/components/ui/dialog';
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { ScrollArea } from '~/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import {
  COMMON_TIMEZONES,
  CreateTournamentSchema,
  type CreateTournamentInput,
  type TournamentTypeValue,
} from '../schemas';
import type { TournamentClassType, TournamentType } from '../types';
import { getLogger } from '~/lib/logger';
import { SCROLLAREA_CSS } from '~/components/reusable/modal';

const log = getLogger('TournamentEditForm');

// Helper to format timezone for display
function formatTimezoneLabel(tz: string): string {
  const parts = tz.split('/');
  return parts.length > 1 ? parts[1].replace(/_/g, ' ') : tz;
}

// Helper to extract date and time from ISO string
function extractDateAndTime(isoString: string | null | undefined): { date: string; time: string } {
  if (!isoString) {
    const now = new Date();
    return {
      date: format(now, 'yyyy-MM-dd'),
      time: '19:00', // Default to 7 PM
    };
  }
  try {
    const date = parseISO(isoString);
    return {
      date: format(date, 'yyyy-MM-dd'),
      time: format(date, 'HH:mm'),
    };
  } catch {
    return {
      date: format(new Date(), 'yyyy-MM-dd'),
      time: '19:00',
    };
  }
}

// Helper to combine date and time into ISO string
function combineDateAndTime(dateStr: string, timeStr: string): string {
  return `${dateStr}T${timeStr}:00`;
}

interface Props {
  tourn: TournamentClassType;
  form?: TournamentClassType;
  setForm?: React.Dispatch<React.SetStateAction<TournamentClassType>>;
  onSuccess?: () => void;
}

export const TournamentEditForm: React.FC<Props> = ({
  tourn,
  onSuccess,
}) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const getTournaments = useUserStore((state) => state.getTournaments);
  const leagues = useUserStore((state) => state.leagues);
  const getLeagues = useUserStore((state) => state.getLeagues);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);

  const isEditing = !!tourn?.pk;

  // Extract initial date and time from existing tournament
  const initialDateTime = extractDateAndTime(tourn?.date_played);
  const [selectedDate, setSelectedDate] = useState(initialDateTime.date);
  const [selectedTime, setSelectedTime] = useState(initialDateTime.time);

  // Fetch leagues if not loaded
  useEffect(() => {
    if (!leagues || leagues.length === 0) {
      getLeagues();
    }
  }, [leagues, getLeagues]);

  const form = useForm<CreateTournamentInput>({
    resolver: zodResolver(CreateTournamentSchema),
    defaultValues: {
      name: tourn?.name || '',
      tournament_type: (tourn?.tournament_type as TournamentTypeValue) || 'double_elimination',
      date_played: combineDateAndTime(initialDateTime.date, initialDateTime.time),
      timezone: (tourn as unknown as { timezone?: string })?.timezone || 'America/New_York',
      league: tourn?.league || null,
    },
  });

  // Update date_played when date or time changes
  useEffect(() => {
    form.setValue('date_played', combineDateAndTime(selectedDate, selectedTime));
  }, [selectedDate, selectedTime, form]);

  // Permission check
  if (!currentUser?.is_staff && !currentUser?.is_superuser) {
    return (
      <div className="text-destructive p-4">
        You do not have permission to edit tournaments.
      </div>
    );
  }

  async function onSubmit(data: CreateTournamentInput) {
    if (isSubmitting) return;
    setIsSubmitting(true);

    try {
      const payload: Partial<TournamentType> & { timezone?: string } = {
        name: data.name,
        tournament_type: data.tournament_type,
        date_played: data.date_played,
        timezone: data.timezone,
        league: data.league || null,
      };

      if (isEditing) {
        await updateTournament(tourn.pk!, payload);
        toast.success(`Tournament "${data.name}" updated successfully`);
      } else {
        await createTournament(payload);
        toast.success(`Tournament "${data.name}" created successfully`);
      }

      getTournaments();
      onSuccess?.();
      form.reset();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      log.error('Failed to save tournament:', err);
      toast.error(isEditing ? 'Failed to update tournament' : 'Failed to create tournament');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <ScrollArea className={SCROLLAREA_CSS}>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-4 p-1"
          data-testid="tournament-form"
        >
          {/* Tournament Name */}
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Tournament Name</FormLabel>
                <FormControl>
                  <Input
                    placeholder="Enter tournament name"
                    data-testid="tournament-name-input"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Tournament Type */}
          <FormField
            control={form.control}
            name="tournament_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Tournament Type</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  defaultValue={field.value}
                >
                  <FormControl>
                    <SelectTrigger data-testid="tournament-type-select">
                      <SelectValue placeholder="Select tournament type" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      value="single_elimination"
                      data-testid="tournament-type-single"
                    >
                      Single Elimination
                    </SelectItem>
                    <SelectItem
                      value="double_elimination"
                      data-testid="tournament-type-double"
                    >
                      Double Elimination
                    </SelectItem>
                    <SelectItem
                      value="swiss"
                      data-testid="tournament-type-swiss"
                    >
                      Swiss System
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Date & Time Picker */}
          <FormField
            control={form.control}
            name="date_played"
            render={({ field }) => (
              <FormItem className="flex flex-col">
                <FormLabel>Tournament Date & Time</FormLabel>
                <div className="flex gap-2">
                  {/* Date Picker */}
                  <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
                    <PopoverTrigger asChild>
                      <FormControl>
                        <Button
                          variant="outline"
                          className={cn(
                            'flex-1 pl-3 text-left font-normal',
                            !selectedDate && 'text-muted-foreground'
                          )}
                          data-testid="tournament-date-picker"
                        >
                          {selectedDate ? (
                            format(new Date(selectedDate), 'PPP')
                          ) : (
                            <span>Pick a date</span>
                          )}
                          <CalendarIcon className="ml-auto h-4 w-4 opacity-50" />
                        </Button>
                      </FormControl>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={selectedDate ? new Date(selectedDate) : undefined}
                        onSelect={(date) => {
                          if (date) {
                            setSelectedDate(format(date, 'yyyy-MM-dd'));
                            setCalendarOpen(false);
                          }
                        }}
                        data-testid="tournament-calendar"
                      />
                    </PopoverContent>
                  </Popover>

                  {/* Time Picker */}
                  <div className="relative">
                    <Input
                      type="time"
                      value={selectedTime}
                      onChange={(e) => setSelectedTime(e.target.value)}
                      className="w-32"
                      data-testid="tournament-time-picker"
                    />
                    <Clock className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 opacity-50 pointer-events-none" />
                  </div>
                </div>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Timezone Picker */}
          <FormField
            control={form.control}
            name="timezone"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="flex items-center gap-2">
                  <Globe className="h-4 w-4" />
                  Timezone
                </FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={field.value}
                >
                  <FormControl>
                    <SelectTrigger data-testid="tournament-timezone-select">
                      <SelectValue placeholder="Select timezone" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {COMMON_TIMEZONES.map((tz) => (
                      <SelectItem
                        key={tz}
                        value={tz}
                        data-testid={`tournament-timezone-${tz}`}
                      >
                        {tz === 'UTC' ? 'UTC' : `${formatTimezoneLabel(tz)} (${tz})`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  The timezone in which the tournament will be played
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* League Picker */}
          <FormField
            control={form.control}
            name="league"
            render={({ field }) => (
              <FormItem>
                <FormLabel>League (Optional)</FormLabel>
                <Select
                  onValueChange={(value) =>
                    field.onChange(value === 'none' ? null : parseInt(value, 10))
                  }
                  value={field.value?.toString() || 'none'}
                >
                  <FormControl>
                    <SelectTrigger data-testid="tournament-league-select">
                      <SelectValue placeholder="Select a league" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="none" data-testid="tournament-league-none">
                      No League
                    </SelectItem>
                    {leagues?.map((league: LeagueType) => (
                      <SelectItem
                        key={league.pk}
                        value={league.pk?.toString() || ''}
                        data-testid={`tournament-league-${league.pk}`}
                      >
                        {league.name}
                        {league.organization_name && (
                          <span className="text-muted-foreground ml-2">
                            ({league.organization_name})
                          </span>
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Submit Button */}
          <div className="flex flex-row justify-end gap-2 pt-4">
            <DialogClose asChild>
              <Button
                type="button"
                variant="outline"
                disabled={isSubmitting}
                data-testid="tournament-cancel-button"
              >
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="submit"
              disabled={isSubmitting}
              data-testid="tournament-submit-button"
            >
              {isSubmitting
                ? isEditing
                  ? 'Saving...'
                  : 'Creating...'
                : isEditing
                  ? 'Save Changes'
                  : 'Create Tournament'}
            </Button>
          </div>
        </form>
      </Form>
    </ScrollArea>
  );
};
