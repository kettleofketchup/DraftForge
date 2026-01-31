import { zodResolver } from '@hookform/resolvers/zod';
import { format, parseISO } from 'date-fns';
import { CalendarIcon, Clock, Globe } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';

import { updateTournament } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import { Button } from '~/components/ui/button';
import { Calendar } from '~/components/ui/calendar';
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import type { TournamentType } from '../types';
import { STATE_CHOICES } from '../constants';
import { COMMON_TIMEZONES, STATE_VALUES, TOURNAMENT_TYPE_VALUES } from '../schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('TournamentEditModal');

const TOURNAMENT_TYPE_CHOICES = [
  { value: 'single_elimination', label: 'Single Elimination' },
  { value: 'double_elimination', label: 'Double Elimination' },
  { value: 'swiss', label: 'Swiss Bracket' },
] as const;

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

const TournamentEditSchema = z.object({
  name: z.string().min(1, 'Name is required').max(200),
  state: z.enum(STATE_VALUES).nullable().optional(),
  tournament_type: z.enum(TOURNAMENT_TYPE_VALUES).nullable().optional(),
  date_played: z.string().nullable().optional(),
  timezone: z.string().optional(),
  league: z.number().nullable().optional(),
});

type TournamentEditInput = z.infer<typeof TournamentEditSchema>;

interface TournamentEditModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tournament: TournamentType;
  onSuccess?: () => void;
}

export function TournamentEditModal({
  open,
  onOpenChange,
  tournament,
  onSuccess,
}: TournamentEditModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const setTournament = useUserStore((state) => state.setTournament);
  const leagues = useUserStore((state) => state.leagues);
  const getLeagues = useUserStore((state) => state.getLeagues);

  // Fetch leagues if not loaded
  useEffect(() => {
    if (!leagues || leagues.length === 0) {
      getLeagues();
    }
  }, [leagues, getLeagues]);

  // Get current league ID from tournament
  const getCurrentLeagueId = (): number | null => {
    if (typeof tournament.league === 'number') {
      return tournament.league;
    }
    if (typeof tournament.league === 'object' && tournament.league) {
      return (tournament.league as unknown as { pk?: number })?.pk ?? null;
    }
    return null;
  };

  // Get league timezone if available, default to America/New_York
  const leagueData = typeof tournament.league === 'object'
    ? (tournament.league as unknown as { timezone?: string })
    : null;
  const defaultTimezone = leagueData?.timezone
    || (tournament as unknown as { timezone?: string })?.timezone
    || 'America/New_York';

  // Extract initial date and time from existing tournament
  const initialDateTime = extractDateAndTime(tournament.date_played);
  const [selectedDate, setSelectedDate] = useState(initialDateTime.date);
  const [selectedTime, setSelectedTime] = useState(initialDateTime.time);

  const form = useForm<TournamentEditInput>({
    resolver: zodResolver(TournamentEditSchema),
    defaultValues: {
      name: tournament.name || '',
      state: tournament.state ?? undefined,
      tournament_type: tournament.tournament_type ?? undefined,
      date_played: combineDateAndTime(initialDateTime.date, initialDateTime.time),
      timezone: defaultTimezone,
      league: getCurrentLeagueId(),
    },
  });

  // Reset form when tournament changes or modal opens
  useEffect(() => {
    if (open) {
      const dateTime = extractDateAndTime(tournament.date_played);
      setSelectedDate(dateTime.date);
      setSelectedTime(dateTime.time);

      const tz = (typeof tournament.league === 'object'
        ? (tournament.league as unknown as { timezone?: string })?.timezone
        : null)
        || (tournament as unknown as { timezone?: string })?.timezone
        || 'America/New_York';

      form.reset({
        name: tournament.name || '',
        state: tournament.state ?? undefined,
        tournament_type: tournament.tournament_type ?? undefined,
        date_played: combineDateAndTime(dateTime.date, dateTime.time),
        timezone: tz,
        league: getCurrentLeagueId(),
      });
    }
  }, [open, tournament, form]);

  // Update date_played when date or time changes
  useEffect(() => {
    form.setValue('date_played', combineDateAndTime(selectedDate, selectedTime));
  }, [selectedDate, selectedTime, form]);

  async function onSubmit(data: TournamentEditInput) {
    if (isSubmitting || !tournament.pk) return;
    setIsSubmitting(true);

    try {
      // Build payload - convert empty strings to null for proper API handling
      const payload: Partial<TournamentType> & { timezone?: string; league_id_write?: number | null } = {
        name: data.name,
        state: data.state || null,
        tournament_type: data.tournament_type || null,
        date_played: data.date_played || null,
        timezone: data.timezone,
        league_id_write: data.league ?? null,
      };
      log.debug('Saving tournament with payload:', payload);

      const updatedTournament = await updateTournament(tournament.pk, payload);
      setTournament(updatedTournament);
      toast.success('Tournament updated successfully');
      onOpenChange(false);
      onSuccess?.();
    } catch (err: any) {
      const message = err?.response?.data || err?.message || 'Failed to update tournament';
      log.error('Failed to update tournament', err);
      toast.error(`Failed to update tournament: ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit Tournament"
      description="Update tournament information."
      submitLabel="Save Changes"
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onSubmit)}
      size="md"
      data-testid="edit-tournament-modal"
    >
      <Form {...form}>
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

        <FormField
          control={form.control}
          name="state"
          render={({ field }) => (
            <FormItem>
              <FormLabel>State</FormLabel>
              <Select onValueChange={field.onChange} value={field.value ?? ''}>
                <FormControl>
                  <SelectTrigger data-testid="tournament-state-select">
                    <SelectValue placeholder="Select state" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {Object.entries(STATE_CHOICES).map(([key, value]) => (
                    <SelectItem key={key} value={key}>
                      {value}
                    </SelectItem>
                  ))}
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
              <FormLabel>Tournament Type</FormLabel>
              <Select onValueChange={field.onChange} value={field.value ?? ''}>
                <FormControl>
                  <SelectTrigger data-testid="tournament-type-select">
                    <SelectValue placeholder="Select tournament type" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {TOURNAMENT_TYPE_CHOICES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
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
          render={() => (
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
                Defaults to league timezone (US East)
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
              <FormLabel>League</FormLabel>
              <Select
                onValueChange={(value) => field.onChange(value === "none" ? null : Number(value))}
                value={field.value?.toString() ?? "none"}
              >
                <FormControl>
                  <SelectTrigger data-testid="tournament-league-select">
                    <SelectValue placeholder="Select league" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="none">No League</SelectItem>
                  {leagues?.filter((league: LeagueType) => league.pk != null).map((league: LeagueType) => (
                    <SelectItem key={league.pk} value={league.pk!.toString()}>
                      {league.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                Assign this tournament to a league
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </Form>
    </FormDialog>
  );
}
