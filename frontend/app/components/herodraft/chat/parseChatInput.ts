// Preview-only mirror of backend parse_composer; the server decides routing.
const NEWLINES = /[\r\n]/g;
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000a-\u001f\u007f-\u009f]/g;
const ALL_PREFIX = /^\/all(?:[ \t]+|$)/i;
const LEADING_BLANKS = /^[ \t]+/;
const TRAILING_BLANKS = /[ \t]+$/;

export type ChatChannel = 'team' | 'all';

export function normalizeChatText(raw: string): string {
  return raw.replace(NEWLINES, ' ').replace(CONTROL, '');
}

function trimBlanks(text: string): string {
  return text.replace(LEADING_BLANKS, '').replace(TRAILING_BLANKS, '');
}

export function parseChatInput(raw: string): {
  channel: ChatChannel;
  body: string;
} {
  const text = normalizeChatText(raw).replace(LEADING_BLANKS, '');
  const match = ALL_PREFIX.exec(text);
  if (match) {
    return { channel: 'all', body: trimBlanks(text.slice(match[0].length)) };
  }
  return { channel: 'team', body: trimBlanks(text) };
}
