import type { CSSProperties, ReactNode } from 'react';
import { cn } from '~/lib/utils';
import { discordColorHex } from './colors';
import { DiscordMarkdown } from './DiscordMarkdown';
import type { EmbedFieldInput, EmbedInput } from './messageInput';
import { safeHref, safeImageSrc } from './safeHref';
import {
  formatDiscordTimestamp,
  usePreviewOptions,
  type DiscordPreviewOptions,
} from './timestamps';
import type { DiscordResolver } from './types';

const ROW_COLS = [
  '',
  'grid-cols-1',
  'grid-cols-1 @xs:grid-cols-2',
  'grid-cols-1 @xs:grid-cols-2 @sm:grid-cols-3',
] as const;
const LINK = 'hover:underline';

export function groupEmbedFields(
  fields: EmbedFieldInput[],
): EmbedFieldInput[][] {
  const rows: EmbedFieldInput[][] = [];
  let current: EmbedFieldInput[] = [];
  for (const field of fields) {
    if (field.inline && current.length < 3) {
      current.push(field);
      continue;
    }
    if (current.length) rows.push(current);
    if (field.inline) {
      current = [field];
    } else {
      rows.push([field]);
      current = [];
    }
  }
  if (current.length) rows.push(current);
  return rows;
}

function MaybeLink({
  href,
  className,
  children,
}: {
  href?: string | null;
  className?: string;
  children: ReactNode;
}) {
  const safe = safeHref(href ?? undefined);
  if (!safe) return <span className={className}>{children}</span>;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cn(className, LINK)}
    >
      {children}
    </a>
  );
}

function SmallImage({ url }: { url?: string | null }) {
  const src = safeImageSrc(url ?? undefined);
  if (!src) return null;
  return (
    <img
      src={src}
      alt=""
      referrerPolicy="no-referrer"
      loading="lazy"
      className="size-5 rounded-full object-cover"
    />
  );
}

function embedTimestamp(
  iso: string | null | undefined,
  options: DiscordPreviewOptions,
): string | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return null;
  return formatDiscordTimestamp(Math.floor(ms / 1000), 'f', options);
}

export function DiscordEmbed({
  embed,
  resolve,
  options,
}: {
  embed: EmbedInput;
  resolve?: DiscordResolver;
  options?: DiscordPreviewOptions;
}) {
  const viewerOptions = usePreviewOptions();
  const opts = options ?? viewerOptions;
  const hex = discordColorHex(embed.color);
  const thumbnail = safeImageSrc(embed.thumbnail?.url ?? undefined);
  const image = safeImageSrc(embed.image?.url ?? undefined);
  const timestamp = embedTimestamp(embed.timestamp, opts);
  const rows = groupEmbedFields(embed.fields ?? []);
  const md = (text: string, className?: string) => (
    <DiscordMarkdown
      text={text}
      resolve={resolve}
      options={opts}
      className={className}
    />
  );

  return (
    <article
      data-testid="discord-embed"
      style={hex ? ({ '--embed-color': hex } as CSSProperties) : undefined}
      className="mt-1 flex max-w-lg overflow-hidden rounded-md bg-base-800"
    >
      <div
        aria-hidden
        className={cn(
          'w-1 shrink-0',
          hex ? 'bg-(--embed-color)' : 'bg-base-700',
        )}
      />
      <div className="flex min-w-0 flex-1 gap-4 py-2 pr-4 pl-3">
        <div className="@container min-w-0 flex-1 space-y-2">
          {embed.author ? (
            <div className="flex items-center gap-2 text-sm font-semibold">
              <SmallImage url={embed.author.icon_url} />
              <MaybeLink href={embed.author.url}>{embed.author.name}</MaybeLink>
            </div>
          ) : null}
          {embed.title ? (
            <div className="font-semibold">
              <MaybeLink
                href={embed.url}
                className={embed.url ? 'text-info' : undefined}
              >
                {embed.title}
              </MaybeLink>
            </div>
          ) : null}
          {embed.description ? md(embed.description, 'text-sm') : null}
          {rows.map((row, i) => (
            <div
              key={i}
              data-testid="discord-embed-field-row"
              className={cn('grid gap-2', ROW_COLS[row.length])}
            >
              {row.map((field, j) => (
                <div key={j} className="min-w-0 text-sm">
                  <div className="font-semibold break-normal">{field.name}</div>
                  {md(field.value, 'break-normal')}
                </div>
              ))}
            </div>
          ))}
          {image ? (
            <img
              src={image}
              alt=""
              referrerPolicy="no-referrer"
              loading="lazy"
              className="max-h-80 rounded-md object-contain"
            />
          ) : null}
          {embed.footer || timestamp ? (
            <div
              data-testid="discord-embed-footer"
              className="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <SmallImage url={embed.footer?.icon_url} />
              <span>
                {[embed.footer?.text, timestamp].filter(Boolean).join(' • ')}
              </span>
            </div>
          ) : null}
        </div>
        {thumbnail ? (
          <img
            data-testid="discord-embed-thumbnail"
            src={thumbnail}
            alt=""
            referrerPolicy="no-referrer"
            loading="lazy"
            className="size-20 shrink-0 rounded-md object-cover"
          />
        ) : null}
      </div>
    </article>
  );
}
