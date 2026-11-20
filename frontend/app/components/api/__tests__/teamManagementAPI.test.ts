import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get, post } }));

import {
  addTeamStandin,
  fetchManagedTeam,
  fetchTeamHistory,
  isTeamManagementError,
  ManagedTeamSchema,
  markTeamDropout,
  removeTeamStandin,
  renameTeam,
  restoreTeamMember,
  runTeamAction,
  setTeamCaptain,
  setTeamDeputy,
  subInTeamStandin,
  TeamHistoryPageSchema,
  type TeamAction,
} from '../teamManagementAPI';
import fixtures from './fixtures/managedTeam.json';
import historyPage from './fixtures/teamHistoryPage.json';

const { managedTeam, ghostCaptainTeam } = fixtures;
const body = { reason: 'r', acknowledged_codes: [] };

function axiosError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('failed', String(status), config, undefined, {
    status,
    statusText: '',
    headers: {},
    config,
    data,
  });
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  post.mockResolvedValue({ data: managedTeam });
  get.mockResolvedValue({ data: historyPage });
});

describe('ManagedTeamSchema', () => {
  it('parses a captured team detail payload', () => {
    const parsed = ManagedTeamSchema.safeParse(managedTeam);
    expect(parsed.success).toBe(true);
    const team = parsed.data!;
    expect(typeof team.left_members[0].pk).toBe('number');
    expect(team.members[0].avatarUrl).toBeNull();
    expect(team.members[0].discordId).toBeNull();
    expect(team.can_manage_team).toBe(true);
    expect(team.leadership_problems).toEqual([]);
  });

  it('parses a ghost captain with its leadership problem', () => {
    const team = ManagedTeamSchema.parse(ghostCaptainTeam);
    expect(team.deputy_captain).toBeNull();
    expect(team.leadership_problems[0].code).toBe('captain_not_member');
    expect(team.leadership_problems[0].field).toBe('captain');
  });

  it('parses the manager-only picker scope', () => {
    const team = ManagedTeamSchema.parse({
      ...managedTeam,
      other_team_user_pks: [6],
    });
    expect(team.organization_pk).toBe(7);
    expect(team.league_pk).toBe(3);
    expect(team.other_team_user_pks).toEqual([6]);
  });

  it('accepts a viewer payload without the picker scope', () => {
    const {
      organization_pk: _org,
      league_pk: _league,
      other_team_user_pks: _others,
      ...viewer
    } = managedTeam;
    const team = ManagedTeamSchema.parse({ ...viewer, can_manage_team: false });
    expect(team.organization_pk).toBeUndefined();
    expect(team.other_team_user_pks).toBeUndefined();
  });

  it('accepts a team without a tournament', () => {
    expect(
      ManagedTeamSchema.safeParse({ ...managedTeam, tournament: null }).success,
    ).toBe(true);
  });

  it('accepts a legacy team with a null draft_order', () => {
    const team = ManagedTeamSchema.parse({ ...managedTeam, draft_order: null });
    expect(team.draft_order).toBeNull();
  });

  it('rejects an unknown leadership problem code', () => {
    const bad = {
      ...ghostCaptainTeam,
      leadership_problems: [{ field: 'captain', code: 'nope', message: 'x' }],
    };
    expect(ManagedTeamSchema.safeParse(bad).success).toBe(false);
  });
});

describe('TeamHistoryPageSchema', () => {
  it('parses a captured page with a system row', () => {
    const page = {
      ...historyPage,
      results: [
        historyPage.results[0],
        { ...historyPage.results[1], actor: null, via: 'system' },
      ],
    };
    const parsed = TeamHistoryPageSchema.parse(page);
    expect(parsed.results).toHaveLength(2);
    expect(parsed.results[1].actor).toBeNull();
    expect(parsed.results[0].target?.pk).toBe(historyPage.results[0].target.pk);
  });
});

describe('isTeamManagementError', () => {
  it('is true for a coded 400', () => {
    const err = axiosError(400, {
      code: 'not_member',
      detail: 'X is not on the team.',
    });
    expect(isTeamManagementError(err)).toBe(true);
  });

  it('is false for a 403 not_permitted', () => {
    const err = axiosError(403, { code: 'not_permitted', detail: 'No.' });
    expect(isTeamManagementError(err)).toBe(false);
  });

  it('is false for a 409 override body', () => {
    const err = axiosError(409, {
      code: 'override_required',
      blocked: false,
      violations: [],
    });
    expect(isTeamManagementError(err)).toBe(false);
  });

  it('is false for a 400 field error and non-axios errors', () => {
    expect(isTeamManagementError(axiosError(400, { reason: ['x'] }))).toBe(
      false,
    );
    expect(isTeamManagementError(new Error('x'))).toBe(false);
  });
});

