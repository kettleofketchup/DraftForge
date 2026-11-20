import { ArrowDown } from 'lucide-react';
import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { SecondaryButton } from '~/components/ui/buttons';
import { ScrollArea } from '~/components/ui/scroll-area';
import { cn } from '~/lib/utils';
import type { ChatMessage } from '../types';
import { ChatMessageRow } from './ChatMessageRow';

const BOTTOM_SLACK_PX = 24;

export interface ChatLogProps {
  messages: ChatMessage[];
  emptyText: string;
  onHeroClick?: (heroId: number) => void;
  className?: string;
}

export function ChatLog({
  messages,
  emptyText,
  onHeroClick,
  className,
}: ChatLogProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const [hasNewBelow, setHasNewBelow] = useState(false);

  const scrollToBottom = useCallback(() => {
    const el = viewportRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    atBottomRef.current = true;
    setHasNewBelow(false);
  }, []);

  const handleScroll = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_SLACK_PX;
    atBottomRef.current = atBottom;
    if (atBottom) setHasNewBelow(false);
  }, []);

  const lastId = messages[messages.length - 1]?.id;
  useLayoutEffect(() => {
    if (lastId === undefined) return;
    if (atBottomRef.current) scrollToBottom();
    else setHasNewBelow(true);
  }, [lastId, scrollToBottom]);

  return (
    <div className={cn('relative min-h-0', className)}>
      <ScrollArea
        className="h-full"
        viewportProps={{ ref: viewportRef, onScroll: handleScroll }}
      >
        <div
          className="flex flex-col py-1"
          role="log"
          aria-live="polite"
          data-testid="herodraft-chat-log"
        >
          {messages.length === 0 ? (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              {emptyText}
            </p>
          ) : (
            messages.map((m) => (
              <ChatMessageRow
                key={m.id}
                message={m}
                onHeroClick={onHeroClick}
              />
            ))
          )}
        </div>
      </ScrollArea>
      {hasNewBelow && (
        <SecondaryButton
          size="sm"
          className="absolute bottom-2 left-1/2 h-7 -translate-x-1/2 text-xs"
          onClick={scrollToBottom}
          data-testid="herodraft-chat-new-messages"
        >
          New messages
          <ArrowDown className="size-3" />
        </SecondaryButton>
      )}
    </div>
  );
}
