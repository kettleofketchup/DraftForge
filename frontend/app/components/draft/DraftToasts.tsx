// frontend/app/components/draft/DraftToasts.tsx
import { AvatarUrl, DisplayName } from "~/components/user/avatar";
import { Avatar, AvatarFallback, AvatarImage } from "~/components/ui/avatar";
import type { UserType } from "~/index";

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
