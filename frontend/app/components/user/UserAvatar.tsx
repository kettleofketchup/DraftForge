import { memo, useMemo } from 'react';
import { SimpleAvatar } from '~/components/ui/simple-avatar';
import { useDisplayOrgId } from '~/lib/displayOrg';
import {
  isDiscordMember,
  mergeCachedUser,
  resolveDisplayName,
  type UserRef,
  userRefPk,
} from '~/lib/userDisplayName';
import { cn } from '~/lib/utils';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { GuildMember, UserClassType, UserType } from './types';

/**
 * Flexible user data type that accepts full UserType, GuildMember, or partial data
 * from various sources (e.g., captain objects from serializers, herodraft data)
 */
type UserLike =
  | UserType
  | GuildMember
  | (UserRef & { nickname?: string | null });

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
  /** Name for the initials and alt text when there is no user (e.g. a team without a captain) */
  fallbackName?: string;
  /** Test ID for testing */
  'data-testid'?: string;
}

const sizeClasses: Record<UserAvatarSize, string> = {
  tiny: 'h-4 w-4', // 16px - position coverage, inline
  xs: 'h-5 w-5', // 20px - compact lists, event logs
  sm: 'h-6 w-6', // 24px - table rows, search results
  md: 'h-8 w-8', // 32px - default
  lg: 'h-10 w-10', // 40px - modals, profile headers
  xl: 'h-12 w-12', // 48px - user cards, prominent
};

const fallbackTextSizes: Record<UserAvatarSize, string> = {
  tiny: 'text-[7px]',
  xs: 'text-[8px]',
  sm: 'text-[10px]',
  md: 'text-xs',
  lg: 'text-sm',
  xl: 'text-base',
};

const onlineIndicatorSizes: Record<UserAvatarSize, string> = {
  tiny: 'h-1.5 w-1.5',
  xs: 'h-2 w-2',
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
  lg: 'h-3 w-3',
  xl: 'h-3.5 w-3.5',
};

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

  // Guard against raw PKs (numbers) from unhydrated data
  if (typeof user !== 'object') {
    return `${genUrl}&name=?&length=1`;
  }

  if (isDiscordMember(user)) {
    const member = user as GuildMember;
    return member.user.avatar
      ? `${discordCdn}/${member.user.id}/${member.user.avatar}`
      : `${genUrl}&name=${encodeURIComponent(resolveDisplayName(member))}`;
  }
  const ref = user as UserRef;

  const fallback = `${genUrl}&length=2&name=${encodeURIComponent(
    ref.discordNickname || ref.username || '?',
  )}`;

  // Helper to check if URL is a Discord default/embed avatar (not a custom one)
  const isDiscordDefaultAvatar = (url: string) =>
    url.includes('cdn.discordapp.com/embed/avatars/');

  // 1. Use avatarUrl if available (full URL from backend), unless it's a Discord default
  if (ref.avatarUrl && !isDiscordDefaultAvatar(ref.avatarUrl)) {
    return ref.avatarUrl;
  }

  // 2. If avatar is already a full URL and not a Discord default, use it
  if (ref.avatar?.startsWith('http') && !isDiscordDefaultAvatar(ref.avatar)) {
    return ref.avatar;
  }

  // 3. If we have discordId and avatar hash, construct Discord CDN URL
  if (ref.discordId && ref.avatar) {
    return `${discordCdn}/${ref.discordId}/${ref.avatar}`;
  }

  // 4. Fall back to the generated avatar
  return fallback;
};

/**
 * Custom comparison for memo - only re-render when avatar-relevant data changes
 */
function arePropsEqual(
  prevProps: UserAvatarProps,
  nextProps: UserAvatarProps,
): boolean {
  if (
    prevProps.src !== nextProps.src ||
    prevProps.size !== nextProps.size ||
    prevProps.showOnline !== nextProps.showOnline ||
    prevProps.online !== nextProps.online ||
    prevProps.border !== nextProps.border ||
    prevProps.className !== nextProps.className ||
    prevProps.alt !== nextProps.alt ||
    prevProps.fallbackName !== nextProps.fallbackName ||
    prevProps['data-testid'] !== nextProps['data-testid']
  ) {
    return false;
  }

  // Compare user objects by avatar-relevant fields only
  const prevUser = prevProps.user;
  const nextUser = nextProps.user;

  if (prevUser === nextUser) return true;
  if (!prevUser || !nextUser) return prevUser === nextUser;

  // Guard against raw PKs
  if (typeof prevUser !== 'object' || typeof nextUser !== 'object')
    return false;

  const prevMember = isDiscordMember(prevUser);
  if (prevMember !== isDiscordMember(nextUser)) return false;

  if (prevMember) {
    const a = prevUser as GuildMember;
    const b = nextUser as GuildMember;
    return (
      a.user.id === b.user.id &&
      a.user.avatar === b.user.avatar &&
      a.user.username === b.user.username &&
      a.user.global_name === b.user.global_name &&
      a.nick === b.nick
    );
  }

  const a = prevUser as UserRef;
  const b = nextUser as UserRef;
  return (
    userRefPk(a) === userRefPk(b) &&
    a.avatar === b.avatar &&
    a.avatarUrl === b.avatarUrl &&
    a.discordId === b.discordId &&
    a.username === b.username &&
    a.nickname === b.nickname &&
    a.discordNickname === b.discordNickname &&
    a.guildNickname === b.guildNickname &&
    a.orgNicknames === b.orgNicknames
  );
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
  fallbackName,
  'data-testid': testId,
}: UserAvatarProps) {
  const pk = userRefPk(user);
  const cached = useUserCacheStore((s) =>
    pk != null ? s.entities[pk] : undefined,
  );
  const orgId = useDisplayOrgId();

  const imageUrl = useMemo(() => {
    if (src) return src;
    if (!user || typeof user !== 'object') return undefined;
    if (isDiscordMember(user)) return AvatarUrl(user);
    return AvatarUrl(mergeCachedUser(user as UserRef, cached));
  }, [src, user, cached]);

  const displayName = useMemo(
    () =>
      user && typeof user === 'object'
        ? resolveDisplayName(user as UserRef, { orgId, cached: cached ?? null })
        : fallbackName?.trim() || '?',
    [user, cached, orgId, fallbackName],
  );

  const altText = useMemo(
    () => alt || (user || fallbackName ? displayName : 'User avatar'),
    [alt, user, fallbackName, displayName],
  );

  const initials = useMemo(
    () => (displayName === '?' ? '?' : displayName.charAt(0).toUpperCase()),
    [displayName],
  );

  // Memoize combined className to avoid cn() on every render
  const avatarClassName = useMemo(
    () => cn(sizeClasses[size], borderClasses[border], className),
    [size, border, className],
  );

  const fallbackClassName = useMemo(
    () => cn(fallbackTextSizes[size], 'font-medium'),
    [size],
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
            online ? 'bg-green-500' : 'bg-gray-400',
          )}
          aria-label={online ? 'Online' : 'Offline'}
        />
      )}
    </div>
  );
}, arePropsEqual);

export default UserAvatar;
