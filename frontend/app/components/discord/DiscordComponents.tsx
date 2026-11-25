import { ChevronDown, ExternalLink } from 'lucide-react';
import type { CSSProperties, MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '~/lib/utils';
import { discordColorHex } from './colors';
import { DiscordMarkdown } from './DiscordMarkdown';
import type {
  ActionRowInput,
  ButtonInput,
  ContainerChildInput,
  ContainerInput,
  EmojiInput,
  MediaGalleryInput,
  SectionInput,
  SelectMenuInput,
  SeparatorInput,
  ThumbnailInput,
  TopLevelComponentInput,
} from './messageInput';
import { safeHref, safeImageSrc } from './safeHref';
import type { DiscordPreviewOptions } from './timestamps';
import type { DiscordResolver } from './types';

type RenderCtx = {
  resolve?: DiscordResolver;
  options?: DiscordPreviewOptions;
};

const BUTTON_BASE =
  'inline-flex min-h-8 cursor-default items-center gap-1.5 rounded-md px-4 py-1 text-sm font-medium select-none';

const BUTTON_STYLE: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: 'bg-discord text-foreground',
  2: 'bg-base-700 text-foreground',
  3: 'bg-success text-success-foreground',
  4: 'bg-destructive text-foreground',
  5: 'bg-base-700 text-foreground',
};

function preventDefault(e: MouseEvent) {
  e.preventDefault();
}

function Emoji({ emoji }: { emoji?: EmojiInput | null }) {
  if (!emoji?.name) return null;
  return <span aria-hidden>{emoji.id ? `:${emoji.name}:` : emoji.name}</span>;
}

function DiscordButton({ button }: { button: ButtonInput }) {
  if (button.style === 6) return null;
  const className = cn(BUTTON_BASE, BUTTON_STYLE[button.style]);
  const body = (
    <>
      <Emoji emoji={button.emoji} />
      {button.label ? <span>{button.label}</span> : null}
    </>
  );
  if (button.style === 5) {
    const href = safeHref(button.url ?? undefined);
    const icon = (
      <ExternalLink
        data-testid="discord-external-icon"
        aria-hidden
        className="size-3.5"
      />
    );
    if (!href)
      return (
        <span data-style={5} aria-disabled="true" className={className}>
          {body}
          {icon}
        </span>
      );
    return (
      <a
        data-style={5}
        href={href}
        target="_blank"
        rel="noopener noreferrer nofollow"
        aria-disabled="true"
        tabIndex={-1}
        onClick={preventDefault}
        className={className}
      >
        {body}
        {icon}
      </a>
    );
  }
  return (
    <span
      role="button"
      data-style={button.style}
      aria-disabled="true"
      className={cn(className, button.disabled && 'opacity-50')}
    >
      {body}
    </span>
  );
}

function DiscordSelect({ menu }: { menu: SelectMenuInput }) {
  const { t } = useTranslation('discordPreview');
  return (
    <div
      role="combobox"
      aria-expanded={false}
      aria-disabled="true"
      className="flex min-h-10 w-full max-w-md cursor-default items-center justify-between rounded-md border border-border bg-base-950 px-3 text-sm text-muted-foreground"
    >
      <span>{menu.placeholder || t('component.select_placeholder')}</span>
      <ChevronDown aria-hidden className="size-4" />
    </div>
  );
}

function ActionRow({ row }: { row: ActionRowInput }) {
  return (
    <div data-testid="discord-action-row" className="flex flex-wrap gap-2">
      {row.components.map((c, i) =>
        c.type === 2 ? (
          <DiscordButton key={i} button={c} />
        ) : (
          <DiscordSelect key={i} menu={c} />
        ),
      )}
    </div>
  );
}

function Thumbnail({ thumb }: { thumb: ThumbnailInput }) {
  const src = safeImageSrc(thumb.media.url);
  if (!src) return null;
  return (
    <img
      src={src}
      alt={thumb.description ?? ''}
      referrerPolicy="no-referrer"
      loading="lazy"
      className={cn(
        'size-20 shrink-0 rounded-md object-cover',
        thumb.spoiler && 'blur-md',
      )}
    />
  );
}

function Section({ section, ctx }: { section: SectionInput; ctx: RenderCtx }) {
  const { accessory } = section;
  return (
    <div data-testid="discord-section" className="flex items-start gap-3">
      <div className="min-w-0 flex-1 space-y-1">
        {section.components.map((td, i) => (
          <DiscordMarkdown
            key={i}
            text={td.content}
            resolve={ctx.resolve}
            options={ctx.options}
          />
        ))}
      </div>
      {accessory.type === 11 ? (
        <Thumbnail thumb={accessory} />
      ) : (
        <DiscordButton button={accessory} />
      )}
    </div>
  );
}

function Separator({ sep }: { sep: SeparatorInput }) {
  const spacing = sep.spacing === 2 ? 'my-3' : 'my-1';
  if (sep.divider === false) return <div aria-hidden className={spacing} />;
  return <hr className={cn('border-border', spacing)} />;
}

function MediaGallery({ gallery }: { gallery: MediaGalleryInput }) {
  return (
    <div className="grid grid-cols-2 gap-1">
      {gallery.items.map((item, i) => {
        const src = safeImageSrc(item.media.url);
        if (!src) return null;
        return (
          <img
            key={i}
            src={src}
            alt={item.description ?? ''}
            referrerPolicy="no-referrer"
            loading="lazy"
            className={cn(
              'w-full rounded-md object-cover',
              item.spoiler && 'blur-md',
            )}
          />
        );
      })}
    </div>
  );
}

function ChildComponent({
  component,
  ctx,
}: {
  component: ContainerChildInput;
  ctx: RenderCtx;
}) {
  switch (component.type) {
    case 1:
      return <ActionRow row={component} />;
    case 9:
      return <Section section={component} ctx={ctx} />;
    case 10:
      return (
        <DiscordMarkdown
          text={component.content}
          resolve={ctx.resolve}
          options={ctx.options}
        />
      );
    case 14:
      return <Separator sep={component} />;
    case 12:
      return <MediaGallery gallery={component} />;
  }
}

function Container({
  container,
  ctx,
}: {
  container: ContainerInput;
  ctx: RenderCtx;
}) {
  const hex = discordColorHex(container.accent_color);
  return (
    <div
      data-testid="discord-container"
      style={hex ? ({ '--accent-color': hex } as CSSProperties) : undefined}
      className="flex max-w-xl overflow-hidden rounded-md border border-border bg-base-800"
    >
      <div
        aria-hidden
        className={cn('w-1 shrink-0', hex ? 'bg-(--accent-color)' : '')}
      />
      <div
        className={cn(
          'min-w-0 flex-1 space-y-2 p-4',
          container.spoiler && 'blur-sm',
        )}
      >
        {container.components.map((c, i) => (
          <ChildComponent key={i} component={c} ctx={ctx} />
        ))}
      </div>
    </div>
  );
}

export function DiscordComponents({
  components,
  resolve,
  options,
}: {
  components: TopLevelComponentInput[];
  resolve?: DiscordResolver;
  options?: DiscordPreviewOptions;
}) {
  if (components.length === 0) return null;
  const ctx: RenderCtx = { resolve, options };
  return (
    <div className="mt-2 space-y-2">
      {components.map((c, i) =>
        c.type === 17 ? (
          <Container key={i} container={c} ctx={ctx} />
        ) : (
          <ChildComponent key={i} component={c} ctx={ctx} />
        ),
      )}
    </div>
  );
}
