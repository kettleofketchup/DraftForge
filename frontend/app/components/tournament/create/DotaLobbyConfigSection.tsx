import type { Control, FieldValues } from 'react-hook-form';
import { Link } from 'react-router';
import {
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
/** The fields this section edits, on tournament, event and series forms. */
interface DotaLobbyFields {
  dota_lobby_mode?: 'off' | 'manual' | 'auto';
  dota_lobby_launch?: 'manual' | 'auto';
  dota_lobby_region?: string;
  discord_send_lobby_info?: boolean;
}

interface Props<T extends FieldValues & DotaLobbyFields> {
  control: Control<T>;
  /** Also render the "send lobby info" DM toggle (event and series forms,
   *  which have no tournament Discord tab). */
  includeLobbyInfo?: boolean;
  /** The tournament's event, when it has one: the settings come from it and
   *  are shown read-only. */
  sourceEvent?: { id: number; name: string } | null;
}

const MODE_OPTIONS = [
  { value: 'off', label: 'Off' },
  { value: 'manual', label: 'Manual (staff create each lobby)' },
  { value: 'auto', label: 'Automatic (when both teams are set)' },
] as const;

const LAUNCH_OPTIONS = [
  { value: 'manual', label: 'Staff or lobby chat starts the match' },
  { value: 'auto', label: 'Start when every player is ready' },
] as const;

/** Settings for dota_lobby-hosted in-game lobbies (tournament, event, series). */
export function DotaLobbyConfigSection<T extends FieldValues & DotaLobbyFields>({
  control: parentControl,
  includeLobbyInfo = false,
  sourceEvent = null,
}: Props<T>) {
  const control = parentControl as unknown as Control<DotaLobbyFields>;
  const disabled = sourceEvent != null;
  return (
    <div className="space-y-3 mt-4" data-testid="config-dota-lobby-section">
      <h3 className="text-sm font-semibold">Dota Lobbies</h3>
      <div className="rounded-md border border-border p-3 space-y-3">
        {sourceEvent && (
          <p className="text-sm text-muted-foreground" data-testid="config-dota-lobby-from-event">
            These settings and the lobby password come from the event{' '}
            <Link to={`/events/${sourceEvent.id}`} className="underline">
              {sourceEvent.name}
            </Link>
            . Edit them in the event settings.
          </p>
        )}
        <FormField
          control={control}
          name="dota_lobby_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Hosted lobbies</FormLabel>
              <Select onValueChange={field.onChange} value={field.value} disabled={disabled}>
                <FormControl>
                  <SelectTrigger data-testid="config-dota-lobby-mode">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {MODE_OPTIONS.map((o) => (
                    <SelectItem
                      key={o.value}
                      value={o.value}
                      data-testid={`config-dota-lobby-mode-${o.value}`}
                    >
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                A lobby bot creates each match&apos;s in-game lobby and invites the players.
                Needs a Normal, Captain&apos;s Mode or Turbo game mode.
              </FormDescription>
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="dota_lobby_launch"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Match start</FormLabel>
              <Select onValueChange={field.onChange} value={field.value} disabled={disabled}>
                <FormControl>
                  <SelectTrigger data-testid="config-dota-lobby-launch">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {LAUNCH_OPTIONS.map((o) => (
                    <SelectItem
                      key={o.value}
                      value={o.value}
                      data-testid={`config-dota-lobby-launch-${o.value}`}
                    >
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="dota_lobby_region"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Server region</FormLabel>
              <FormControl>
                <Input
                  placeholder="Service default"
                  data-testid="config-dota-lobby-region"
                  disabled={disabled}
                  {...field}
                />
              </FormControl>
              <FormDescription>
                A region name the lobby service knows, such as us_east. Leave empty for its
                default.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        {includeLobbyInfo && (
          <FormField
            control={control}
            name="discord_send_lobby_info"
            render={({ field }) => (
              <FormItem className="flex items-center gap-3">
                <FormControl>
                  <input
                    type="checkbox"
                    data-testid="config-dota-lobby-send-info"
                    checked={field.value}
                    onChange={field.onChange}
                    disabled={disabled}
                    className="h-4 w-4 rounded border-border accent-primary"
                  />
                </FormControl>
                <div>
                  <FormLabel className="text-sm font-medium cursor-pointer">
                    Send lobby info
                  </FormLabel>
                  <FormDescription>
                    DM players the in-game lobby name, password and side when their lobby is
                    created
                  </FormDescription>
                </div>
              </FormItem>
            )}
          />
        )}
      </div>
    </div>
  );
}
