import type { Control, FieldValues, UseFormWatch } from 'react-hook-form';
import {
  FormControl,
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
import { GameMode } from './schemas';
import { GAME_TYPE } from '~/components/game/constants';

/** Field set this section renders. Not extracted as a zod sub-schema (yet) —
 *  these keys are inline on createEventInputSchema, editEventSchema,
 *  editRepeaterSchema. The constraint catches field-name typos in this file
 *  without forcing a schema refactor across all four parent forms. */
interface LobbyFields {
  game_type: number;
  game_mode: string;
  lobby_steam_league_id: number | null;
  captains_draft_time: number;
  custom_game_name: string;
}

interface LobbyConfigSectionProps<T extends FieldValues & LobbyFields> {
  control: Control<T>;
  watch: UseFormWatch<T>;
}

const GAME_MODE_LABELS: Record<string, string> = {
  [GameMode.NORMAL]: 'Normal',
  [GameMode.CAPTAINS_MODE]: "Captain's Mode",
  [GameMode.TURBO]: 'Turbo',
  [GameMode.CUSTOM]: 'Custom Lobby',
};

const DOTA_ONLY_MODES: Set<string> = new Set([GameMode.CAPTAINS_MODE, GameMode.TURBO]);

export function LobbyConfigSection<T extends FieldValues & LobbyFields>({
  control: parentControl,
  watch: parentWatch,
}: LobbyConfigSectionProps<T>) {
  // Narrow once: T extends LobbyFields, so all this section's field references
  // are sound. Catches typo'd `name=`s in the JSX below.
  const control = parentControl as unknown as Control<LobbyFields>;
  const watch = parentWatch as unknown as UseFormWatch<LobbyFields>;

  const gameType = watch('game_type');
  const gameMode = watch('game_mode');
  const isDota = gameType === GAME_TYPE.DOTA2;

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium text-muted-foreground">Lobby & Tournament Config</h4>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField
          control={control}
          name="game_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Game Mode</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
              >
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {Object.entries(GAME_MODE_LABELS)
                    .filter(([key]) => isDota || !DOTA_ONLY_MODES.has(key))
                    .map(([val, label]) => (
                      <SelectItem key={val} value={val}>{label}</SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        {isDota && (
          <FormField
            control={control}
            name="lobby_steam_league_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Steam League ID</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="Optional"
                    value={field.value ?? ''}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10);
                      field.onChange(Number.isNaN(v) ? null : v);
                    }}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}
      </div>

      {gameMode === GameMode.CAPTAINS_MODE && (
        <FormField
          control={control}
          name="captains_draft_time"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Draft Time (seconds)</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  min={1}
                  {...field}
                  onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 10)}
                />
              </FormControl>
              <p className="text-xs text-muted-foreground">
                Seconds per pick in Captain's Mode draft
              </p>
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {gameMode === GameMode.CUSTOM && (
        <FormField
          control={control}
          name="custom_game_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Custom Game Name</FormLabel>
              <FormControl>
                <Input placeholder="e.g. Dota 12v12" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}
