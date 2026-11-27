import { safeHref } from '../safeHref';
import type { TimestampStyle } from '../timestamps';

type Parent<T extends string> = { type: T; children: MdNode[] };

export type MdNode =
  | { type: 'text'; value: string }
  | Parent<'bold'>
  | Parent<'italic'>
  | Parent<'underline'>
  | Parent<'strike'>
  | Parent<'spoiler'>
  | { type: 'inlineCode'; value: string }
  | { type: 'codeBlock'; lang?: string; value: string }
  | Parent<'blockquote'>
  | { type: 'heading'; level: 1 | 2 | 3; children: MdNode[] }
  | Parent<'subtext'>
  | { type: 'list'; ordered: boolean; children: MdNode[] }
  | Parent<'listItem'>
  | { type: 'link'; href: string; children: MdNode[] }
  | { type: 'url'; href: string }
  | { type: 'userMention'; id: string }
  | { type: 'roleMention'; id: string }
  | { type: 'channelMention'; id: string }
  | { type: 'everyone' }
  | { type: 'here' }
  | { type: 'timestamp'; unix: number; style: TimestampStyle }
  | { type: 'customEmoji'; name: string; id: string; animated: boolean }
  | { type: 'lineBreak' };

type Match = { node: MdNode; length: number };
type Rule = (src: string, pos: number) => Match | null;

function sticky(
  re: RegExp,
): (src: string, pos: number) => RegExpExecArray | null {
  const flags = re.flags.includes('y') ? re.flags : `${re.flags}y`;
  const compiled = new RegExp(re.source, flags);
  return (src, pos) => {
    compiled.lastIndex = pos;
    return compiled.exec(src);
  };
}

function simple(
  re: RegExp,
  build: (m: RegExpExecArray) => MdNode | null,
): Rule {
  const exec = sticky(re);
  return (src, pos) => {
    const m = exec(src, pos);
    if (!m) return null;
    const node = build(m);
    return node ? { node, length: m[0].length } : null;
  };
}

const ESCAPE = simple(/\\([^0-9A-Za-z\s])/, (m) => ({
  type: 'text',
  value: m[1] ?? '',
}));
const NEWLINE = simple(/\n/, () => ({ type: 'lineBreak' }));
const INLINE_CODE = simple(/(`+)([\s\S]*?[^`])\1(?!`)/, (m) => ({
  type: 'inlineCode',
  value: m[2] ?? '',
}));
const TIMESTAMP = simple(/<t:(-?\d+)(?::([tTdDfFR]))?>/, (m) => ({
  type: 'timestamp',
  unix: Number(m[1]),
  style: (m[2] ?? 'f') as TimestampStyle,
}));
const USER = simple(/<@!?(\d+)>/, (m) => ({
  type: 'userMention',
  id: m[1] ?? '',
}));
const ROLE = simple(/<@&(\d+)>/, (m) => ({
  type: 'roleMention',
  id: m[1] ?? '',
}));
const CHANNEL = simple(/<#(\d+)>/, (m) => ({
  type: 'channelMention',
  id: m[1] ?? '',
}));
const EMOJI = simple(/<(a?):(\w+):(\d+)>/, (m) => ({
  type: 'customEmoji',
  animated: m[1] === 'a',
  name: m[2] ?? '',
  id: m[3] ?? '',
}));
const AUTOLINK = simple(/<(https?:\/\/[^\s>]+)>/, (m) => {
  const href = safeHref(m[1]);
  return href ? { type: 'url', href } : null;
});
const EVERYONE = simple(/@everyone/, () => ({ type: 'everyone' }));
const HERE = simple(/@here/, () => ({ type: 'here' }));
const BARE_URL = simple(/https?:\/\/[^\s<]+[^<.,:;"')\]\s]/, (m) => {
  const href = safeHref(m[0]);
  return href ? { type: 'url', href } : null;
});

const LINK_EXEC = sticky(
  /\[((?:\\[\s\S]|[^[\]\\])+)\]\(\s*<?([^\s()<>]+(?:\([^\s()<>]*\)[^\s()<>]*)*)>?\s*\)/,
);
const LINK: Rule = (src, pos) => {
  const m = LINK_EXEC(src, pos);
  if (!m) return null;
  const href = safeHref(m[2]);
  const node: MdNode = href
    ? { type: 'link', href, children: parseInline(m[1] ?? '') }
    : { type: 'text', value: m[0] };
  return { node, length: m[0].length };
};

function wrap(
  type: 'bold' | 'italic' | 'underline' | 'strike' | 'spoiler',
  re: RegExp,
): Rule {
  const exec = sticky(re);
  return (src, pos) => {
    const m = exec(src, pos);
    if (!m) return null;
    const inner = m.slice(1).find((g) => g !== undefined) ?? '';
    return {
      node: { type, children: parseInline(inner) },
      length: m[0].length,
    };
  };
}

const BOLD = wrap('bold', /\*\*([\s\S]+?)\*\*(?!\*)/);
const UNDERLINE = wrap('underline', /__([\s\S]+?)__(?!_)/);
const ITALIC = wrap(
  'italic',
  /\b_((?:__|\\[\s\S]|[^\\_])+?)_\b|\*(?=\S)((?:\*\*|\\[\s\S]|\s+(?:\\[\s\S]|[^\s*\\]|\*\*)|[^\s*\\])+?)\*(?!\*)/,
);
const STRIKE = wrap('strike', /~~(?=\S)([\s\S]*?\S)~~/);
const SPOILER = wrap('spoiler', /\|\|([\s\S]+?)\|\|/);

const FIRST_MATCH: readonly Rule[] = [
  ESCAPE,
  NEWLINE,
  INLINE_CODE,
  TIMESTAMP,
  USER,
  ROLE,
  CHANNEL,
  EMOJI,
  AUTOLINK,
  EVERYONE,
  HERE,
  LINK,
  BARE_URL,
];
// Discord picks the longest of these; italic wins a tie.
const LONGEST_MATCH: readonly Rule[] = [ITALIC, BOLD, UNDERLINE];
const AFTER: readonly Rule[] = [STRIKE, SPOILER];

const PLAIN_RUN = sticky(/[^\\\n`<@[\]h*_~|]+/);

