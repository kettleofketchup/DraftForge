import { describe, expect, it } from 'vitest';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import {
  ATTENDANCE_STATES,
  eventConductEnabled,
  FORECAST_STATES,
} from '../eventConduct';

const access = makeOrgFeatureAccess({ settled: true, viewerPk: 11 });
const staffEvent = { user_can_manage: true, organization: 3 };
const conductOrg = { features: ['conduct'] };

describe('eventConductEnabled', () => {
  it('is true for event staff of an org with conduct once access settles', () => {
    expect(eventConductEnabled(staffEvent, conductOrg, access)).toBe(true);
  });

  it.each([
    [
      'non-staff',
      { user_can_manage: false, organization: 3 },
      conductOrg,
      access,
    ],
    [
      'null org',
      { user_can_manage: true, organization: null },
      conductOrg,
      access,
    ],
    ['feature missing', staffEvent, { features: ['promotion'] }, access],
    ['features undefined', staffEvent, {}, access],
    ['no event', undefined, conductOrg, access],
    ['no org payload', staffEvent, undefined, access],
    [
      'not settled',
      staffEvent,
      conductOrg,
      makeOrgFeatureAccess({ settled: false, viewerPk: 11 }),
    ],
  ])('is false for %s', (_label, event, org, a) => {
    expect(eventConductEnabled(event, org, a)).toBe(false);
  });
});

describe('event state sets', () => {
  it('forecasts before the event starts', () => {
    expect([...FORECAST_STATES].sort()).toEqual(
      ['roll_call', 'signups_open', 'upcoming'].sort(),
    );
  });

  it('shows attendance from roll call on', () => {
    expect([...ATTENDANCE_STATES].sort()).toEqual(
      ['cancelled', 'completed', 'in_progress', 'roll_call'].sort(),
    );
  });
});
