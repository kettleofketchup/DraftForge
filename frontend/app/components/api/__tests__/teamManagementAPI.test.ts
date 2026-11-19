import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get, post } }));

import {
  addTeamStandin,
  fetchTeamHistory,
  isTeamManagementError,
  ManagedTeamSchema,
  markTeamDropout,
  removeTeamStandin,
  renameTeam,
  restoreTeamMember,
  setTeamCaptain,
  setTeamDeputy,
  subInTeamStandin,
  TeamHistoryPageSchema,
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

  it('accepts a team without a tournament', () => {
    expect(
      ManagedTeamSchema.safeParse({ ...managedTeam, tournament: null }).success,
    ).toBe(true);
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
