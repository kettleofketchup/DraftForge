import type { Control, FieldValues, UseFormWatch } from 'react-hook-form';
import { GAME_TYPE } from '~/components/game/constants';
import { LobbyPasswordSettings } from '~/components/lobby/LobbyPasswordSettings';
import type { LobbyPasswordMode } from '~/components/lobby/password';
import type { LobbyPasswordInfo } from '~/components/lobby/schemas';
import { DotaLobbyConfigSection } from '~/components/tournament/create/DotaLobbyConfigSection';

/** Fields of dotaLobbyConfigSchema, as the series and event forms hold them. */
interface DotaLobbyEventFields {
  game_type: number;
  dota_lobby_mode?: 'off' | 'manual' | 'auto';
  dota_lobby_launch?: 'manual' | 'auto';
  dota_lobby_region?: string;
  discord_send_lobby_info?: boolean;
  dota_lobby_password_mode?: LobbyPasswordMode;
  dota_lobby_password?: string;
  dota_lobby_password_saved?: boolean;
}

interface Props<T extends FieldValues & DotaLobbyEventFields> {
  control: Control<T>;
  watch: UseFormWatch<T>;
  scope: 'series' | 'event';
  saved?: LobbyPasswordInfo | null;
  followsSeries?: boolean;
  onRegenerate?: () => void;
  regenerating?: boolean;
}

/**
 * Hosted-lobby settings and the lobby password on series and event forms
 * (Dota 2 only). Generated events and their tournaments inherit them.
 */
export function DotaLobbyEventSettings<T extends FieldValues & DotaLobbyEventFields>({
  control: parentControl,
  watch: parentWatch,
  ...passwordProps
}: Props<T>) {
  const control = parentControl as unknown as Control<DotaLobbyEventFields>;
  const watch = parentWatch as unknown as UseFormWatch<DotaLobbyEventFields>;
  if (watch('game_type') !== GAME_TYPE.DOTA2) return null;
  return (
    <div className="space-y-4">
      <DotaLobbyConfigSection control={control} includeLobbyInfo />
      <LobbyPasswordSettings control={control} watch={watch} {...passwordProps} />
    </div>
  );
}