describe('team actions', () => {
  it('addTeamStandin posts the body and parses the team', async () => {
    const team = await addTeamStandin(5, { user_id: 7, ...body });
    expect(post).toHaveBeenCalledWith('/teams/5/standins/', {
      user_id: 7,
      ...body,
    });
    expect(team.pk).toBe(managedTeam.pk);
  });

  it.each([
    ['removeTeamStandin', removeTeamStandin, '/teams/5/standins/remove/'],
    ['setTeamCaptain', setTeamCaptain, '/teams/5/set-captain/'],
    ['markTeamDropout', markTeamDropout, '/teams/5/dropout/'],
    ['restoreTeamMember', restoreTeamMember, '/teams/5/restore/'],
  ] as const)('%s hits its endpoint', async (_name, fn, url) => {
    await fn(5, { user_id: 7, ...body });
    expect(post).toHaveBeenCalledWith(url, { user_id: 7, ...body });
  });

  it('setTeamDeputy can clear the deputy', async () => {
    await setTeamDeputy(5, { user_id: null, ...body });
    expect(post).toHaveBeenCalledWith('/teams/5/set-deputy/', {
      user_id: null,
      ...body,
    });
  });

  it('subInTeamStandin posts both ids', async () => {
    await subInTeamStandin(5, { standin_id: 7, replacing_id: 8, ...body });
    expect(post).toHaveBeenCalledWith('/teams/5/sub-in/', {
      standin_id: 7,
      replacing_id: 8,
      ...body,
    });
  });

  it('renameTeam posts the name', async () => {
    await renameTeam(5, { name: 'New', ...body });
    expect(post).toHaveBeenCalledWith('/teams/5/rename/', {
      name: 'New',
      ...body,
    });
  });

  it('rejects a malformed response', async () => {
    post.mockResolvedValue({ data: { ...managedTeam, members: 'x' } });
    await expect(addTeamStandin(5, { user_id: 7, ...body })).rejects.toThrow();
  });

  it('propagates errors unchanged', async () => {
    const err = axiosError(409, { code: 'override_required' });
    post.mockRejectedValue(err);
    await expect(markTeamDropout(5, { user_id: 7, ...body })).rejects.toBe(err);
  });
});

describe('fetchTeamHistory', () => {
  it('requests the page', async () => {
    const page = await fetchTeamHistory(5, 2);
    expect(get).toHaveBeenCalledWith('/teams/5/history/', {
      params: { page: 2 },
    });
    expect(page.count).toBe(historyPage.count);
  });

  it('sends page_size when given', async () => {
    await fetchTeamHistory(5, 1, 50);
    expect(get).toHaveBeenCalledWith('/teams/5/history/', {
      params: { page: 1, page_size: 50 },
    });
  });
});

describe('fetchManagedTeam', () => {
  it('GETs the team detail and parses it', async () => {
    get.mockResolvedValue({ data: managedTeam });
    const team = await fetchManagedTeam(7);
    expect(get).toHaveBeenCalledWith('/teams/7/');
    expect(team.pk).toBe(managedTeam.pk);
    expect(team.can_manage_team).toBe(true);
  });

  it('rejects a malformed response', async () => {
    get.mockResolvedValue({ data: { ...managedTeam, can_manage_team: 'x' } });
    await expect(fetchManagedTeam(7)).rejects.toThrow();
  });
});

describe('runTeamAction', () => {
  const team = ManagedTeamSchema.parse(managedTeam);
  const [captain, , member] = team.members;
  const standin = team.dropin_members[0];
  const ackBody = {
    reason: 'because',
    acknowledged_codes: ['team_standin_cap'],
  };

  it.each<[string, TeamAction, string, Record<string, unknown>]>([
    [
      'set_captain',
      { kind: 'set_captain', user: member },
      'set-captain',
      { user_id: member.pk },
    ],
    [
      'set_deputy',
      { kind: 'set_deputy', user: member },
      'set-deputy',
      { user_id: member.pk },
    ],
    [
      'set_deputy (clear)',
      { kind: 'set_deputy', user: null },
      'set-deputy',
      { user_id: null },
    ],
    [
      'mark_dropout',
      { kind: 'mark_dropout', user: member },
      'dropout',
      { user_id: member.pk },
    ],
    [
      'restore_member',
      { kind: 'restore_member', user: member },
      'restore',
      { user_id: member.pk },
    ],
    [
      'add_standin',
      { kind: 'add_standin', user: standin },
      'standins',
      { user_id: standin.pk },
    ],
    [
      'remove_standin',
      { kind: 'remove_standin', user: standin },
      'standins/remove',
      { user_id: standin.pk },
    ],
    [
      'sub_in',
      { kind: 'sub_in', standin, replacing: captain },
      'sub-in',
      { standin_id: standin.pk, replacing_id: captain.pk },
    ],
    [
      'sub_in (no replacing)',
      { kind: 'sub_in', standin, replacing: null },
      'sub-in',
      { standin_id: standin.pk, replacing_id: null },
    ],
  ])('%s posts its endpoint and body', async (_name, action, path, ids) => {
    const result = await runTeamAction(5, action, ackBody);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(`/teams/5/${path}/`, {
      ...ids,
      ...ackBody,
    });
    expect(result.pk).toBe(managedTeam.pk);
  });

  it('propagates errors unchanged', async () => {
    const err = axiosError(409, { code: 'override_required' });
    post.mockRejectedValue(err);
    await expect(
      runTeamAction(5, { kind: 'add_standin', user: standin }, body),
    ).rejects.toBe(err);
  });
});
