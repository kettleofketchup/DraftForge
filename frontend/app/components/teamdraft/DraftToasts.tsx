// frontend/app/components/draft/DraftToasts.tsx
import {
  cachedUserName,
  type NameResolver,
} from '~/components/teamdraft/eventMessages';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserType } from '~/index';
import type { PlayerPickedPayload } from '~/types/draftEvent';

/**
 * Truncate a string to maxLength characters with ellipsis
 */
function truncateName(name: string, maxLength: number = 12): string {
  if (name.length <= maxLength) return name;
  return name.slice(0, maxLength - 1) + '…';
}

interface PlayerPickedToastProps {
  payload: PlayerPickedPayload;
  name?: NameResolver;
}

/**
 * Toast content for player_picked events from WebSocket
 * Format: [Captain Avatar] Captain Name picked [Player Avatar] Player Name (Pick N)
 */
export function PlayerPickedToast({
  payload,
  name = cachedUserName,
}: PlayerPickedToastProps) {
  const captainName = name(payload.captain_id, payload.captain_name);
  const pickedName = name(payload.picked_id, payload.picked_name);

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <UserAvatar
        src={payload.captain_avatar_url || undefined}
        user={{ username: captainName }}
        size="xs"
        className="shrink-0"
      />
      <span className="font-medium truncate max-w-[80px]" title={captainName}>
        {truncateName(captainName)}
      </span>
      <span className="text-green-500 font-semibold">picked</span>
      <UserAvatar
        src={payload.picked_avatar_url || undefined}
        user={{ username: pickedName }}
        size="xs"
        className="shrink-0"
      />
      <span className="font-medium truncate max-w-[80px]" title={pickedName}>
        {truncateName(pickedName)}
      </span>
      <span className="text-muted-foreground text-sm">
        (Pick {payload.pick_number})
      </span>
    </div>
  );
}

interface PlayerPickToastProps {
  captain: UserType | null | undefined;
  player: UserType | null | undefined;
}

/**
 * Toast content showing captain picking a player
 * Format: [Captain Avatar] Captain Name picked [Player Avatar] Player Name
 */
export function PlayerPickToast({ captain, player }: PlayerPickToastProps) {
  const captainName = captain ? DisplayName(captain) : 'Unknown';
  const playerName = player ? DisplayName(player) : 'Unknown';

  return (
    <div className="flex items-center gap-2">
      <UserAvatar user={captain || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{captainName}</span>
      <span className="text-green-500 font-semibold">picked</span>
      <UserAvatar user={player || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{playerName}</span>
    </div>
  );
}

interface DoublePickToastProps {
  captain: UserType | null | undefined;
}

/**
 * Toast for when a captain gets a double pick in shuffle draft
 */
export function DoublePickToast({ captain }: DoublePickToastProps) {
  const captainName = captain ? DisplayName(captain) : 'Unknown';

  return (
    <div className="flex items-center gap-2">
      <UserAvatar user={captain || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{captainName}</span>
      <span className="text-orange-500 font-semibold">
        gets double pick! 🔥
      </span>
    </div>
  );
}

interface CaptainTurnToastProps {
  captain: UserType | null | undefined;
}

/**
 * Toast for when it's a captain's turn to pick
 */
export function CaptainTurnToast({ captain }: CaptainTurnToastProps) {
  const captainName = captain ? DisplayName(captain) : 'Unknown';

  return (
    <div className="flex items-center gap-2">
      <UserAvatar user={captain || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{captainName}</span>
      <span className="text-blue-500">is now picking...</span>
    </div>
  );
}
