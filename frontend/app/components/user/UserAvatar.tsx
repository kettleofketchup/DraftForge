import { memo, useMemo } from 'react';
import { SimpleAvatar } from '~/components/ui/simple-avatar';
import { cn } from '~/lib/utils';
import type { UserType, UserClassType, GuildMember } from './types';

/**
 * Flexible user data type that accepts full UserType, GuildMember, or partial data
 * from various sources (e.g., captain objects from serializers, herodraft data)
 */
type UserLike = UserType | GuildMember | {
  pk?: number;
  username?: string;
  nickname?: string | null;
  avatar?: string | null;
  avatarUrl?: string | null;
  discordId?: string | null;
};

export type UserAvatarSize = 'tiny' | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
export type UserAvatarBorder = 'none' | 'primary' | 'muted' | 'captain';

interface UserAvatarProps {
  /** User data - flexible to accept partial data from various sources */
  user?: UserLike;
  /** Or provide URL directly (for pre-computed URLs like avatar_url from events) */
  src?: string;
  /** Predefined sizes */
  size?: UserAvatarSize;
  /** Show online presence indicator */
  showOnline?: boolean;
  /** Whether user is online (requires showOnline=true) */
  online?: boolean;
  /** Border styling variant */
  border?: UserAvatarBorder;
  /** Additional classes */
  className?: string;
  /** Alt text override */
  alt?: string;
  /** Test ID for testing */
  'data-testid'?: string;
}

// Size mappings
const sizeClasses: Record<UserAvatarSize, string> = {
  tiny: 'h-4 w-4',      // 16px - position coverage, inline
  xs: 'h-5 w-5',        // 20px - compact lists, event logs
  sm: 'h-6 w-6',        // 24px - table rows, search results
  md: 'h-8 w-8',        // 32px - default
  lg: 'h-10 w-10',      // 40px - modals, profile headers
  xl: 'h-12 w-12',      // 48px - user cards, prominent
};

// Fallback text sizes for each avatar size
const fallbackTextSizes: Record<UserAvatarSize, string> = {
  tiny: 'text-[7px]',
  xs: 'text-[8px]',
  sm: 'text-[10px]',
  md: 'text-xs',
  lg: 'text-sm',
  xl: 'text-base',
};

// Online indicator sizes
const onlineIndicatorSizes: Record<UserAvatarSize, string> = {
  tiny: 'h-1.5 w-1.5',
  xs: 'h-2 w-2',
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
  lg: 'h-3 w-3',
  xl: 'h-3.5 w-3.5',
};

// Border classes
const borderClasses: Record<UserAvatarBorder, string> = {
  none: '',
  primary: 'ring-2 ring-primary',
  muted: 'border border-background',
  captain: 'ring-2 ring-yellow-500',
};

/**
 * Generate avatar URL with fallback to ui-avatars.com
 * Handles UserType, GuildMember, and partial user data
 */
export const AvatarUrl = (
  user: UserType | GuildMember | UserClassType | UserLike | undefined,
): string => {
  const genUrl = `https://ui-avatars.com/api/?rounded=True&background=random`;
  const discordCdn = `https://cdn.discordapp.com/avatars`;

  if (!user) {
    return `${genUrl}&name=?&length=1`;
  }

  if ('user' in user) {
    // user is GuildMember
    return user.user.avatar
      ? `${discordCdn}/${user.user.id}/${user.user.avatar}`
      : `${genUrl}&name=${encodeURIComponent(
          user.nick || user.user.global_name || user.user.username,
        )}`;
  }

  // Generate fallback URL from username/nickname
  const fallback = `${genUrl}&length=2&name=${encodeURIComponent(
    user.nickname || user.username || '?',
  )}`;

  // Helper to check if URL is a Discord default/embed avatar (not a custom one)
  const isDiscordDefaultAvatar = (url: string) =>
    url.includes('cdn.discordapp.com/embed/avatars/');

  // 1. Use avatarUrl if available (full URL from backend), unless it's a Discord default
  if (user.avatarUrl && !isDiscordDefaultAvatar(user.avatarUrl)) {
    return user.avatarUrl;
  }

  // 2. If avatar is already a full URL and not a Discord default, use it
  if (user.avatar?.startsWith('http') && !isDiscordDefaultAvatar(user.avatar)) {
    return user.avatar;
  }

  // 3. If we have discordId and avatar hash, construct Discord CDN URL
  if (user.discordId && user.avatar) {
    return `${discordCdn}/${user.discordId}/${user.avatar}`;
  }

  // 4. Fall back to generated avatar from username
  return fallback;
};

/**
 * Get display name from user-like object
 */
function getDisplayName(user: UserLike | undefined): string {
  if (!user) return '?';

  if ('user' in user) {
    // GuildMember
    return user.nick || user.user.global_name || user.user.username;
  }

  return user.nickname || user.username || '?';
}

