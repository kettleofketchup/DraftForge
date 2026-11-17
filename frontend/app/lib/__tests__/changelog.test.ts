// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { allReleases, latestReleases, parseReleases } from '~/lib/changelog';
import { CHANGELOG_FIXTURE as FIXTURE } from './changelog-fixture';

describe('parseReleases', () => {
  it('returns releases newest first with version, date and body', () => {
    const releases = parseReleases(FIXTURE);
    expect(releases.map((r) => r.version)).toEqual(['2.1.0', '2.0.0', '1.0.0']);
    expect(releases[0].date).toBe('2030-02-01');
    expect(releases[0].body.startsWith('### Fixed')).toBe(true);
    expect(releases[0].body).not.toContain('## [');
    expect(releases[0].body).not.toContain('pointer');
  });

  it('returns no releases when only the preamble and Unreleased exist', () => {
    expect(
      parseReleases('# Changelog\n\n## [Unreleased]\n\n<!-- x -->\n'),
    ).toEqual([]);
    expect(parseReleases('')).toEqual([]);
  });

  it('parses CRLF line endings the same as LF', () => {
    expect(parseReleases(FIXTURE.replace(/\n/g, '\r\n'))).toEqual(
      parseReleases(FIXTURE),
    );
  });
});

describe('latestReleases', () => {
  it('returns at most n releases from the top', () => {
    expect(latestReleases(2, FIXTURE).map((r) => r.version)).toEqual([
      '2.1.0',
      '2.0.0',
    ]);
    expect(latestReleases(5, FIXTURE)).toHaveLength(3);
  });
});

describe('allReleases', () => {
  it('parses the bundled copy into semver releases', () => {
    const releases = allReleases();
    expect(releases.length).toBeGreaterThanOrEqual(1);
    for (const r of releases) {
      expect(r.version).toMatch(/^\d+\.\d+\.\d+$/);
    }
  });
});
