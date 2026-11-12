import type { Control } from 'react-hook-form';
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
import type { CreateTournamentInput } from '../schemas';

interface Props {
  control: Control<CreateTournamentInput>;
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

/** Tournament settings for dota_lobby-hosted in-game lobbies. */
export function DotaLobbyConfigSection({ control }: Props) {
  return (
    <div className="space-y-3 mt-4" data-testid="config-dota-lobby-section">
      <h3 className="text-sm font-semibold">Dota Lobbies</h3>
      <div className="rounded-md border border-border p-3 space-y-3">
        <FormField
          control={control}
          name="dota_lobby_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Hosted lobbies</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
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
              <Select onValueChange={field.onChange} value={field.value}>
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
      </div>
    </div>
  );
}
