import changelogMd from '~/data/CHANGELOG.md?raw';
import { parseReleases, type Release } from './changelog-parse';

export { parseReleases };
export type { Release };

export function allReleases(md: string = changelogMd): Release[] {
  return parseReleases(md);
}

export function latestReleases(n = 2, md: string = changelogMd): Release[] {
  return parseReleases(md).slice(0, n);
}
