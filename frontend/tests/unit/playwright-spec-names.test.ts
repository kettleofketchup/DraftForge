import { readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';

const E2E = fileURLToPath(new URL('../playwright/e2e', import.meta.url));

const entries = (d: string): string[] =>
  readdirSync(d, { withFileTypes: true }).flatMap((e) => {
    const p = join(d, e.name);
    return e.isDirectory() ? [p, ...entries(p)] : [p];
  });

it('spec files and directories have no numeric prefix', () => {
  const numbered = entries(E2E)
    .map((p) => relative(E2E, p))
    .filter((p) => /^\d+-/.test(p.split('/').at(-1) ?? ''));
  expect(numbered).toEqual([]);
});
