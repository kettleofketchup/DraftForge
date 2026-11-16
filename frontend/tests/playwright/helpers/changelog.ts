import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { parseReleases } from '../../../app/lib/changelog-parse';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CHANGELOG_COPY = path.resolve(
  __dirname,
  '../../../app/data/CHANGELOG.md',
);

export function latestChangelogVersions(n: number): string[] {
  const md = fs.readFileSync(CHANGELOG_COPY, 'utf-8');
  return parseReleases(md)
    .slice(0, n)
    .map((r) => r.version);
}
