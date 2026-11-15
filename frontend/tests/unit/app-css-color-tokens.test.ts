import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';

const APP_CSS = fileURLToPath(new URL('../../app/app.css', import.meta.url));

// Theme tokens are full oklch() colors, so hsl(var(--x) / a) resolves to hsl(oklch(...) / a),
// which is invalid and drops the whole declaration at computed-value time.
it('app.css never wraps a color token in hsl()/hsla()/rgb()/rgba()', () => {
  const offenders = readFileSync(APP_CSS, 'utf8')
    .split('\n')
    .map((line, i) => ({ line: i + 1, text: line.trim() }))
    .filter(({ text }) => /\b(hsla?|rgba?)\(\s*var\(--/.test(text));
  expect(offenders).toEqual([]);
});
