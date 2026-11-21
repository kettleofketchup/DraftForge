import { memo } from 'react';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { getHeroIcon, getHeroName } from '~/lib/dota/heroes';
import { cn } from '~/lib/utils';
import type { ChatMessage } from '../types';

export interface ChatMessageRowProps {
  message: ChatMessage;
  onHeroClick?: (heroId: number) => void;
}

export function ChannelBadge({ channel }: { channel: 'team' | 'all' }) {
  return (
    <Badge
      className={cn(
        'border-transparent px-1.5 text-[10px] font-semibold',
        channel === 'team'
          ? 'bg-info/20 text-info'
          : 'bg-warning/20 text-warning',
      )}
    >
      {channel === 'team' ? 'TEAM' : 'ALL'}
    </Badge>
  );
}

function SuggestionBody({
  message,
  onHeroClick,
}: {
  message: ChatMessage & { hero_id: number };
  onHeroClick?: (heroId: number) => void;
}) {
  const isPick = message.kind === 'suggest_pick';
  const heroName = getHeroName(message.hero_id);
  return (
    <SecondaryButton
      size="sm"
      className="h-auto gap-1.5 px-1.5 py-0.5 text-xs"
      onClick={() => onHeroClick?.(message.hero_id)}
      data-testid={`herodraft-chat-suggestion-${message.id}`}
    >
      <span className="text-muted-foreground">suggests</span>
      <Badge
        className={cn(
          'border-transparent px-1.5 text-[10px] font-semibold',
          isPick ? 'bg-pick-surface text-pick' : 'bg-ban-surface text-ban',
        )}
      >
        {isPick ? 'PICK' : 'BAN'}
      </Badge>
      <img
        src={getHeroIcon(message.hero_id)}
        alt=""
        className="size-5 rounded-sm object-cover"
      />
      <span>{heroName}</span>
    </SecondaryButton>
  );
}

export const ChatMessageRow = memo(function ChatMessageRow({
  message,
  onHeroClick,
}: ChatMessageRowProps) {
  const name = DisplayName(message.sender);
  return (
    <div
      className="flex items-start gap-2 px-2 py-1 text-sm"
      data-testid={`herodraft-chat-message-${message.id}`}
      data-channel={message.channel}
      data-kind={message.kind}
      data-hero-id={message.hero_id ?? undefined}
    >
      <ChannelBadge channel={message.channel} />
      <UserAvatar user={message.sender} size="xs" className="shrink-0" />
      <div className="min-w-0 flex-1 break-words">
        <span className="font-semibold">{name}</span>
        {message.kind !== 'text' && message.hero_id !== null ? (
          <>
            {' '}
            <SuggestionBody
              message={message as ChatMessage & { hero_id: number }}
              onHeroClick={onHeroClick}
            />
          </>
        ) : (
          <span className="whitespace-pre-wrap">: {message.body}</span>
        )}
      </div>
    </div>
  );
});
