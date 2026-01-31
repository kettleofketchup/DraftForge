// frontend/app/components/herodraft/DraftToasts.tsx
import { DisplayName } from "~/components/user/avatar";
import { UserAvatar } from "~/components/user/UserAvatar";

interface CaptainInfo {
  pk: number;
  username: string;
  nickname: string | null;
  avatar: string | null;
  avatarUrl?: string | null;
  discordId?: string | null;
}

interface CaptainToastProps {
  captain: CaptainInfo | null | undefined;
  message: string;
  messageClassName?: string;
}

/**
 * Toast content showing captain avatar + name + message
 * Used for: connected, disconnected, ready, roll_result
 */
export function CaptainToast({ captain, message, messageClassName }: CaptainToastProps) {
  const captainName = captain ? DisplayName(captain) : "Unknown";

  return (
    <div className="flex items-center gap-2">
      <UserAvatar user={captain || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{captainName}</span>
      <span className={messageClassName}>{message}</span>
    </div>
  );
}

interface HeroActionToastProps {
  captain: CaptainInfo | null | undefined;
  action: "picked" | "banned";
  heroName: string;
  heroIconUrl?: string;
}

/**
 * Toast content showing captain avatar + name + action + hero name + hero icon
 * Used for: hero_selected (picks and bans)
 */
export function HeroActionToast({ captain, action, heroName, heroIconUrl }: HeroActionToastProps) {
  const captainName = captain ? DisplayName(captain) : "Unknown";
  const isBan = action === "banned";

  return (
    <div className="flex items-center gap-2">
      <UserAvatar user={captain || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{captainName}</span>
      <span className={isBan ? "text-red-500 font-semibold" : "text-green-500 font-semibold"}>
        {action}
      </span>
      <span className="font-medium">{heroName}</span>
      {heroIconUrl && (
        <img
          src={heroIconUrl}
          alt={heroName}
          className="w-6 h-6 rounded shrink-0"
        />
      )}
    </div>
  );
}
