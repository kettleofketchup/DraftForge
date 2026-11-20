import { Badge } from '~/components/ui/badge';
import { DisplayName } from '~/components/user/avatar';
import { getHeroName } from '~/lib/dota/heroes';
import { cn } from '~/lib/utils';
import { ChannelBadge } from './ChatMessageRow';
import { PREVIEW_FADE_MS, type PreviewLine } from './chatPreview';

function PreviewBody({ line }: { line: PreviewLine }) {
  const { message } = line;
  if (message.kind === 'text' || message.hero_id === null) {
    return <>: {message.body}</>;
  }
  const isPick = message.kind === 'suggest_pick';
  return (
    <>
      {' '}
      <span className="text-muted-foreground">suggests</span>{' '}
      <Badge
        className={cn(
          'border-transparent px-1.5 text-[10px] font-semibold',
          isPick ? 'bg-pick-surface text-pick' : 'bg-ban-surface text-ban',
        )}
      >
        {isPick ? 'PICK' : 'BAN'}
      </Badge>{' '}
      {getHeroName(message.hero_id)}
    </>
  );
}

export interface ChatPreviewProps {
  lines: PreviewLine[];
  now: number;
}

/** Click-through strip of recent messages while the chat panel is closed. */
export function ChatPreview({ lines, now }: ChatPreviewProps) {
  return (
    <div
      className="pointer-events-none flex flex-col items-start gap-1"
      aria-live="polite"
      data-testid="herodraft-chat-preview"
    >
      {lines.map((line) => (
        <p
          key={line.key}
          className={cn(
            'max-w-full truncate rounded-md bg-card/90 px-2 py-0.5 text-xs shadow-md backdrop-blur',
            'transition-opacity duration-500 motion-reduce:transition-none',
            now >= line.expiresAt - PREVIEW_FADE_MS && 'opacity-0',
          )}
          data-testid="herodraft-chat-preview-line"
        >
          <ChannelBadge channel={line.message.channel} />{' '}
          <span className="font-semibold">
            {DisplayName(line.message.sender)}
          </span>
          {line.count > 1 && (
            <span
              className="ml-1 text-muted-foreground"
              data-testid="herodraft-chat-preview-count"
            >
              ×{line.count}
            </span>
          )}
          <PreviewBody line={line} />
        </p>
      ))}
    </div>
  );
}
