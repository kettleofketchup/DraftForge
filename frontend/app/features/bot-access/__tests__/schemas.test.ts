import { describe, expect, it } from 'vitest';

import { BotAccessSnapshotSchema, isAllowedExternalLink } from '../schemas';
import { makeRow, makeSnapshot } from './fixtures';

describe('BotAccessSnapshotSchema', () => {
  it('parses a valid snapshot', () => {
    const snapshot = makeSnapshot();
    expect(BotAccessSnapshotSchema.parse(snapshot)).toEqual(snapshot);
  });

  it('parses a row whose identity is not known yet', () => {
    const snapshot = makeSnapshot({
      bots: [makeRow({ identity: null, status: 'offline', access: 'unknown' })],
    });
    expect(BotAccessSnapshotSchema.safeParse(snapshot).success).toBe(true);
  });

  it('rejects a non-https profile url', () => {
    const snapshot = makeSnapshot({
      bots: [
        makeRow({
          identity: {
            kind: 'steam',
            value: '1',
            profile_url: 'http://steamcommunity.com/profiles/1',
          },
        }),
      ],
    });
    expect(BotAccessSnapshotSchema.safeParse(snapshot).success).toBe(false);
  });

  it('rejects a javascript league link', () => {
    const snapshot = makeSnapshot({
      league_link: { kind: 'league_admin_portal', url: 'javascript:alert(1)' },
    });
    expect(BotAccessSnapshotSchema.safeParse(snapshot).success).toBe(false);
  });

  it('rejects an unknown service status', () => {
    const snapshot = {
      ...makeSnapshot(),
      service: { status: 'exploded', code: null, retryable: false },
    };
    expect(BotAccessSnapshotSchema.safeParse(snapshot).success).toBe(false);
  });
});

describe('isAllowedExternalLink', () => {
  it('allows a Steam profile link', () => {
    expect(
      isAllowedExternalLink(
        'https://steamcommunity.com/profiles/76561197960265729',
      ),
    ).toBe(true);
  });

  it('allows the league admins page', () => {
    expect(
      isAllowedExternalLink('https://www.dota2.com/league/12345/admins'),
    ).toBe(true);
  });

  it('rejects a foreign host', () => {
    expect(isAllowedExternalLink('https://evil.example/x')).toBe(false);
  });

  it('rejects a lookalike host', () => {
    expect(
      isAllowedExternalLink('https://steamcommunity.com.evil.example/'),
    ).toBe(false);
  });

  it('rejects http on an allowed host', () => {
    expect(isAllowedExternalLink('http://steamcommunity.com/profiles/1')).toBe(
      false,
    );
  });

  it('rejects unparsable and javascript urls', () => {
    expect(isAllowedExternalLink('not a url')).toBe(false);
    expect(isAllowedExternalLink('javascript:alert(1)')).toBe(false);
  });
});