function matchAt(src: string, pos: number): Match | null {
  for (const rule of FIRST_MATCH) {
    const m = rule(src, pos);
    if (m) return m;
  }
  let best: Match | null = null;
  for (const rule of LONGEST_MATCH) {
    const m = rule(src, pos);
    if (m && (!best || m.length > best.length)) best = m;
  }
  if (best) return best;
  for (const rule of AFTER) {
    const m = rule(src, pos);
    if (m) return m;
  }
  return null;
}

function pushText(out: MdNode[], value: string): void {
  const last = out[out.length - 1];
  if (last?.type === 'text') last.value += value;
  else out.push({ type: 'text', value });
}

function pushNode(out: MdNode[], node: MdNode): void {
  if (node.type === 'text') pushText(out, node.value);
  else out.push(node);
}

function parseInline(src: string): MdNode[] {
  const out: MdNode[] = [];
  let pos = 0;
  while (pos < src.length) {
    const run = PLAIN_RUN(src, pos);
    if (run) {
      pushText(out, run[0]);
      pos += run[0].length;
      continue;
    }
    const m = matchAt(src, pos);
    if (m) {
      pushNode(out, m.node);
      pos += m.length;
    } else {
      pushText(out, src.charAt(pos));
      pos += 1;
    }
  }
  return out;
}

const HEADING_RE = /^(#{1,3}) (.+)$/;
const SUBTEXT_RE = /^-# (.+)$/;
const LIST_RE = /^\s*([-*]|\d+\.) (.+)$/;
const QUOTE_RE = /^> ?(.*)$/;

function isQuoteLine(line: string): boolean {
  return line === '>' || line.startsWith('> ');
}

function parseLines(src: string, inQuote: boolean): MdNode[] {
  if (src === '') return [];
  const lines = src.split('\n');
  const out: MdNode[] = [];
  let para: string[] = [];
  const flush = (): void => {
    if (para.length) out.push(...parseInline(para.join('\n')));
    para = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    if (!inQuote && line.startsWith('>>> ')) {
      flush();
      const rest = [line.slice(4), ...lines.slice(i + 1)].join('\n');
      out.push({ type: 'blockquote', children: parseBlocks(rest, true) });
      return out;
    }
    if (!inQuote && isQuoteLine(line)) {
      flush();
      const quoted: string[] = [];
      while (i < lines.length && isQuoteLine(lines[i] ?? '')) {
        quoted.push(QUOTE_RE.exec(lines[i] ?? '')?.[1] ?? '');
        i++;
      }
      i--;
      out.push({
        type: 'blockquote',
        children: parseBlocks(quoted.join('\n'), true),
      });
      continue;
    }
    const heading = HEADING_RE.exec(line);
    if (heading) {
      flush();
      out.push({
        type: 'heading',
        level: (heading[1]?.length ?? 1) as 1 | 2 | 3,
        children: parseInline(heading[2] ?? ''),
      });
      continue;
    }
    const subtext = SUBTEXT_RE.exec(line);
    if (subtext) {
      flush();
      out.push({ type: 'subtext', children: parseInline(subtext[1] ?? '') });
      continue;
    }
    const item = LIST_RE.exec(line);
    if (item) {
      flush();
      const ordered = /\d/.test(item[1] ?? '');
      const items: MdNode[] = [];
      while (i < lines.length) {
        const next = LIST_RE.exec(lines[i] ?? '');
        if (!next || /\d/.test(next[1] ?? '') !== ordered) break;
        items.push({ type: 'listItem', children: parseInline(next[2] ?? '') });
        i++;
      }
      i--;
      out.push({ type: 'list', ordered, children: items });
      continue;
    }
    para.push(line);
  }
  flush();
  return out;
}

const FENCE_RE = /```(?:([a-z0-9_+\-.#]+)\n)?\n*([^\n][\s\S]*?)\n*```/gi;

function parseBlocks(src: string, inQuote: boolean): MdNode[] {
  const out: MdNode[] = [];
  let last = 0;
  for (const m of src.matchAll(FENCE_RE)) {
    let before = src.slice(last, m.index);
    if (last > 0) before = before.replace(/^\n/, '');
    out.push(...parseLines(before.replace(/\n$/, ''), inQuote));
    const block: Extract<MdNode, { type: 'codeBlock' }> = {
      type: 'codeBlock',
      value: m[2] ?? '',
    };
    if (m[1]) block.lang = m[1];
    out.push(block);
    last = m.index + m[0].length;
  }
  let rest = src.slice(last);
  if (last > 0) rest = rest.replace(/^\n/, '');
  out.push(...parseLines(rest, inQuote));
  return out;
}

export function parseDiscordMarkdown(text: string): MdNode[] {
  return parseBlocks(text, false);
}
