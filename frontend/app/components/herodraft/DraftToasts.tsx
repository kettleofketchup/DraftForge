// frontend/app/components/herodraft/DraftToasts.tsx
import { UserAvatar } from '~/components/user/UserAvatar';
import { displayNameById, resolveDisplayName } from '~/lib/userDisplayName';

interface CaptainInfo {
  pk: number;
  username: string | null;
  discordNickname?: string | null;
  avatar: string | null;
  avatarUrl?: string | null;
  discordId?: string | null;
}

function captainDisplayName(
  captain: CaptainInfo | null | undefined,
  orgId: number | null,
): string {
  if (!captain) return 'Unknown';
  return displayNameById(captain.pk, resolveDisplayName(captain), orgId);
}

interface CaptainToastProps {
  captain: CaptainInfo | null | undefined;
  message: string;
  messageClassName?: string;
  orgId: number | null;
}

/**
 * Toast content showing captain avatar + name + message
 * Used for: connected, disconnected, ready, roll_result
 */
export function CaptainToast({
  captain,
  message,
  messageClassName,
  orgId,
}: CaptainToastProps) {
  const captainName = captainDisplayName(captain, orgId);

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
  action: 'picked' | 'banned';
  heroName: string;
  heroIconUrl?: string;
  orgId: number | null;
}

/**
 * Toast content showing captain avatar + name + action + hero name + hero icon
 * Used for: hero_selected (picks and bans)
 */
export function HeroActionToast({
  captain,
  action,
  heroName,
  heroIconUrl,
  orgId,
}: HeroActionToastProps) {
  const captainName = captainDisplayName(captain, orgId);
  const isBan = action === 'banned';

  return (
    <div className="flex items-center gap-2">
      <UserAvatar user={captain || undefined} size="sm" className="shrink-0" />
      <span className="font-medium">{captainName}</span>
      <span
        className={
          isBan ? 'text-red-500 font-semibold' : 'text-green-500 font-semibold'
        }
      >
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
