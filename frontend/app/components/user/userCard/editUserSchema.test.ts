import { beforeEach, describe, expect, it, vi } from 'vitest';
import { updateOrgUser } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserClassType, UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserEntry } from '~/store/userCacheTypes';
import {
  buildDefaults,
  dispatchPatch,
  editableGames,
  EditUserSchema,
  pickDirty,
  resolveEditScope,
  resolveOrgUserLink,
  scopeToContext,
  type EditUserScope,
} from './editUserSchema';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  updateOrgUser: vi.fn(),
}));

const league = { pk: 7, name: 'L' } as LeagueType;

describe('scopeToContext org-id chain', () => {
  it('prefers scope.orgId for league scope', () => {
    const scope: EditUserScope = { kind: 'league', league, orgId: 42 };
    expect(scopeToContext(scope)).toEqual({ orgId: 42 });
  });

  it('falls back to league.organization.pk when orgId absent', () => {
    const scope: EditUserScope = {
      kind: 'league',
      league: { pk: 7, name: 'L', organization: { pk: 9 } } as LeagueType,
    };
    expect(scopeToContext(scope)).toEqual({ orgId: 9 });
  });
});

const org = { pk: 2, name: 'Org' } as OrganizationType;
const lg = { pk: 5, name: 'League' } as LeagueType;

// Minimal UserEntry-shaped object (isUserEntry checks `'orgData' in user`).
function entry(over: Partial<UserEntry> = {}): UserEntry {
  return {
    pk: 1,
    username: 'u',
    orgData: {},
    leagueData: {},
    _fetchedAt: 0,
    ...over,
  } as UserEntry;
}

describe('resolveOrgUserLink', () => {
  it('returns the flat orgUserPk when present', () => {
    expect(resolveOrgUserLink({ orgUserPk: 110 }, { organizationId: 2 })).toBe(
      110,
    );
  });

  it('falls back to orgData[orgId].id for a UserEntry without a flat field', () => {
    const u = entry({
      orgData: { 2: { id: 110, mmrs: { 1: 0 }, _fetchedAt: 0 } },
    });
    expect(resolveOrgUserLink(u, { organizationId: 2 })).toBe(110);
  });

  it('falls back to leagueData[leagueId].id', () => {
    const u = entry({ leagueData: { 5: { id: 111, mmr: 0, _fetchedAt: 0 } } });
    expect(resolveOrgUserLink(u, { leagueId: 5 })).toBe(111);
  });

  it('returns undefined for a plain user with no link', () => {
    expect(resolveOrgUserLink({ username: 'u' } as never, {})).toBeUndefined();
  });
});

describe('resolveEditScope game context', () => {
  it('carries ctx.gameType onto league and org scopes', () => {
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        {
          organizationId: 2,
          leagueId: 5,
          currentOrg: org,
          currentLeague: lg,
          gameType: 2,
        },
      ),
    ).toEqual({ kind: 'league', league: lg, orgId: 2, gameType: 2 });
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        {
          organizationId: 2,
          currentOrg: org,
          currentLeague: null,
          gameType: 2,
        },
      ),
    ).toEqual({ kind: 'org', organization: org, gameType: 2 });
  });
});

