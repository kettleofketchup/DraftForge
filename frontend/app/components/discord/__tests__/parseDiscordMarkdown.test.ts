import { describe, expect, it } from 'vitest';
import {
  parseDiscordMarkdown,
  type MdNode,
} from '../markdown/parseDiscordMarkdown';

const text = (value: string): MdNode => ({ type: 'text', value });

describe('parseDiscordMarkdown', () => {
  it('plain text is one text node', () => {
    expect(parseDiscordMarkdown('hello world')).toEqual([text('hello world')]);
  });

  it('parseDiscordMarkdown keeps &amp; literal', () => {
    expect(parseDiscordMarkdown('Snacks &amp; drinks')).toEqual([
      text('Snacks &amp; drinks'),
    ]);
  });

  it('HTML stays a text node', () => {
    expect(parseDiscordMarkdown('<img onerror=alert(1)>')).toEqual([
      text('<img onerror=alert(1)>'),
    ]);
  });

  it.each([
    ['**b**', 'bold'],
    ['*i*', 'italic'],
    ['_i_', 'italic'],
    ['__u__', 'underline'],
    ['~~s~~', 'strike'],
    ['||x||', 'spoiler'],
  ] as const)('%s is %s', (src, type) => {
    const [node] = parseDiscordMarkdown(src);
    expect(node).toMatchObject({ type });
    expect(node && 'children' in node && node.children).toHaveLength(1);
  });

  it('nests italic inside bold', () => {
    expect(parseDiscordMarkdown('**bold *italic***')).toEqual([
      {
        type: 'bold',
        children: [
          text('bold '),
          { type: 'italic', children: [text('italic')] },
        ],
      },
    ]);
  });

  it('nests bold inside underline', () => {
    expect(parseDiscordMarkdown('__underline **bold**__')).toEqual([
      {
        type: 'underline',
        children: [
          text('underline '),
          { type: 'bold', children: [text('bold')] },
        ],
      },
    ]);
  });

  it('keeps bold inside italic', () => {
    expect(parseDiscordMarkdown('*a **b** c*')).toEqual([
      {
        type: 'italic',
        children: [
          text('a '),
          { type: 'bold', children: [text('b')] },
          text(' c'),
        ],
      },
    ]);
  });

  it('leaves underscores inside words alone', () => {
    expect(parseDiscordMarkdown('snake_case_name')).toEqual([
      text('snake_case_name'),
    ]);
  });

  it.each([['**open'], ['`x'], ['__u'], ['||x'], ['~~s']])(
    'unterminated %s stays literal',
    (src) => {
      expect(parseDiscordMarkdown(src)).toEqual([text(src)]);
    },
  );

  it('backslash escapes a marker', () => {
    expect(parseDiscordMarkdown('\\*not italic\\*')).toEqual([
      text('*not italic*'),
    ]);
  });

  it('inline code is raw', () => {
    expect(parseDiscordMarkdown('run `**x**` now')).toEqual([
      text('run '),
      { type: 'inlineCode', value: '**x**' },
      text(' now'),
    ]);
  });

  it('fenced code block keeps language and raw body', () => {
    expect(parseDiscordMarkdown('```py\nprint("*x*")\n```')).toEqual([
      { type: 'codeBlock', lang: 'py', value: 'print("*x*")' },
    ]);
  });

  it('fenced code block without language', () => {
    expect(parseDiscordMarkdown('before\n```\na\nb\n```\nafter')).toEqual([
      text('before'),
      { type: 'codeBlock', value: 'a\nb' },
      text('after'),
    ]);
  });

  it('line quote groups consecutive lines', () => {
    expect(parseDiscordMarkdown('> one\n> two\nthree')).toEqual([
      {
        type: 'blockquote',
        children: [text('one'), { type: 'lineBreak' }, text('two')],
      },
      text('three'),
    ]);
  });

  it('>>> quotes the rest of the message', () => {
    expect(parseDiscordMarkdown('>>> a\nb')).toEqual([
      {
        type: 'blockquote',
        children: [text('a'), { type: 'lineBreak' }, text('b')],
      },
    ]);
  });

  it.each([
    ['# h', 1],
    ['## h', 2],
    ['### h', 3],
  ] as const)('%s is a level %i heading', (src, level) => {
    expect(parseDiscordMarkdown(src)).toEqual([
      { type: 'heading', level, children: [text('h')] },
    ]);
  });

  it('#### is not a heading', () => {
    expect(parseDiscordMarkdown('#### h')).toEqual([text('#### h')]);
  });

  it('-# is subtext', () => {
    expect(parseDiscordMarkdown('-# small')).toEqual([
      { type: 'subtext', children: [text('small')] },
    ]);
  });

  it('unordered list', () => {
    expect(parseDiscordMarkdown('- a\n* **b**')).toEqual([
      {
        type: 'list',
        ordered: false,
        children: [
          { type: 'listItem', children: [text('a')] },
          {
            type: 'listItem',
            children: [{ type: 'bold', children: [text('b')] }],
          },
        ],
      },
    ]);
  });

  it('ordered list', () => {
    expect(parseDiscordMarkdown('1. a\n2. b')).toEqual([
      {
        type: 'list',
        ordered: true,
        children: [
          { type: 'listItem', children: [text('a')] },
          { type: 'listItem', children: [text('b')] },
        ],
      },
    ]);
  });

  it('masked link with formatted label', () => {
    expect(parseDiscordMarkdown('[**Sign up**](https://x.test/e/1)')).toEqual([
      {
        type: 'link',
        href: 'https://x.test/e/1',
        children: [{ type: 'bold', children: [text('Sign up')] }],
      },
    ]);
  });

  it('masked link to javascript: stays text', () => {
    const nodes = parseDiscordMarkdown('[x](javascript:alert(1))');
    expect(JSON.stringify(nodes)).not.toContain('"link"');
    expect(nodes).toEqual([text('[x](javascript:alert(1))')]);
  });

  it('bare URL and suppressed-embed URL', () => {
    expect(
      parseDiscordMarkdown('go https://x.test/a, or <https://y.test>'),
    ).toEqual([
      text('go '),
      { type: 'url', href: 'https://x.test/a' },
      text(', or '),
      { type: 'url', href: 'https://y.test' },
    ]);
  });

  it('mentions', () => {
    expect(
      parseDiscordMarkdown('<@1> <@!2> <@&3> <#4> @everyone @here'),
    ).toEqual([
      { type: 'userMention', id: '1' },
      text(' '),
      { type: 'userMention', id: '2' },
      text(' '),
      { type: 'roleMention', id: '3' },
      text(' '),
      { type: 'channelMention', id: '4' },
      text(' '),
      { type: 'everyone' },
      text(' '),
      { type: 'here' },
    ]);
  });

  it('timestamps with and without a style', () => {
    expect(parseDiscordMarkdown('<t:1794704400:F><t:5>')).toEqual([
      { type: 'timestamp', unix: 1794704400, style: 'F' },
      { type: 'timestamp', unix: 5, style: 'f' },
    ]);
  });

  it('a bad timestamp style stays literal', () => {
    expect(parseDiscordMarkdown('<t:5:X>')).toEqual([text('<t:5:X>')]);
  });

  it('custom emoji, static and animated', () => {
    expect(parseDiscordMarkdown('<:dota:11><a:spin:22>')).toEqual([
      { type: 'customEmoji', name: 'dota', id: '11', animated: false },
      { type: 'customEmoji', name: 'spin', id: '22', animated: true },
    ]);
  });

  it('newlines become line breaks', () => {
    expect(parseDiscordMarkdown('a\nb')).toEqual([
      text('a'),
      { type: 'lineBreak' },
      text('b'),
    ]);
  });

  it('bold spans lines', () => {
    expect(parseDiscordMarkdown('**a\nb**')).toEqual([
      {
        type: 'bold',
        children: [text('a'), { type: 'lineBreak' }, text('b')],
      },
    ]);
  });

  it('a long run of markers does not hang', () => {
    const src = '*_~|'.repeat(1500);
    const started = Date.now();
    parseDiscordMarkdown(src);
    expect(Date.now() - started).toBeLessThan(2000);
  });
});
