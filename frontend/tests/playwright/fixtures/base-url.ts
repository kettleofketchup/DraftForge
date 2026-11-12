import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { resolveBaseUrl } from './base-url-resolve';

function readFile(p: string): string | null {
  try {
    return fs.readFileSync(p, 'utf8');
  } catch {
    return null;
  }
}

function realpath(p: string): string {
  try {
    return fs.realpathSync(path.resolve(p));
  } catch {
    return path.resolve(p);
  }
}

export const BASE_URL: string = resolveBaseUrl({
  env: process.env,
  repoRoot: () => fileURLToPath(new URL('../../../../', import.meta.url)),
  readFile,
  realpath,
});

export const API_URL = `${BASE_URL}/api`;