/**
 * Get initials for fallback display
 */
function getInitials(user: UserLike | undefined): string {
  const name = getDisplayName(user);
  if (name === '?') return '?';

  // Return first character uppercase
  return name.charAt(0).toUpperCase();
}

/**
 * Custom comparison for memo - only re-render when avatar-relevant data changes
 */
function arePropsEqual(
  prevProps: UserAvatarProps,
  nextProps: UserAvatarProps
): boolean {
  // Compare primitive props directly
  if (
    prevProps.src !== nextProps.src ||
    prevProps.size !== nextProps.size ||
    prevProps.showOnline !== nextProps.showOnline ||
    prevProps.online !== nextProps.online ||
    prevProps.border !== nextProps.border ||
    prevProps.className !== nextProps.className ||
    prevProps.alt !== nextProps.alt ||
    prevProps['data-testid'] !== nextProps['data-testid']
  ) {
    return false;
  }

  // Compare user objects by avatar-relevant fields only
  const prevUser = prevProps.user;
  const nextUser = nextProps.user;

  if (prevUser === nextUser) return true;
  if (!prevUser || !nextUser) return prevUser === nextUser;

  // For GuildMember
  if ('user' in prevUser && 'user' in nextUser) {
    return (
      prevUser.user.id === nextUser.user.id &&
      prevUser.user.avatar === nextUser.user.avatar &&
      prevUser.nick === nextUser.nick
    );
  }

  // For UserType/UserLike
  if (!('user' in prevUser) && !('user' in nextUser)) {
    return (
      prevUser.pk === nextUser.pk &&
      prevUser.avatar === nextUser.avatar &&
      prevUser.avatarUrl === nextUser.avatarUrl &&
      prevUser.discordId === nextUser.discordId &&
      prevUser.username === nextUser.username &&
      prevUser.nickname === nextUser.nickname
    );
  }

  return false;
}

/**
 * Centralized UserAvatar component with consistent styling, loading states,
 * error handling, and support for online presence indicators.
 */
export const UserAvatar = memo(function UserAvatar({
  user,
  src,
  size = 'md',
  showOnline = false,
  online = false,
  border = 'none',
  className,
  alt,
  'data-testid': testId,
}: UserAvatarProps) {
  // Extract stable keys for memoization
  const isGuildMember = user && 'user' in user;
  const guildUserId = isGuildMember ? user.user.id : undefined;
  const guildUserAvatar = isGuildMember ? user.user.avatar : undefined;
  const guildNick = isGuildMember ? user.nick : undefined;
  const guildUsername = isGuildMember ? user.user.username : undefined;
  const userPk = !isGuildMember ? user?.pk : undefined;
  const userAvatar = !isGuildMember ? user?.avatar : undefined;
  const userAvatarUrl = !isGuildMember ? user?.avatarUrl : undefined;
  const userDiscordId = !isGuildMember ? user?.discordId : undefined;
  const userNickname = !isGuildMember ? user?.nickname : undefined;
  const userUsername = !isGuildMember ? user?.username : undefined;

  // Memoize the image URL - only recompute when avatar-relevant fields change
  const imageUrl = useMemo(
    () => src || (user ? AvatarUrl(user as UserType) : undefined),
    [src, guildUserId, guildUserAvatar, userPk, userAvatar, userAvatarUrl, userDiscordId]
  );

  // Memoize display name for alt and initials
  const displayName = useMemo(
    () => (user ? getDisplayName(user) : '?'),
    [guildNick, guildUsername, userNickname, userUsername]
  );

  // Memoize alt text
  const altText = useMemo(
    () => alt || (user ? displayName : 'User avatar'),
    [alt, user, displayName]
  );

  // Memoize initials
  const initials = useMemo(
    () => (displayName === '?' ? '?' : displayName.charAt(0).toUpperCase()),
    [displayName]
  );

  // Memoize combined className to avoid cn() on every render
  const avatarClassName = useMemo(
    () => cn(sizeClasses[size], borderClasses[border], className),
    [size, border, className]
  );

  const fallbackClassName = useMemo(
    () => cn(fallbackTextSizes[size], 'font-medium'),
    [size]
  );

  return (
    <div className="relative inline-block" data-testid={testId}>
      <SimpleAvatar
        src={imageUrl}
        alt={altText}
        fallback={initials}
        className={avatarClassName}
        fallbackClassName={fallbackClassName}
      />

      {/* Online indicator */}
      {showOnline && (
        <span
          className={cn(
            'absolute bottom-0 right-0 rounded-full border-2 border-background',
            onlineIndicatorSizes[size],
            online ? 'bg-green-500' : 'bg-gray-400'
          )}
          aria-label={online ? 'Online' : 'Offline'}
        />
      )}
    </div>
  );
}, arePropsEqual);

export default UserAvatar;