describe('resolveEditScope', () => {
  it('no link -> global', () => {
    expect(
      resolveEditScope({ username: 'u' } as never, {
        organizationId: 2,
        leagueId: 5,
        currentOrg: org,
        currentLeague: lg,
      }),
    ).toEqual({ kind: 'global' });
  });

  it('flat link + leagueId matches currentLeague -> league with deterministic orgId', () => {
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        {
          organizationId: 2,
          leagueId: 5,
          currentOrg: org,
          currentLeague: lg,
        },
      ),
    ).toEqual({ kind: 'league', league: lg, orgId: 2 });
  });

  it('flat link + currentLeague stale/absent + currentOrg present -> org', () => {
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        {
          organizationId: 2,
          leagueId: 5,
          currentOrg: org,
          currentLeague: null,
        },
      ),
    ).toEqual({ kind: 'org', organization: org });
  });

  it('flat link + neither store loaded -> global (safe degrade)', () => {
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        {
          organizationId: 2,
          leagueId: 5,
          currentOrg: null,
          currentLeague: null,
        },
      ),
    ).toEqual({ kind: 'global' });
  });

  it('UserEntry orgData-only link -> org', () => {
    const u = entry({
      orgData: { 2: { id: 110, mmrs: { 1: 0 }, _fetchedAt: 0 } },
    });
    expect(
      resolveEditScope(u, {
        organizationId: 2,
        currentOrg: org,
        currentLeague: null,
      }),
    ).toEqual({ kind: 'org', organization: org });
  });

  it('link present but MMR is 0 -> still scope-aware (gate keys on id, not mmr)', () => {
    const u = entry({
      orgData: { 2: { id: 110, mmrs: { 1: 0 }, _fetchedAt: 0 } },
    });
    expect(
      resolveEditScope(u, {
        organizationId: 2,
        leagueId: 5,
        currentOrg: org,
        currentLeague: lg,
      }),
    ).toEqual({ kind: 'league', league: lg, orgId: 2 });
  });

  it('/users invariant: link in orgData but NO org/league context + stale currentOrg -> global', () => {
    const u = entry({
      orgData: { 2: { id: 110, mmrs: { 1: 0 }, _fetchedAt: 0 } },
    });
    expect(
      resolveEditScope(u, { currentOrg: org, currentLeague: null }),
    ).toEqual({ kind: 'global' });
  });

  it('flat link but no organizationId + stale currentOrg -> global', () => {
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        { currentOrg: org, currentLeague: null },
      ),
    ).toEqual({ kind: 'global' });
  });

  it('flat link + currentOrg for a different org -> global', () => {
    expect(
      resolveEditScope(
        { orgUserPk: 110 },
        {
          organizationId: 3,
          currentOrg: org,
          currentLeague: null,
        },
      ),
    ).toEqual({ kind: 'global' });
  });
});

