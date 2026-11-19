// Raw Tailwind palette classes in any string. shadcn/no-raw-colors only follows strings
// that reach a className; maps, arrays, returns and shared constants slip past it.

const UTILITIES = [
  'bg',
  'text',
  'border',
  'border-[xytrblse]',
  'ring',
  'ring-offset',
  'inset-ring',
  'outline',
  'from',
  'via',
  'to',
  'fill',
  'stroke',
  'shadow',
  'inset-shadow',
  'drop-shadow',
  'divide',
  'placeholder',
  'decoration',
  'accent',
  'caret',
];
const HUES = [
  'slate',
  'gray',
  'zinc',
  'neutral',
  'stone',
  'red',
  'orange',
  'amber',
  'yellow',
  'lime',
  'green',
  'emerald',
  'teal',
  'cyan',
  'sky',
  'blue',
  'indigo',
  'violet',
  'purple',
  'fuchsia',
  'pink',
  'rose',
];
const PALETTE = new RegExp(
  `^!?(?:${UTILITIES.join('|')})-(?:${HUES.join('|')})-(?:50|[1-9]00|950)(?:/\\S+)?!?$`,
);
const RULE_ID = 'draftforge/no-raw-color-strings';
const SHADCN_RULE_ID = 'shadcn/no-raw-colors';

// The utility after the last variant colon outside [] and ().
function utilityOf(token) {
  let depth = 0;
  let start = 0;
  for (let i = 0; i < token.length; i++) {
    const ch = token[i];
    if (ch === '[' || ch === '(') depth++;
    else if (ch === ']' || ch === ')') depth--;
    else if (ch === ':' && depth === 0) start = i + 1;
  }
  return token.slice(start);
}

export const noRawColorStrings = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Raw Tailwind palette classes in strings outside className',
    },
    messages: {
      raw: '"{{token}}" uses the raw Tailwind palette. Use the token for what it means: docs/THEMING-GUIDE.md "Domain Colors" (radiant, pick, pos-carry, role-admin, ...) or its generic table (success, error, base-*).',
    },
    schema: [],
  },
  create(context) {
    const { sourceCode } = context;
    function check(node) {
      const raw = sourceCode.getText(node);
      const re = /\S+/g;
      let m;
      while ((m = re.exec(raw))) {
        const token = m[0].replace(/^[`'"}]+|[`'"$]+$/g, '');
        if (!PALETTE.test(utilityOf(token))) continue;
        const at = node.range[0] + m.index + m[0].indexOf(token);
        context.report({
          node,
          loc: {
            start: sourceCode.getLocFromIndex(at),
            end: sourceCode.getLocFromIndex(at + token.length),
          },
          messageId: 'raw',
          data: { token },
        });
      }
    }
    return {
      Literal(node) {
        if (typeof node.value === 'string') check(node);
      },
      TemplateElement: check,
    };
  },
};

const quoted = (message) => /^"([^"]+)"/.exec(message)?.[1];

// Drops a no-raw-color-strings report when shadcn/no-raw-colors already reported the
// same class on overlapping lines, so each raw class is counted once.
export const dedupeRawColors = {
  meta: { name: 'dedupe-raw-colors' },
  supportsAutofix: true,
  preprocess: (text) => [text],
  postprocess(messageLists) {
    const messages = messageLists.flat();
    const shadcn = messages.filter((m) => m.ruleId === SHADCN_RULE_ID);
    return messages.filter((m) => {
      if (m.ruleId !== RULE_ID) return true;
      const token = quoted(m.message);
      const end = m.endLine ?? m.line;
      return !shadcn.some(
        (s) =>
          quoted(s.message) === token &&
          s.line <= end &&
          (s.endLine ?? s.line) >= m.line,
      );
    });
  },
};
