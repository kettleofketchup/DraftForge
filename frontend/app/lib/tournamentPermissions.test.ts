import { describe, expect, it } from 'vitest';
import {
  canAdminLeague,
  canCreateTournament,
  canEditTournament,
  isSiteStaff,
  leagueOptionsFor,
} from './tournamentPermissions';

const plain = {
  pk: 1,
  is_staff: false,
  is_superuser: false,
  admin_organization_ids: [],
  staff_organization_ids: [],
  admin_league_ids: [],
  staff_league_ids: [],
};
const staff = { ...plain, is_staff: true };
const superuser = { ...plain, is_superuser: true };

type L = {
  pk: number;
  name: string;
  organization?: { pk: number } | null;
  organization_id?: number;
};
const league9: L = { pk: 9, name: 'L9', organization: { pk: 8 } };
const league10: L = { pk: 10, name: 'L10', organization: { pk: 8 } };
const league20: L = { pk: 20, name: 'L20', organization: { pk: 7 } };
const league21: L = { pk: 21, name: 'L21', organization_id: 7 };
const all = [league9, league10, league20, league21];

describe('isSiteStaff', () => {
  it('is true for is_staff', () => expect(isSiteStaff(staff)).toBe(true));
  it('is true for is_superuser', () =>
    expect(isSiteStaff(superuser)).toBe(true));
  it('is false for a plain user', () => expect(isSiteStaff(plain)).toBe(false));
  it('is false for undefined', () =>
    expect(isSiteStaff(undefined)).toBe(false));
});

describe('canCreateTournament', () => {
  it('is true for is_staff', () =>
    expect(canCreateTournament(staff)).toBe(true));
  it('is false for a superuser without is_staff', () =>
    expect(
      canCreateTournament({ ...plain, is_superuser: true, is_staff: false }),
    ).toBe(false));
  it('is false for undefined', () =>
    expect(canCreateTournament(undefined)).toBe(false));
});

describe('canEditTournament', () => {
  it('site staff can edit a leagueless tournament', () =>
    expect(
      canEditTournament(staff, { leaguePk: null, leagueOrgPk: null }),
    ).toBe(true));
  it('org admin cannot edit a leagueless tournament', () =>
    expect(
      canEditTournament(
        { ...plain, admin_organization_ids: [8] },
        { leaguePk: null, leagueOrgPk: 8 },
      ),
    ).toBe(false));
  it('league staff can edit', () =>
    expect(
      canEditTournament(
        { ...plain, staff_league_ids: [9] },
        { leaguePk: 9, leagueOrgPk: 8 },
      ),
    ).toBe(true));
  it('org staff can edit', () =>
    expect(
      canEditTournament(
        { ...plain, staff_organization_ids: [8] },
        { leaguePk: 9, leagueOrgPk: 8 },
      ),
    ).toBe(true));
  it('league with no org is not editable via an unrelated org admin', () =>
    expect(
      canEditTournament(
        { ...plain, admin_organization_ids: [8] },
        { leaguePk: 9, leagueOrgPk: null },
      ),
    ).toBe(false));
  it('org admin can edit', () =>
    expect(
      canEditTournament(
        { ...plain, admin_organization_ids: [8] },
        { leaguePk: 9, leagueOrgPk: 8 },
      ),
    ).toBe(true));
  it('member with empty arrays cannot edit', () =>
    expect(canEditTournament(plain, { leaguePk: 9, leagueOrgPk: 8 })).toBe(
      false,
    ));
  it('undefined user / missing id arrays return false without throwing', () => {
    expect(canEditTournament(undefined, { leaguePk: 9, leagueOrgPk: 8 })).toBe(
      false,
    );
    expect(canEditTournament(null, { leaguePk: 9, leagueOrgPk: 8 })).toBe(
      false,
    );
    expect(canEditTournament({ pk: 1 }, { leaguePk: 9, leagueOrgPk: 8 })).toBe(
      false,
    );
  });
});

describe('canAdminLeague', () => {
  it('league admin can admin', () =>
    expect(canAdminLeague({ ...plain, admin_league_ids: [9] }, league9)).toBe(
      true,
    ));
  it('org admin via organization.pk can admin', () =>
    expect(
      canAdminLeague({ ...plain, admin_organization_ids: [8] }, league9),
    ).toBe(true));
  it('org admin via organization_id can admin', () =>
    expect(
      canAdminLeague({ ...plain, admin_organization_ids: [7] }, league21),
    ).toBe(true));
  it('league staff only cannot admin', () =>
    expect(canAdminLeague({ ...plain, staff_league_ids: [9] }, league9)).toBe(
      false,
    ));
  it('site staff can admin', () =>
    expect(canAdminLeague(staff, league20)).toBe(true));
  it('missing id arrays return false', () =>
    expect(canAdminLeague({ pk: 1 }, league9)).toBe(false));
});

describe('leagueOptionsFor', () => {
  it('site staff gets all leagues and may clear', () =>
    expect(
      leagueOptionsFor(staff, all, { currentLeague: null, eventOrgPk: null }),
    ).toEqual({
      options: all,
      allowNone: true,
      locked: false,
    }));

  it('org admin sees only their org leagues and may not clear', () =>
    expect(
      leagueOptionsFor({ ...plain, admin_organization_ids: [8] }, all, {
        currentLeague: league9,
        eventOrgPk: null,
      }),
    ).toEqual({
      options: [league9, league10],
      allowNone: false,
      locked: false,
    }));

  it('eventOrgPk filter drops other-org leagues even for site staff', () =>
    expect(
      leagueOptionsFor(staff, all, { currentLeague: null, eventOrgPk: 7 })
        .options,
    ).toEqual([league20, league21]));

  it('locks current league the user cannot admin', () =>
    expect(
      leagueOptionsFor({ ...plain, staff_league_ids: [9] }, all, {
        currentLeague: league9,
        eventOrgPk: null,
      }),
    ).toEqual({ options: [league9], allowNone: false, locked: true }));

  it('current league missing from list is still returned', () => {
    const result = leagueOptionsFor(
      { ...plain, staff_league_ids: [9] },
      [league20, league21],
      {
        currentLeague: league9,
        eventOrgPk: null,
      },
    );
    expect(result.options).toEqual([league9]);
    expect(result.locked).toBe(true);
  });

  it('admin of a current league missing from the list keeps it alongside admin-able leagues', () => {
    const result = leagueOptionsFor(
      { ...plain, admin_league_ids: [9], admin_organization_ids: [7] },
      [league20, league21],
      { currentLeague: league9, eventOrgPk: null },
    );
    expect(result.locked).toBe(false);
    expect(result.allowNone).toBe(false);
    expect(result.options).toHaveLength(3);
    expect(result.options).toEqual(
      expect.arrayContaining([league9, league20, league21]),
    );
  });

  it('site staff with a current league missing from the list still gets it', () => {
    const result = leagueOptionsFor(staff, [league10], {
      currentLeague: league9,
      eventOrgPk: null,
    });
    expect(result.options).toEqual(expect.arrayContaining([league9, league10]));
    expect(result.options).toHaveLength(2);
  });

  it('undefined user gets no options', () =>
    expect(
      leagueOptionsFor(undefined, all, {
        currentLeague: null,
        eventOrgPk: null,
      }),
    ).toEqual({
      options: [],
      allowNone: false,
      locked: false,
    }));
});
