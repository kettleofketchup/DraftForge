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
  standingTabs: [],
  canUsePromotion: false,
  canViewClaims: false,
  canReviewMmr: false,
  mmrPendingCount: 0,
};

const tracks = [
  { value: 'contributions', label: 'Contributions' },
  { value: 'conduct', label: 'Conduct' },
];

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

  it('shows the pending claims count on the claims entry', () => {
    const claims = (pendingClaimsCount?: number) =>
      buildOrgPageNavOptions({
        ...base,
        canViewClaims: true,
        pendingClaimsCount,
      }).find((o) => o.value === 'claims')?.label;
    expect(claims(3)).toBe('Claims (3)');
    expect(claims(0)).toBe('Claims');
    expect(claims(undefined)).toBe('Claims');
  });

  it('omits claims for a plain member', () => {
    expect(values(base)).not.toContain('claims');
  });

  it('lists MMR requests for org staff', () => {
    expect(
      buildOrgPageNavOptions({ ...base, canReviewMmr: true }),
    ).toContainEqual({ value: 'mmr-requests', label: 'MMR requests' });
  });

  it('shows the pending MMR request count in the label', () => {
    expect(
      buildOrgPageNavOptions({
        ...base,
        canReviewMmr: true,
        mmrPendingCount: 3,
      }),
    ).toContainEqual({ value: 'mmr-requests', label: 'MMR requests (3)' });
  });

  it('omits MMR requests for a plain member', () => {
    expect(values(base)).not.toContain('mmr-requests');
  });

  it('never lists settings; settings open from the header cog', () => {
    expect(
      values({
        ...base,
        canViewMembers: true,
        standingTabs: tracks,
        canUsePromotion: true,
        canViewClaims: true,
      }),
    ).not.toContain('settings');
  });

  it('labels standing tabs with the track label', () => {
    expect(buildOrgPageNavOptions({ ...base, standingTabs: tracks })).toEqual([
      { value: 'leagues', label: 'Leagues (2)' },
      { value: 'events', label: 'Events (3)' },
      { value: 'contributions', label: 'Contributions' },
      { value: 'conduct', label: 'Conduct' },
    ]);
  });

  it('keeps the tab order of the desktop tab list', () => {
    expect(
      values({
        ...base,
        canViewMembers: true,
        standingTabs: tracks,
        canUsePromotion: true,
        canViewClaims: true,
        canReviewMmr: true,
      }),
    ).toEqual([
      'leagues',
      'events',
      'users',
      'contributions',
      'conduct',
      'promotion',
      'claims',
      'mmr-requests',
    ]);
  });
});
