// frontend/app/components/draft/DraftToasts.tsx
import { AvatarUrl, DisplayName } from "~/components/user/avatar";
import { Avatar, AvatarFallback, AvatarImage } from "~/components/ui/avatar";
import type { UserType } from "~/index";
import type { PlayerPickedPayload } from "~/types/draftEvent";

/**
 * Truncate a string to maxLength characters with ellipsis
 */
function truncateName(name: string, maxLength: number = 12): string {
  if (name.length <= maxLength) return name;
  return name.slice(0, maxLength - 1) + '…';
}

interface PlayerPickedToastProps {
  payload: PlayerPickedPayload;
}

/**
 * Toast content for player_picked events from WebSocket
 * Format: [Captain Avatar] Captain Name picked [Player Avatar] Player Name (Pick N)
 */
export function PlayerPickedToast({ payload }: PlayerPickedToastProps) {
  const captainInitial = payload.captain_name?.charAt(0).toUpperCase() || '?';
  const pickedInitial = payload.picked_name?.charAt(0).toUpperCase() || '?';

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Avatar className="w-5 h-5 shrink-0">
        <AvatarImage src={payload.captain_avatar_url || undefined} alt="" />
        <AvatarFallback className="text-[10px]">{captainInitial}</AvatarFallback>
      </Avatar>
      <span className="font-medium truncate max-w-[80px]" title={payload.captain_name}>
        {truncateName(payload.captain_name)}
      </span>
      <span className="text-green-500 font-semibold">picked</span>
      <Avatar className="w-5 h-5 shrink-0">
        <AvatarImage src={payload.picked_avatar_url || undefined} alt="" />
        <AvatarFallback className="text-[10px]">{pickedInitial}</AvatarFallback>
      </Avatar>
      <span className="font-medium truncate max-w-[80px]" title={payload.picked_name}>
        {truncateName(payload.picked_name)}
      </span>
      <span className="text-muted-foreground text-sm">(Pick {payload.pick_number})</span>
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
  const captainAvatarUrl = captain ? AvatarUrl(captain) : undefined;
  const captainName = captain ? DisplayName(captain) : "Unknown";
  const playerAvatarUrl = player ? AvatarUrl(player) : undefined;
  const playerName = player ? DisplayName(player) : "Unknown";

  return (
    <div className="flex items-center gap-2">
      <Avatar className="w-6 h-6 shrink-0">
        <AvatarImage src={captainAvatarUrl} alt="" />
        <AvatarFallback className="text-xs">{captainName.charAt(0).toUpperCase()}</AvatarFallback>
      </Avatar>
      <span className="font-medium">{captainName}</span>
      <span className="text-green-500 font-semibold">picked</span>
      <Avatar className="w-6 h-6 shrink-0">
        <AvatarImage src={playerAvatarUrl} alt="" />
        <AvatarFallback className="text-xs">{playerName.charAt(0).toUpperCase()}</AvatarFallback>
      </Avatar>
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
  const captainAvatarUrl = captain ? AvatarUrl(captain) : undefined;
  const captainName = captain ? DisplayName(captain) : "Unknown";

  return (
    <div className="flex items-center gap-2">
      <Avatar className="w-6 h-6 shrink-0">
        <AvatarImage src={captainAvatarUrl} alt="" />
        <AvatarFallback className="text-xs">{captainName.charAt(0).toUpperCase()}</AvatarFallback>
      </Avatar>
      <span className="font-medium">{captainName}</span>
      <span className="text-orange-500 font-semibold">gets double pick! 🔥</span>
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
  const captainAvatarUrl = captain ? AvatarUrl(captain) : undefined;
  const captainName = captain ? DisplayName(captain) : "Unknown";

  return (
    <div className="flex items-center gap-2">
      <Avatar className="w-6 h-6 shrink-0">
        <AvatarImage src={captainAvatarUrl} alt="" />
        <AvatarFallback className="text-xs">{captainName.charAt(0).toUpperCase()}</AvatarFallback>
      </Avatar>
      <span className="font-medium">{captainName}</span>
      <span className="text-blue-500">is now picking...</span>
    </div>
  );
}
