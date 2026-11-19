import tsParser from '@typescript-eslint/parser';
import type { Linter, Rule } from 'eslint';
import { RuleTester } from 'eslint';
import { describe, expect, it } from 'vitest';

import {
  dedupeRawColors,
  noRawColorStrings,
} from '../../eslint-rules/colors.js';

RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const tester = new RuleTester({
  languageOptions: {
    parser: tsParser,
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

const raw = (token: string) => ({ messageId: 'raw', data: { token } });

tester.run('no-raw-color-strings', noRawColorStrings as Rule.RuleModule, {
  valid: [
    "const m = { a: 'bg-radiant-surface/60 text-dire' };",
    "const a = ['bg-base-800 text-muted-foreground border-border'];",
    "const s = 'text-white bg-black/40 ring-white/10';",
    "const s = 'red-500 is a shade';",
    "const s = 'bg-red-ish text-green';",
    'const n = 500;',
    'const t = `p-2 ${x}`;',
  ],
  invalid: [
    {
      code: "const m = { str: 'bg-red-900/40' };",
      errors: [{ ...raw('bg-red-900/40'), line: 1, column: 19 }],
    },
    {
      code: "const a = ['bg-yellow-500 text-yellow-900'];",
      errors: [raw('bg-yellow-500'), raw('text-yellow-900')],
    },
    {
      code: "function f() { return 'hover:!bg-rose-800'; }",
      errors: [raw('hover:!bg-rose-800')],
    },
    {
      code: "const s = 'data-[state=open]:ring-violet-400 [&_svg]:text-sky-300';",
      errors: [
        raw('data-[state=open]:ring-violet-400'),
        raw('[&_svg]:text-sky-300'),
      ],
    },
    {
      code: 'const t = `p-2 ${c ? 1 : 2} border-l-emerald-600 fill-slate-50`;',
      errors: [raw('border-l-emerald-600'), raw('fill-slate-50')],
    },
    {
      code: "const s = 'ring-offset-gray-900 shadow-red-950/40';",
      errors: [raw('ring-offset-gray-900'), raw('shadow-red-950/40')],
    },
  ],
});

const msg = (
  ruleId: string,
  token: string,
  line: number,
  endLine = line,
): Linter.LintMessage => ({
  ruleId,
  message: `"${token}" uses the raw Tailwind palette.`,
  line,
  endLine,
  column: 1,
  severity: 2,
});

describe('dedupe-raw-colors', () => {
  const STRINGS = 'draftforge/no-raw-color-strings';
  const SHADCN = 'shadcn/no-raw-colors';

  it('drops a string report shadcn already made for the same class and lines', () => {
    const out = dedupeRawColors.postprocess([
      [msg(SHADCN, 'bg-red-500', 4, 6), msg(STRINGS, 'bg-red-500', 5)],
    ]);
    expect(out.map((m) => m.ruleId)).toEqual([SHADCN]);
  });

  it('keeps string reports for other classes or other lines', () => {
    const out = dedupeRawColors.postprocess([
      [
        msg(SHADCN, 'bg-red-500', 4),
        msg(STRINGS, 'bg-red-400', 4),
        msg(STRINGS, 'bg-red-500', 9),
        msg('other/rule', 'bg-red-500', 4),
      ],
    ]);
    expect(out).toHaveLength(4);
  });
});
