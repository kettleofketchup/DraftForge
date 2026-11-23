import type { ReactNode } from 'react';

import { DisplayName } from '~/components/user/avatar';
import { UserAvatar, type UserAvatarSize } from '~/components/user/UserAvatar';
import { isDiscordMember } from '~/lib/userDisplayName';
import type { SearchableUser } from '~/lib/userSearch';

function handleOf(user: SearchableUser): string | null | undefined {
  return isDiscordMember(user) ? user.user.username : user.username;
}

export interface UserSearchOptionProps {
  user: SearchableUser;
  /** Right-aligned status ("Org Member", "Already added"). */
  badge?: ReactNode;
  size?: UserAvatarSize;
}

/** One search result: avatar, display name, and the @handle when it differs so same-named people can be told apart. */
export function UserSearchOption({
  user,
  badge,
  size = 'sm',
}: UserSearchOptionProps) {
  const name = DisplayName(user);
  const handle = handleOf(user);
  return (
    <>
      <UserAvatar user={user} size={size} />
      <span className="flex min-w-0 flex-col">
        <span className="truncate">{name}</span>
        {handle && handle !== name ? (
          <span className="truncate text-xs text-muted-foreground">
            @{handle}
          </span>
        ) : null}
      </span>
      {badge ? <span className="ml-auto shrink-0">{badge}</span> : null}
    </>
  );
}
