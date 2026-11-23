import { useWatch, type Control, type FieldValues } from 'react-hook-form';
import { GAME_TYPE } from '~/components/game/constants';
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

/** Field set this section renders. The four event forms (createEventInputSchema,
 *  createSeriesEventInputSchema, editEventFormSchema, editRepeaterSchema) take
 *  these keys from eventTemplateSchema; CreateTournamentSchema declares them
 *  inline. The constraint catches field-name typos in this file. */
interface LobbyFields {
  game_type: number;
  game_mode: string;
  lobby_steam_league_id: number | null;
  captains_draft_time: number;
  custom_game_name: string;
}

interface LobbyConfigSectionProps<T extends FieldValues & LobbyFields> {
  control: Control<T>;
}

const GAME_MODE_LABELS: Record<string, string> = {
  [GameMode.NORMAL]: 'Normal',
  [GameMode.CAPTAINS_MODE]: "Captain's Mode",
  [GameMode.TURBO]: 'Turbo',
  [GameMode.CUSTOM]: 'Custom Lobby',
};

const DOTA_ONLY_MODES: Set<string> = new Set([
  GameMode.CAPTAINS_MODE,
  GameMode.TURBO,
]);

export function LobbyConfigSection<T extends FieldValues & LobbyFields>({
  control: parentControl,
}: LobbyConfigSectionProps<T>) {
  // Narrow once: T extends LobbyFields, so all this section's field references
  // are sound. Catches typo'd `name=`s in the JSX below.
  const control = parentControl as unknown as Control<LobbyFields>;

  const gameType = useWatch({ control, name: 'game_type' });
  const gameMode = useWatch({ control, name: 'game_mode' });
  const isDota = gameType === GAME_TYPE.DOTA2;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold">Game lobby</h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField
          control={control}
          name="game_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Game Mode</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger
                    className="w-full"
                    data-testid="lobby-config-game-mode"
                  >
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {Object.entries(GAME_MODE_LABELS)
                    .filter(([key]) => isDota || !DOTA_ONLY_MODES.has(key))
                    .map(([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
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
                    data-testid="lobby-config-steam-league-id"
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
                  data-testid="lobby-config-draft-time"
                  {...field}
                  onChange={(e) => {
                    const seconds = parseInt(e.target.value, 10);
                    field.onChange(
                      Number.isNaN(seconds) ? 10 : Math.max(1, seconds),
                    );
                  }}
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
                <Input
                  placeholder="e.g. Dota 12v12"
                  data-testid="lobby-config-custom-game-name"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}
