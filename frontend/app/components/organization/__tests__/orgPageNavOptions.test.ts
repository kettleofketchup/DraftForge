import { describe, expect, it } from 'vitest';
import {
  buildOrgPageNavOptions,
  type OrgPageNavInput,
} from '../orgPageNavOptions';

const base: OrgPageNavInput = {
  leaguesCount: 2,
  eventsCount: 3,
  userCountDisplay: 4,
  canViewMembers: false,
  canViewContributions: false,
  canViewConduct: false,
  canUsePromotion: false,
  canViewClaims: false,
};

const values = (input: OrgPageNavInput): string[] =>
  buildOrgPageNavOptions(input).map((o) => o.value);

describe('buildOrgPageNavOptions', () => {
  it('always lists leagues and events with counts', () => {
    expect(buildOrgPageNavOptions(base)).toEqual([
      { value: 'leagues', label: 'Leagues (2)' },
      { value: 'events', label: 'Events (3)' },
    ]);
  });

  it('lists claims when the viewer can view claims (org staff)', () => {
    expect(values({ ...base, canViewClaims: true })).toContain('claims');
  });

  it('omits claims for a plain member', () => {
    expect(values(base)).not.toContain('claims');
  });

  it('never lists settings; settings open from the header cog', () => {
    expect(
      values({
        ...base,
        canViewMembers: true,
        canViewContributions: true,
        canUsePromotion: true,
        canViewClaims: true,
      }),
    ).not.toContain('settings');
  });

  it('adds conduct after contributions when allowed', () => {
    expect(
      values({ ...base, canViewContributions: true, canViewConduct: true }),
    ).toEqual(['leagues', 'events', 'contributions', 'conduct']);
  });

  it('omits conduct when not allowed', () => {
    expect(values({ ...base, canViewContributions: true })).not.toContain(
      'conduct',
    );
  });

  it('keeps the tab order of the desktop tab list', () => {
    expect(
      values({
        ...base,
        canViewMembers: true,
        canViewContributions: true,
        canViewConduct: true,
        canUsePromotion: true,
        canViewClaims: true,
      }),
    ).toEqual([
      'leagues',
      'events',
      'users',
      'contributions',
      'conduct',
      'promotion',
      'claims',
    ]);
  });
});
