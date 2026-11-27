import { CornerUpLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '~/lib/utils';
import { DiscordComponents } from './DiscordComponents';
import { DiscordEmbed } from './DiscordEmbed';
import { DiscordMarkdown } from './DiscordMarkdown';
import { normalizeMessage, type DiscordMessageInput } from './messageInput';
import { usePreviewOptions, type DiscordPreviewOptions } from './timestamps';
import type { DiscordResolver } from './types';

export type DiscordMessageAuthor = {
  name: ReactNode;
  avatar?: ReactNode;
  bot?: boolean;
};

export interface DiscordMessagePreviewProps {
  messages: DiscordMessageInput[];
  author?: DiscordMessageAuthor;
  resolve?: DiscordResolver;
  options?: DiscordPreviewOptions;
  replyTo?: string;
  className?: string;
}

function AuthorHeader({ author }: { author: DiscordMessageAuthor }) {
  const { t } = useTranslation('discordPreview');
  return (
    <div
      data-testid="discord-message-author"
      className="flex items-center gap-2"
    >
      <span className="font-semibold">{author.name}</span>
      {author.bot ? (
        <span className="rounded-sm bg-discord px-1 text-[0.625rem] leading-4 font-semibold text-foreground">
          {t('message.app_tag')}
        </span>
      ) : null}
    </div>
  );
}

export function DiscordMessagePreview({
  messages,
  author,
  resolve,
  options,
  replyTo,
  className,
}: DiscordMessagePreviewProps) {
  const viewerOptions = usePreviewOptions();
  const opts = options ?? viewerOptions;
  return (
    <div
      data-testid="discord-message-preview"
      className={cn(
        'rounded-md border border-border bg-base-900 p-4 text-sm text-foreground',
        className,
      )}
    >
      {replyTo ? (
        <div
          data-testid="discord-reply"
          className="mb-1 flex items-center gap-1 pl-12 text-xs text-muted-foreground"
        >
          <CornerUpLeft aria-hidden className="size-3" />
          <span>{replyTo}</span>
        </div>
      ) : null}
      <div className="flex gap-3">
        {author?.avatar ? (
          <div className="size-10 shrink-0 overflow-hidden rounded-full">
            {author.avatar}
          </div>
        ) : null}
        <div className="min-w-0 flex-1 space-y-3">
          {author ? <AuthorHeader author={author} /> : null}
          {messages.map((raw, i) => {
            const m = normalizeMessage(raw);
            return (
              <div key={i} data-testid="discord-message" className="space-y-1">
                {m.content ? (
                  <DiscordMarkdown
                    text={m.content}
                    resolve={resolve}
                    options={opts}
                  />
                ) : null}
                {m.embeds.map((embed, j) => (
                  <DiscordEmbed
                    key={j}
                    embed={embed}
                    resolve={resolve}
                    options={opts}
                  />
                ))}
                <DiscordComponents
                  components={m.components}
                  resolve={resolve}
                  options={opts}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
