import type { TFunction } from 'i18next';
import type { CSSProperties, ReactNode } from 'react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '~/lib/utils';
import {
  parseDiscordMarkdown,
  type MdNode,
} from './markdown/parseDiscordMarkdown';
import {
  formatDiscordTimestamp,
  usePreviewOptions,
  type DiscordPreviewOptions,
} from './timestamps';
import type { DiscordResolver } from './types';

interface DiscordMarkdownProps {
  text: string;
  resolve?: DiscordResolver;
  options?: DiscordPreviewOptions;
  className?: string;
}

const PILL = 'rounded-sm bg-discord/20 px-0.5 font-medium text-discord';
const ROLE_PILL =
  'rounded-sm bg-[color-mix(in_oklab,var(--role-color)_20%,transparent)] px-0.5 font-medium text-[var(--role-color)]';
const LINK = 'text-info hover:underline';

function shortId(id: string): string {
  return id.length > 4 ? `${id.slice(0, 4)}…` : id;
}

function roleHex(color: number | undefined): string | undefined {
  if (!color) return undefined;
  return `#${color.toString(16).padStart(6, '0')}`;
}

type Ctx = {
  resolve: DiscordResolver;
  options: DiscordPreviewOptions;
  t: TFunction<'discordPreview'>;
};

function renderNodes(nodes: MdNode[], ctx: Ctx): ReactNode[] {
  return nodes.map((node, i) => renderNode(node, i, ctx));
}

function renderNode(node: MdNode, key: number, ctx: Ctx): ReactNode {
  const { resolve, options, t } = ctx;
  switch (node.type) {
    case 'text':
      return node.value;
    case 'lineBreak':
      return <br key={key} />;
    case 'bold':
      return <strong key={key}>{renderNodes(node.children, ctx)}</strong>;
    case 'italic':
      return <em key={key}>{renderNodes(node.children, ctx)}</em>;
    case 'underline':
      return <u key={key}>{renderNodes(node.children, ctx)}</u>;
    case 'strike':
      return <s key={key}>{renderNodes(node.children, ctx)}</s>;
    case 'spoiler':
      return (
        <span
          key={key}
          title={t('markdown.spoiler')}
          className="rounded-sm bg-base-700 px-0.5"
        >
          {renderNodes(node.children, ctx)}
        </span>
      );
    case 'inlineCode':
      return (
        <code
          key={key}
          className="rounded-sm bg-base-800 px-1 font-mono text-[0.85em]"
        >
          {node.value}
        </code>
      );
    case 'codeBlock':
      return (
        <pre
          key={key}
          data-lang={node.lang}
          className="my-1 overflow-x-auto rounded-md border border-border bg-base-800 p-2 font-mono text-[0.85em]"
        >
          <code>{node.value}</code>
        </pre>
      );
    case 'blockquote':
      return (
        <blockquote key={key} className="my-0.5 border-l-4 border-border pl-3">
          {renderNodes(node.children, ctx)}
        </blockquote>
      );
    case 'heading':
      return (
        <div
          key={key}
          data-heading={node.level}
          className={cn(
            'my-1 font-bold',
            node.level === 1 && 'text-2xl',
            node.level === 2 && 'text-xl',
            node.level === 3 && 'text-lg',
          )}
        >
          {renderNodes(node.children, ctx)}
        </div>
      );
    case 'subtext':
      return (
        <div
          key={key}
          data-subtext=""
          className="text-xs text-muted-foreground"
        >
          {renderNodes(node.children, ctx)}
        </div>
      );
    case 'list': {
      const List = node.ordered ? 'ol' : 'ul';
      return (
        <List
          key={key}
          className={cn(
            'my-0.5 pl-5',
            node.ordered ? 'list-decimal' : 'list-disc',
          )}
        >
          {renderNodes(node.children, ctx)}
        </List>
      );
    }
    case 'listItem':
      return <li key={key}>{renderNodes(node.children, ctx)}</li>;
    case 'link':
      return (
        <a
          key={key}
          href={node.href}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className={LINK}
        >
          {renderNodes(node.children, ctx)}
        </a>
      );
    case 'url':
      return (
        <a
          key={key}
          href={node.href}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className={LINK}
        >
          {node.href}
        </a>
      );
    case 'userMention': {
      const name = resolve.users?.[node.id];
      return (
        <span key={key} title={node.id} className={PILL}>
          {name !== undefined
            ? `@${name}`
            : t('mention.unknown_user', { id: node.id })}
        </span>
      );
    }
    case 'roleMention': {
      const role = resolve.roles?.[node.id];
      const hex = roleHex(role?.color);
      return (
        <span
          key={key}
          title={node.id}
          className={hex ? ROLE_PILL : PILL}
          style={hex ? ({ '--role-color': hex } as CSSProperties) : undefined}
        >
          {role
            ? `@${role.name}`
            : t('mention.unknown_role', { id: shortId(node.id) })}
        </span>
      );
    }
    case 'channelMention': {
      const name = resolve.channels?.[node.id];
      return (
        <span key={key} title={node.id} className={PILL}>
          {name !== undefined
            ? `#${name}`
            : t('mention.unknown_channel', { id: shortId(node.id) })}
        </span>
      );
    }
    case 'everyone':
      return (
        <span key={key} className={PILL}>
          @everyone
        </span>
      );
    case 'here':
      return (
        <span key={key} className={PILL}>
          @here
        </span>
      );
    case 'timestamp': {
      const date = new Date(node.unix * 1000);
      if (Number.isNaN(date.getTime())) return null;
      return (
        <time
          key={key}
          dateTime={date.toISOString()}
          title={formatDiscordTimestamp(node.unix, 'F', options)}
          className="rounded-sm bg-base-800 px-0.5"
        >
          {formatDiscordTimestamp(node.unix, node.style, options)}
        </time>
      );
    }
    case 'customEmoji':
      return (
        <span key={key} title={`:${node.name}:`}>
          :{node.name}:
        </span>
      );
  }
}

export function DiscordMarkdown({
  text,
  resolve,
  options,
  className,
}: DiscordMarkdownProps) {
  const { t } = useTranslation('discordPreview');
  const viewerOptions = usePreviewOptions();
  const nodes = useMemo(() => parseDiscordMarkdown(text), [text]);
  const ctx: Ctx = {
    resolve: resolve ?? {},
    options: options ?? viewerOptions,
    t,
  };
  return (
    <div className={cn('break-words', className)}>
      {renderNodes(nodes, ctx)}
    </div>
  );
}
