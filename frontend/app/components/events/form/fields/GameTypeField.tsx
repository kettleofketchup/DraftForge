import {
  useFormContext,
  type Control,
  type FieldValues,
} from 'react-hook-form';
import { GAME_TYPE } from '~/components/game/constants';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { GameMode } from '../../schemas';

export interface GameTypeFields {
  game_type: number;
  people_per_team: number;
  game_mode: string;
  lobby_steam_league_id?: number | null;
}

interface Props<T extends FieldValues & GameTypeFields> {
  control: Control<T>;
  testId: string;
  /** Clear lobby_steam_league_id when leaving Dota 2. */
  resetLobbyLeague?: boolean;
}

export function GameTypeField<T extends FieldValues & GameTypeFields>({
  control: parentControl,
  testId,
  resetLobbyLeague = true,
}: Props<T>) {
  const control = parentControl as unknown as Control<GameTypeFields>;
  const { setValue, getValues } = useFormContext<GameTypeFields>();
  return (
    <FormField
      control={control}
      name="game_type"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Game</FormLabel>
          <Select
            onValueChange={(val) => {
              const gameType = parseInt(val, 10);
              field.onChange(gameType);
              setValue(
                'people_per_team',
                gameType === GAME_TYPE.DEADLOCK ? 6 : 5,
              );
              if (gameType !== GAME_TYPE.DOTA2) {
                const mode = getValues('game_mode');
                if (
                  mode === GameMode.CAPTAINS_MODE ||
                  mode === GameMode.TURBO
                ) {
                  setValue('game_mode', GameMode.NORMAL);
                }
                if (resetLobbyLeague) setValue('lobby_steam_league_id', null);
              }
            }}
            value={field.value?.toString()}
          >
            <FormControl>
              <SelectTrigger data-testid={testId} className="w-full">
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              <SelectItem value="1" data-testid={`${testId}-option-1`}>
                Dota 2
              </SelectItem>
              <SelectItem value="2" data-testid={`${testId}-option-2`}>
                Deadlock
              </SelectItem>
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
