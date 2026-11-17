export type Release = { version: string; date: string; body: string };

const RELEASE_HEADING = /^## \[(\d+\.\d+\.\d+)\] - (\S+)$/gm;
const ANY_H2 = /^## /gm;

export function parseReleases(md: string): Release[] {
  const text = md.replace(/\r\n/g, '\n');
  const releases: Release[] = [];
  for (const match of text.matchAll(RELEASE_HEADING)) {
    const start = match.index + match[0].length;
    ANY_H2.lastIndex = start;
    const next = ANY_H2.exec(text);
    const end = next ? next.index : text.length;
    releases.push({
      version: match[1],
      date: match[2],
      body: text.slice(start, end).trim(),
    });
  }
  return releases;
}
