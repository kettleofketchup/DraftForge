import React, { useCallback } from 'react';
import { ConfirmButton } from '~/components/ui/buttons';
import type { DiscordSearchResult } from '~/components/api/api';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { cn } from '~/lib/utils';

interface DiscordMemberStripProps {
  member: DiscordSearchResult;
  /** Accepts member as argument — DO NOT use inline arrows in parent */
  onAdd: (member: DiscordSearchResult) => void;
  disabled: boolean;
  disabledLabel?: string;
  adding?: boolean;
}

export const DiscordMemberStrip = React.memo(function DiscordMemberStrip({
  member,
  onAdd,
  disabled,
  disabledLabel,
  adding,
}: DiscordMemberStripProps) {
  const displayName = DisplayName({
    nickname: member.nick,
    username: member.user.global_name || member.user.username,
  });
  const subtitle =
    member.nick || member.user.global_name
      ? member.user.username
      : undefined;

  const handleClick = useCallback(() => onAdd(member), [onAdd, member]);

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg p-1 transition-colors',
        'border border-border/50',
        'bg-muted/20 hover:bg-muted/40',
        disabled && 'opacity-50',
      )}
    >
      {/* Avatar */}
      <UserAvatar
        user={{
          nickname: member.nick ?? member.user.global_name,
          username: member.user.username,
          avatar: member.user.avatar,
          discordId: member.user.id,
        }}
        size="md"
        className="shrink-0"
      />

      {/* Name */}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-medium text-foreground">
          {displayName}
        </span>
        {subtitle && (
          <span className="truncate text-xs text-muted-foreground">
            {subtitle}
          </span>
        )}
      </div>

      {/* Site account badge */}
      {member.has_site_account && (
        <span className="shrink-0 text-xs text-muted-foreground">
          Linked
        </span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Action */}
      <div className="shrink-0">
        {disabled ? (
          <span className="text-xs text-muted-foreground">
            {disabledLabel || 'Added'}
          </span>
        ) : (
          <ConfirmButton
            variant="success"
            size="sm"
            depth={false}
            onClick={handleClick}
            loading={adding}
          >
            +
          </ConfirmButton>
        )}
      </div>
    </div>
  );
});
