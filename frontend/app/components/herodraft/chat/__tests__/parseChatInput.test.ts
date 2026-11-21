import { describe, expect, it } from 'vitest';
import { normalizeChatText, parseChatInput } from '../parseChatInput';

// Mirrors backend ParseComposerTest.PARITY in draft/tests/test_hero_chat_functions.py.
const PARITY: [string, { channel: 'team' | 'all'; body: string }][] = [
  ['/all x', { channel: 'all', body: 'x' }],
  ['/ALL  x ', { channel: 'all', body: 'x' }],
  ['/allx', { channel: 'team', body: '/allx' }],
  ['/all', { channel: 'all', body: '' }],
  ['   hi', { channel: 'team', body: 'hi' }],
  ['/all\x1fx', { channel: 'team', body: '/allx' }],
  ['/all\tx', { channel: 'all', body: 'x' }],
  ['/all x', { channel: 'team', body: '/all x' }],
  ['a\nb', { channel: 'team', body: 'a b' }],
  ['\x00\x07', { channel: 'team', body: '' }],
  ['a\u2028b\u2029c', { channel: 'team', body: 'a b c' }],
  ['\u200b/all x', { channel: 'all', body: 'x' }],
  ['/all\u202ex', { channel: 'team', body: '/allx' }],
];

describe('parseChatInput', () => {
  it.each(PARITY)('parses %j', (raw, expected) => {
    expect(parseChatInput(raw)).toEqual(expected);
  });

  it('matches the prefix case-insensitively after leading blanks', () => {
    expect(parseChatInput('/All gl hf')).toEqual({
      channel: 'all',
      body: 'gl hf',
    });
    expect(parseChatInput('  /aLL\t\tgg')).toEqual({
      channel: 'all',
      body: 'gg',
    });
  });

  it('does not treat non-ASCII whitespace as a separator or trim it', () => {
    expect(parseChatInput(' hi ')).toEqual({
      channel: 'team',
      body: ' hi ',
    });
  });
});

describe('normalizeChatText', () => {
  it('turns newlines into spaces and strips C0/C1 controls but keeps tabs', () => {
    expect(normalizeChatText('a\r\nb\x85c\x7fd\x9f')).toBe('a  bcd');
    expect(normalizeChatText('tab\tkept')).toBe('tab\tkept');
  });

  it('turns line/paragraph separators into spaces and strips format characters', () => {
    expect(normalizeChatText('a\u2028b\u2029c')).toBe('a b c');
    expect(
      normalizeChatText(
        'x\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069y',
      ),
    ).toBe('xy');
    expect(normalizeChatText('a\u200bb\u2060c\ufeffd\u00ade')).toBe('abcde');
  });

  it('keeps joiners used by emoji and scripts', () => {
    expect(normalizeChatText('\u{1f468}\u200d\u{1f469}')).toBe(
      '\u{1f468}\u200d\u{1f469}',
    );
    expect(normalizeChatText('\u0645\u200c\u06cc')).toBe('\u0645\u200c\u06cc');
  });
});