// dispatchPatch — the org/league branches PATCH through a bare axios call that
// mutates nothing locally, unlike the global branch's User.dbUpdate. Without
// the write-back, the modal re-seeds pre-edit values on reopen and RHF reports
// the form clean, so a follow-up edit sends no request at all.
describe('dispatchPatch', () => {
  const mockUpdateOrgUser = vi.mocked(updateOrgUser);

  function userClass(over: Partial<UserClassType> = {}): UserClassType {
    return {
      pk: 1,
      username: 'u',
      nickname: 'Before',
      orgUserPk: 110,
      positions: {},
      dbUpdate: vi.fn(),
      ...over,
    } as unknown as UserClassType;
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('org scope PATCHes the OrgUser endpoint', async () => {
    mockUpdateOrgUser.mockResolvedValue({
      pk: 1,
      nickname: 'After',
    } as UserType);
    const user = userClass();
    await dispatchPatch(
      user,
      { kind: 'org', organization: org },
      { nickname: 'After' },
    );
    expect(mockUpdateOrgUser).toHaveBeenCalledWith(
      2,
      110,
      {
        nickname: 'After',
      },
      1,
    );
  });

  it('league scope PATCHes through the deterministic parent orgId', async () => {
    mockUpdateOrgUser.mockResolvedValue({
      pk: 1,
      nickname: 'After',
    } as UserType);
    const user = userClass();
    await dispatchPatch(
      user,
      { kind: 'league', league: lg, orgId: 2 },
      { nickname: 'After' },
    );
    expect(mockUpdateOrgUser).toHaveBeenCalledWith(
      2,
      110,
      {
        nickname: 'After',
      },
      1,
    );
  });

  it('mirrors the org response onto the instance so a reopen re-seeds fresh', async () => {
    mockUpdateOrgUser.mockResolvedValue({
      pk: 1,
      nickname: 'After',
    } as UserType);
    const user = userClass();
    await dispatchPatch(
      user,
      { kind: 'org', organization: org },
      { nickname: 'After' },
    );
    expect(user.nickname).toBe('After');
    expect(
      buildDefaults(user, { kind: 'org', organization: org }).nickname,
    ).toBe('After');
  });

  it('mirrors the league response onto the instance', async () => {
    mockUpdateOrgUser.mockResolvedValue({
      pk: 1,
      nickname: 'After',
    } as UserType);
    const user = userClass();
    const scope: EditUserScope = { kind: 'league', league: lg, orgId: 2 };
    await dispatchPatch(user, scope, { nickname: 'After' });
    expect(buildDefaults(user, scope).nickname).toBe('After');
  });

  it('sends the tournament id for a tournament-scoped league edit', async () => {
    mockUpdateOrgUser.mockResolvedValue({ pk: 1 } as UserType);
    const user = userClass();
    await dispatchPatch(
      user,
      { kind: 'league', league: lg, orgId: 2, tournamentId: 5 },
      { game_mmrs: { 1: 4200 } },
    );
    expect(mockUpdateOrgUser).toHaveBeenCalledWith(
      2,
      expect.anything(),
      expect.anything(),
      expect.anything(),
      5,
    );
  });

  it('keeps user.pk intact — OrgUserSerializer maps pk to the User pk', async () => {
    mockUpdateOrgUser.mockResolvedValue({
      pk: 1,
      orgUserPk: 110,
      nickname: 'After',
    } as UserType);
    const user = userClass();
    await dispatchPatch(
      user,
      { kind: 'org', organization: org },
      { nickname: 'After' },
    );
    expect(user.pk).toBe(1);
  });

  it('global scope delegates to dbUpdate, which assigns in place itself', async () => {
    const user = userClass({ orgUserPk: undefined });
    await dispatchPatch(user, { kind: 'global' }, { nickname: 'After' });
    expect(user.dbUpdate).toHaveBeenCalledWith({ nickname: 'After' });
    expect(mockUpdateOrgUser).not.toHaveBeenCalled();
  });

  it('league scope sends dirty game_mmrs with the context ?game_type', async () => {
    mockUpdateOrgUser.mockResolvedValue({ pk: 1, mmr: 2500 } as UserType);
    const scope: EditUserScope = {
      kind: 'league',
      league: lg,
      orgId: 2,
      gameType: 2,
    };
    await dispatchPatch(userClass(), scope, { game_mmrs: { '2': 2500 } });
    expect(mockUpdateOrgUser).toHaveBeenCalledWith(
      2,
      110,
      { game_mmrs: { 2: 2500 } },
      2,
    );
  });

  it('nickname-only edit sends no game_mmrs and keeps ?game_type', async () => {
    mockUpdateOrgUser.mockResolvedValue({ pk: 1 } as UserType);
    const scope: EditUserScope = {
      kind: 'league',
      league: lg,
      orgId: 2,
      gameType: 2,
    };
    await dispatchPatch(userClass(), scope, { nickname: 'After' });
    expect(mockUpdateOrgUser).toHaveBeenCalledWith(
      2,
      110,
      { nickname: 'After' },
      2,
    );
  });

  it('league scope without an OrgUser link throws rather than silently no-op', async () => {
    const user = userClass({ orgUserPk: undefined });
    await expect(
      dispatchPatch(
        user,
        { kind: 'league', league: lg, orgId: 2 },
        { nickname: 'After' },
      ),
    ).rejects.toThrow(/OrgUser link/);
  });
});

describe('org-less league tournament (spec 6.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('leagueData-only link -> league scope that PATCHes via the league parent org', async () => {
    const leagueWithOrg = {
      pk: 3,
      name: 'L3',
      organization: { pk: 5 },
    } as LeagueType;
    const ctx = {
      organizationId: undefined,
      leagueId: 3,
      currentOrg: { pk: 9, name: 'Stale' } as OrganizationType,
      currentLeague: leagueWithOrg,
    };
    const u = entry({
      pk: 10,
      leagueData: { 3: { id: 41, mmr: 0, _fetchedAt: 0 } },
    });
    const scope = resolveEditScope(u, ctx);
    expect(scope).toMatchObject({ kind: 'league', orgId: undefined });

    vi.mocked(updateOrgUser).mockResolvedValue({
      pk: 10,
      nickname: 'After',
    } as UserType);
    const user = {
      pk: 10,
      username: 'u',
      orgUserPk: resolveOrgUserLink(u, ctx),
      positions: {},
      dbUpdate: vi.fn(),
    } as unknown as UserClassType;
    await dispatchPatch(user, scope, { nickname: 'After' });
    expect(updateOrgUser).toHaveBeenCalledWith(5, 41, { nickname: 'After' }, 1);
  });
});

