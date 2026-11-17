import type { ComponentProps } from 'react';
import type { Control, FieldValues, UseFormWatch } from 'react-hook-form';
import { DotaLobbyEventSettings } from '../../DotaLobbyEventSettings';
import { LobbyConfigSection } from '../../LobbyConfigSection';

type LobbyFields = {
  game_type: number;
  game_mode: string;
  lobby_steam_league_id: number | null;
  captains_draft_time: number;
  custom_game_name: string;
};

type PasswordProps = Omit<
  ComponentProps<typeof DotaLobbyEventSettings>,
  'control' | 'watch'
>;

type Props<T extends FieldValues & LobbyFields> = PasswordProps & {
  control: Control<T>;
  watch: UseFormWatch<T>;
};

/** The Lobby tab: game mode settings, then hosted lobby and password. */
export function EventLobbyFields<T extends FieldValues & LobbyFields>({
  control,
  watch,
  ...passwordProps
}: Props<T>) {
  return (
    <div className="flex flex-col gap-4">
      <LobbyConfigSection control={control} watch={watch} />
      <DotaLobbyEventSettings
        control={control}
        watch={watch}
        {...passwordProps}
      />
    </div>
  );
}
