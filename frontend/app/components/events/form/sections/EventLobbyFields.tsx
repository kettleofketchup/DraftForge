import type { ComponentProps } from 'react';
import type { Control, FieldValues } from 'react-hook-form';
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
  'control'
>;

type Props<T extends FieldValues & LobbyFields> = PasswordProps & {
  control: Control<T>;
};

/** The Lobby tab: game mode settings, then hosted lobby and password. */
export function EventLobbyFields<T extends FieldValues & LobbyFields>({
  control,
  ...passwordProps
}: Props<T>) {
  return (
    <div className="flex flex-col gap-4">
      <LobbyConfigSection control={control} />
      <DotaLobbyEventSettings control={control} {...passwordProps} />
    </div>
  );
}