describe('per-game org MMR edit fields', () => {
  const mockUpdateOrgUser = vi.mocked(updateOrgUser);

  beforeEach(() => {
    vi.clearAllMocks();
    useUserCacheStore.getState().reset?.();
  });

  function plainUser(over: Partial<UserClassType> = {}): UserClassType {
    return {
      pk: 1,
      username: 'u',
      nickname: 'Nick',
      orgUserPk: 110,
      positions: {},
      dbUpdate: vi.fn(),
      ...over,
    } as unknown as UserClassType;
  }

  it('org scope edits every game, defaulted from the cache', () => {
    useUserCacheStore.setState({
      entities: {
        1: entry({
          pk: 1,
          orgData: {
            2: { id: 110, mmrs: { 1: 4200, 2: 2500 }, _fetchedAt: 0 },
          },
        }),
      },
    } as never);
    const scope: EditUserScope = { kind: 'org', organization: org };
    expect(editableGames(scope)).toEqual([1, 2]);
    expect(buildDefaults(plainUser(), scope).game_mmrs).toEqual({
      '1': 4200,
      '2': 2500,
    });
  });

  it('org scope falls back to the user game_mmrs payload', () => {
    const user = plainUser({ game_mmrs: { '1': 4000, '2': 0 } } as never);
    expect(
      buildDefaults(user, { kind: 'org', organization: org }).game_mmrs,
    ).toEqual({ '1': 4000, '2': 0 });
  });

  it('a Deadlock tournament scope edits only Deadlock, from the flat mmr', () => {
    useUserCacheStore.setState({
      entities: {
        1: entry({
          pk: 1,
          orgData: { 2: { id: 110, mmrs: { 1: 4200 }, _fetchedAt: 0 } },
        }),
      },
    } as never);
    const scope: EditUserScope = {
      kind: 'org',
      organization: org,
      gameType: 2,
    };
    expect(editableGames(scope)).toEqual([2]);
    expect(
      buildDefaults(plainUser({ mmr: 2600, mmr_game_type: 2 } as never), scope)
        .game_mmrs,
    ).toEqual({ '2': 2600 });
  });

  it('league scope without a game edits the league game only', () => {
    expect(editableGames({ kind: 'league', league: lg, orgId: 2 })).toEqual([
      1,
    ]);
  });

  it('global scope has no org MMR fields', () => {
    expect(editableGames({ kind: 'global' })).toEqual([]);
    expect(
      'game_mmrs' in buildDefaults(plainUser({ mmr: 1 }), { kind: 'global' }),
    ).toBe(false);
  });

  it('pickDirty keeps only the dirty games', () => {
    expect(
      pickDirty(
        {
          nickname: 'n',
          steam_account_id: null,
          positions: {} as never,
          game_mmrs: { '1': 4200, '2': 3000 },
        },
        { game_mmrs: { '2': true } } as never,
      ),
    ).toEqual({ game_mmrs: { '2': 3000 } });
  });

  it('a cleared field is sent as null', async () => {
    mockUpdateOrgUser.mockResolvedValue({ pk: 1 } as UserType);
    await dispatchPatch(
      plainUser(),
      { kind: 'org', organization: org },
      { game_mmrs: { '2': null } },
    );
    expect(mockUpdateOrgUser).toHaveBeenCalledWith(
      2,
      110,
      { game_mmrs: { 2: null } },
      1,
    );
  });

  it('never sends the legacy mmr key', async () => {
    mockUpdateOrgUser.mockResolvedValue({ pk: 1 } as UserType);
    await dispatchPatch(
      plainUser(),
      { kind: 'org', organization: org, gameType: 2 },
      { game_mmrs: { '2': 3000 } },
    );
    const body = mockUpdateOrgUser.mock.calls[0][2];
    expect(body).not.toHaveProperty('mmr');
    expect(body).not.toHaveProperty('mmr_game_type');
    expect(mockUpdateOrgUser.mock.calls[0][3]).toBe(2);
  });

  it('a legacy out-of-range value errors on its own field only', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Nick',
      steam_account_id: null,
      positions: {
        carry: 0,
        mid: 0,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
      game_mmrs: { '1': 25000, '2': 2500 },
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.map((i) => i.path.join('.'))).toEqual([
        'game_mmrs.1',
      ]);
    }
  });
});
