import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';

const PW = fileURLToPath(new URL('../playwright', import.meta.url));
const FRONTEND = fileURLToPath(new URL('../..', import.meta.url));
const walk = (d: string): string[] =>
  readdirSync(d, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(join(d, e.name)) : /\.(ts|tsx|js|mjs)$/.test(e.name) ? [join(d, e.name)] : [],
  );
const globConfigs = (d: string): string[] =>
  readdirSync(d)
    .filter((n) => /^playwright.*\.config\.ts$/.test(n))
    .map((n) => join(d, n));

it('no localhost/DOCKER_HOST literals outside base-url-resolve.ts', () => {
  const offenders = walk(PW)
    .concat(globConfigs(FRONTEND))
    .filter((f) => !f.endsWith('base-url-resolve.ts'))
    .filter((f) => /https:\/\/localhost|DOCKER_HOST/.test(readFileSync(f, 'utf8')));
  expect(offenders).toEqual([]);
});
