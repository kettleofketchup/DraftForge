import { readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';

const E2E = fileURLToPath(new URL('../playwright/e2e', import.meta.url));

// Duplicates that predate this check; do not add to this list.
const KNOWN = new Set(['.:00-', '.:01-', '.:06-', '15-edit-user:11-']);

const dirs = (d: string): string[] => [
  d,
  ...readdirSync(d, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .flatMap((e) => dirs(join(d, e.name))),
];

it('spec files in one directory have distinct numeric prefixes', () => {
  const duplicates = dirs(E2E).flatMap((d) => {
    const prefixes = readdirSync(d)
      .filter((n) => n.endsWith('.spec.ts'))
      .map((n) => /^\d+-/.exec(n)?.[0])
      .filter((p): p is string => p !== undefined);
    const dup = prefixes.filter((p, i) => prefixes.indexOf(p) !== i);
    return [...new Set(dup)].map((p) => `${relative(E2E, d) || '.'}:${p}`);
  });
  expect(duplicates.filter((d) => !KNOWN.has(d))).toEqual([]);
});
