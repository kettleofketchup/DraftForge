import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import { CalendarIcon, Settings2, Trophy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm, type FieldErrors } from 'react-hook-form';
import { useLocation } from 'react-router';
import { toast } from 'sonner';

import { createTournament, updateTournament } from '~/components/api/api';
import type { TournamentWritePayload } from '~/components/api/tournamentAPI';
import { DiscordIcon } from '~/components/events/DiscordConfigSection';
import { BracketTypeField } from '~/components/events/form/fields/BracketTypeField';
import { TimezoneField } from '~/components/events/form/fields/TimezoneField';
import { LobbyConfigSection } from '~/components/events/LobbyConfigSection';
import type { LeagueType } from '~/components/league/schemas';
import { FormTabsList } from '~/components/patterns/FormTabsList';
import { DraftSettingsSection } from '~/components/teamdraft/DraftSettingsSection';
import {
  draftSettingsFormToPatch,
  draftSettingsToFormInput,
} from '~/components/teamdraft/schemas';
import { Button } from '~/components/ui/button';
import { CancelButton, SubmitButton } from '~/components/ui/buttons';
import { Calendar } from '~/components/ui/calendar';
import { DialogClose } from '~/components/ui/dialog';
import {
  Form,
  FormControl,
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
import { Tabs, TabsContent } from '~/components/ui/tabs';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { TOURNAMENT_TIMEZONES } from '~/lib/timezones';
import {
  canCreateTournament,
  leagueOptionsFor,
} from '~/lib/tournamentPermissions';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import {
  CreateTournamentSchema,
  type CreateTournamentInput,
  type TournamentTypeValue,
} from '../schemas';
import type { TournamentClassType } from '../types';
import { DiscordTournamentConfigSection } from './DiscordTournamentConfigSection';
import { DotaLobbyConfigSection } from './DotaLobbyConfigSection';
import { fieldErrorsFrom, tabForField, type FormTab } from './formErrors';
import { TournamentConfigSection } from './TournamentConfigSection';

const log = getLogger('TournamentEditForm');

// Helper to format timezone for display
function formatTimezoneLabel(tz: string): string {
  const parts = tz.split('/');
  return parts.length > 1 ? parts[1].replace(/_/g, ' ') : tz;
}

// Helper to extract date and time from ISO string
function extractDateAndTime(isoString: string | null | undefined): {
  date: string;
  time: string;
} {
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

// Helper to parse a yyyy-MM-dd string as local midnight.
// new Date('yyyy-MM-dd') parses as UTC, causing off-by-one-day errors
// in timezones behind UTC. Appending T00:00:00 forces local-time parsing.
function localDate(dateStr: string): Date {
  return new Date(dateStr + 'T00:00:00');
}

export function refreshAfterSave({
  pathname,
  getTournaments,
  queryClient,
  pk,
}: {
  pathname: string;
  getTournaments: () => unknown;
  queryClient: QueryClient;
  pk?: number;
}): void {
  if (pathname.replace(/\/+$/, '') !== '/tournaments') {
    getTournaments();
  }
  queryClient.invalidateQueries({ queryKey: ['tournaments'] });
  if (pk) {
    queryClient.invalidateQueries({ queryKey: ['tournament', pk] });
  }
}

interface Props {
  tourn: TournamentClassType;
  onSuccess?: () => void;
  canEdit?: boolean;
}

type LeagueOption = LeagueType & { organization?: { pk: number } | null };

export const TournamentEditForm: React.FC<Props> = ({
  tourn,
  onSuccess,
  canEdit,
}) => {
  const queryClient = useQueryClient();
  const { pathname } = useLocation();
  const currentUser = useUserStore((state) => state.currentUser);
  const getTournaments = useUserStore((state) => state.getTournaments);
  const leagues = useUserStore((state) => state.leagues);
  const getLeagues = useUserStore((state) => state.getLeagues);
  const leaguesOrgId = useUserStore((state) => state.leaguesOrgId);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [tab, setTab] = useState<FormTab>('general');

  const isEditing = !!tourn?.pk;
  const sourceEvent = tourn?.source_event
    ? { id: tourn.source_event.id, name: tourn.source_event.name }
    : null;

  // Extract initial date and time from existing tournament
  const initialDateTime = extractDateAndTime(tourn?.date_played);
  const [selectedDate, setSelectedDate] = useState(initialDateTime.date);
  const [selectedTime, setSelectedTime] = useState(initialDateTime.time);

  useEffect(() => {
    if (leaguesOrgId !== 'all') getLeagues();
  }, [leaguesOrgId, getLeagues]);

  // tourn.league may be a number (id) or an embedded { pk, name, ... } —
  // the form field expects a numeric league id (or null).
  const leagueDefault =
    typeof tourn?.league === 'object' && tourn.league !== null
      ? tourn.league.pk
      : (tourn?.league ?? null);

  const form = useForm<CreateTournamentInput>({
    // Cast: zodResolver's TFieldValues generic resolves to `unknown` when
    // the schema uses z.coerce, so RHF's inferred Resolver doesn't unify
    // with our explicit CreateTournamentInput. Same workaround as in
    // editUser/editModal.tsx — the runtime resolver is correct.
    resolver: zodResolver(
      CreateTournamentSchema,
    ) as unknown as import('react-hook-form').Resolver<CreateTournamentInput>,
    defaultValues: {
      name: tourn?.name || '',
      tournament_type:
        (tourn?.tournament_type as TournamentTypeValue) || 'double_elimination',
      date_played: combineDateAndTime(
        initialDateTime.date,
        initialDateTime.time,
      ),
      timezone:
        (tourn as unknown as { timezone?: string })?.timezone ||
        'America/New_York',
      league: leagueDefault,
      auto_create_hero_drafts: tourn?.auto_create_hero_drafts ?? false,
      discord_send_draft_link: tourn?.discord_send_draft_link ?? false,
      discord_send_herodraft_link: tourn?.discord_send_herodraft_link ?? false,
      dota_lobby_mode: tourn?.dota_lobby_mode ?? 'off',
      dota_lobby_launch: tourn?.dota_lobby_launch ?? 'manual',
      dota_lobby_region: tourn?.dota_lobby_region ?? '',
      discord_send_lobby_info: tourn?.discord_send_lobby_info ?? false,
      game_type: tourn?.game_type ?? 1,
      game_mode: tourn?.game_mode ?? 'normal',
      lobby_steam_league_id: tourn?.lobby_steam_league_id ?? null,
      captains_draft_time: tourn?.captains_draft_time ?? 10,
      custom_game_name: tourn?.custom_game_name ?? '',
      ...draftSettingsToFormInput(tourn?.draft_options),
    },
  });

  // Update date_played when date or time changes
  useEffect(() => {
    form.setValue(
      'date_played',
      combineDateAndTime(selectedDate, selectedTime),
    );
  }, [selectedDate, selectedTime, form]);

  const currentLeague: LeagueOption | null =
    typeof tourn?.league === 'object' && tourn.league !== null
      ? (tourn.league as LeagueOption)
      : ((leagues as LeagueOption[] | undefined)?.find(
          (l) => l.pk === leagueDefault,
        ) ?? null);
  const {
    options: leagueOptions,
    allowNone,
    locked: leagueLocked,
  } = leagueOptionsFor(currentUser, (leagues ?? []) as LeagueOption[], {
    currentLeague,
    eventOrgPk: tourn?.source_event?.organization_id ?? null,
  });

  const allowed = isEditing ? !!canEdit : canCreateTournament(currentUser);
  if (!allowed) {
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
      const payload: TournamentWritePayload & {
        timezone?: string;
        league_id_write?: number | null;
      } = {
        name: data.name,
        tournament_type: data.tournament_type,
        date_played: data.date_played,
        timezone: data.timezone,
        league_id_write: data.league || null,
        auto_create_hero_drafts: data.auto_create_hero_drafts,
        discord_send_draft_link: data.discord_send_draft_link,
        discord_send_herodraft_link: data.discord_send_herodraft_link,
        game_mode: data.game_mode,
        lobby_steam_league_id: data.lobby_steam_league_id,
        ...(data.game_mode === 'captains_mode' && {
          captains_draft_time: data.captains_draft_time,
        }),
        custom_game_name: data.custom_game_name,
        dota_lobby_mode: data.dota_lobby_mode,
        dota_lobby_launch: data.dota_lobby_launch,
        dota_lobby_region: data.dota_lobby_region.trim(),
        discord_send_lobby_info: data.discord_send_lobby_info,
        draft_options: draftSettingsFormToPatch(data),
      };

      if (isEditing) {
        await updateTournament(tourn.pk!, payload);
        toast.success(`Tournament "${data.name}" updated successfully`);
      } else {
        await createTournament(payload);
        toast.success(`Tournament "${data.name}" created successfully`);
      }

      refreshAfterSave({
        pathname,
        getTournaments,
        queryClient,
        pk: isEditing ? (tourn?.pk ?? undefined) : undefined,
      });
      onSuccess?.();
      form.reset();
    } catch (err: unknown) {
      log.error('Failed to save tournament:', err);
      const title = isEditing
        ? 'Failed to update tournament'
        : 'Failed to create tournament';
      const fieldErrors = fieldErrorsFrom(
        (err as { response?: { data?: unknown } })?.response?.data,
      );
      if (fieldErrors.length > 0) {
        fieldErrors.forEach(({ field, message }) =>
          form.setError(field, { message }),
        );
        setTab(tabForField(fieldErrors[0].field));
        toast.error(title, { description: fieldErrors[0].message });
      } else {
        const errorMessage =
          err instanceof Error ? err.message : 'Unknown error';
        toast.error(title, {
          description: extractApiError(err) ?? errorMessage,
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function onInvalid(errors: FieldErrors<CreateTournamentInput>) {
    const [key, error] = Object.entries(errors)[0] ?? [];
    if (!key) return;
    setTab(tabForField(key));
    toast.error('Please fix the highlighted fields', {
      description:
        typeof error?.message === 'string' ? error.message : undefined,
    });
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit, onInvalid)}
        className="flex min-h-0 flex-1 flex-col"
        data-testid="tournament-form"
      >
        <ScrollArea className="-mx-6 min-h-0 flex-1 px-6">
          <Tabs
            value={tab}
            onValueChange={(v) => setTab(v as FormTab)}
            className="gap-4 p-1"
          >
            <FormTabsList
              className="sticky top-0 z-10 bg-background"
              testIdPrefix="tournament-form"
              tabs={[
                { value: 'general', label: 'General', icon: Trophy },
                { value: 'config', label: 'Config', icon: Settings2 },
                { value: 'discord', label: 'Discord', icon: DiscordIcon },
              ]}
            />

            <TabsContent
              value="general"
              className="mx-auto flex w-full max-w-4xl flex-col gap-4"
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

              <BracketTypeField
                control={form.control}
                label="Tournament Type"
                description={null}
                placeholder="Select tournament type"
                triggerTestId="tournament-type-select"
                itemTestIds={{
                  single_elimination: 'tournament-type-single',
                  double_elimination: 'tournament-type-double',
                  swiss: 'tournament-type-swiss',
                }}
                optionLabels={{ swiss: 'Swiss System' }}
                order={['single_elimination', 'double_elimination', 'swiss']}
              />

              {/* Date & Time Picker */}
              <FormField
                control={form.control}
                name="date_played"
                render={({ field }) => (
                  <FormItem className="flex flex-col">
                    <FormLabel>Tournament Date & Time</FormLabel>
                    <div className="flex flex-wrap gap-2">
                      {/* Date Picker */}
                      <Popover
                        open={calendarOpen}
                        onOpenChange={setCalendarOpen}
                        modal={true}
                      >
                        <PopoverTrigger asChild>
                          <FormControl>
                            <Button
                              variant="outline"
                              className={cn(
                                'pl-3 text-left font-normal',
                                !selectedDate && 'text-muted-foreground',
                              )}
                              data-testid="tournament-date-picker"
                            >
                              {selectedDate ? (
                                format(localDate(selectedDate), 'PPP')
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
                            selected={
                              selectedDate ? localDate(selectedDate) : undefined
                            }
                            onSelect={(date) => {
                              if (date) {
                                setSelectedDate(format(date, 'yyyy-MM-dd'));
                              }
                              setCalendarOpen(false);
                            }}
                            data-testid="tournament-calendar"
                          />
                        </PopoverContent>
                      </Popover>

                      {/* Time Picker */}
                      <Input
                        type="time"
                        value={selectedTime}
                        onChange={(e) => setSelectedTime(e.target.value)}
                        className="w-fit"
                        data-testid="tournament-time-picker"
                      />
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <TimezoneField
                control={form.control}
                showIcon
                description="The timezone in which the tournament will be played"
                triggerTestId="tournament-timezone-select"
                itemTestIdPrefix="tournament-timezone-"
                timezones={TOURNAMENT_TIMEZONES}
                formatLabel={(tz) =>
                  tz === 'UTC' ? 'UTC' : `${formatTimezoneLabel(tz)} (${tz})`
                }
              />

              {/* League Picker */}
              <FormField
                control={form.control}
                name="league"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>League (Optional)</FormLabel>
                    <Select
                      onValueChange={(value) => {
                        const leagueId =
                          value === 'none' ? null : parseInt(value, 10);
                        field.onChange(leagueId);
                        if (leagueId) {
                          const selectedLeague = leagueOptions.find(
                            (l) => l.pk === leagueId,
                          );
                          if (selectedLeague?.timezone) {
                            form.setValue('timezone', selectedLeague.timezone);
                          }
                        }
                      }}
                      value={field.value?.toString() || 'none'}
                      disabled={leagueLocked}
                    >
                      <FormControl>
                        <SelectTrigger
                          className="w-full"
                          data-testid="tournament-league-select"
                        >
                          <SelectValue placeholder="Select a league" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {allowNone && (
                          <SelectItem
                            value="none"
                            data-testid="tournament-league-none"
                          >
                            No League
                          </SelectItem>
                        )}
                        {leagueOptions.map((league) => (
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
            </TabsContent>

            <TabsContent
              value="config"
              className="mx-auto flex w-full max-w-4xl flex-col gap-4"
            >
              <LobbyConfigSection control={form.control} watch={form.watch} />
              <TournamentConfigSection control={form.control} />
              <DraftSettingsSection
                control={form.control}
                showDraftType={false}
                showTimeoutAction={false}
              />
              <DotaLobbyConfigSection
                control={form.control}
                sourceEvent={sourceEvent}
              />
            </TabsContent>

            <TabsContent
              value="discord"
              className="mx-auto flex w-full max-w-4xl flex-col gap-4"
            >
              <DiscordTournamentConfigSection control={form.control} />
            </TabsContent>
          </Tabs>
        </ScrollArea>

        <div className="flex flex-none flex-row justify-end gap-2 pt-4">
          <DialogClose asChild>
            <CancelButton
              type="button"
              disabled={isSubmitting}
              data-testid="tournament-cancel-button"
            >
              Cancel
            </CancelButton>
          </DialogClose>
          <SubmitButton
            loading={isSubmitting}
            loadingText={isEditing ? 'Saving...' : 'Creating...'}
            data-testid="tournament-submit-button"
          >
            {isEditing ? 'Save Changes' : 'Create Tournament'}
          </SubmitButton>
        </div>
      </form>
    </Form>
  );
};
