import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get, post } }));

import {
  fetchEventOpsNotices,
  fetchOrgOpsNotices,
  OpsNoticeSchema,
  resolveEventOpsNotice,
} from '../opsNoticesAPI';

const notice = {
  id: 7,
  key: 'future.type',
  label: 'Future type',
  category: 'urgent',
  severity: 'warning',
  state: 'open',
  summary: 'Something needs attention',
  event_id: 3,
  event_name: 'Night 4',
  subject_user: { id: 2, username: 'alice', nickname: null, avatar: null },
  actor: null,
  dedupe_key: '',
  occurrences: 1,
  first_seen_at: '2026-11-17T10:00:00Z',
  last_seen_at: '2026-11-17T10:05:00Z',
  closed_at: null,
  close_note: '',
  delivery_state: 'pending',
  payload: { anything: 1 },
};

function requestedParams(): URLSearchParams {
  const url = get.mock.calls[0][0] as string;
  return new URLSearchParams(url.split('?')[1] ?? '');
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockResolvedValue({ data: [] });
});

describe('OpsNoticeSchema', () => {
  it('accepts an unknown future key', () => {
    expect(OpsNoticeSchema.parse(notice).key).toBe('future.type');
  });

  it('rejects an unknown severity', () => {
    expect(
      OpsNoticeSchema.safeParse({ ...notice, severity: 'catastrophic' })
        .success,
    ).toBe(false);
  });
});

describe('fetchEventOpsNotices', () => {
  it('fetchEventOpsNotices builds query params', async () => {
    await fetchEventOpsNotices(3, {
      state: 'open',
      category: ['urgent', 'task'],
    });
    const url = get.mock.calls[0][0] as string;
    expect(url.startsWith('/events/3/ops-notices/?')).toBe(true);
    expect(requestedParams().get('state')).toBe('open');
    expect(requestedParams().get('category')).toBe('urgent,task');
  });

  it('omits unset params', async () => {
    await fetchEventOpsNotices(3, {});
    expect(get.mock.calls[0][0]).toBe('/events/3/ops-notices/');
  });

  it('parses the response rows', async () => {
    get.mockResolvedValue({ data: [notice] });
    const rows = await fetchEventOpsNotices(3, {});
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe(7);
  });

  it('throws on a malformed response', async () => {
    get.mockResolvedValue({ data: [{ ...notice, category: 'nope' }] });
    await expect(fetchEventOpsNotices(3, {})).rejects.toThrow();
  });
});

describe('fetchOrgOpsNotices', () => {
  it('uses the organization path', async () => {
    await fetchOrgOpsNotices(5, { state: 'all' });
    const url = get.mock.calls[0][0] as string;
    expect(url).toBe('/organizations/5/ops-notices/?state=all');
  });
});

describe('resolveEventOpsNotice', () => {
  it('posts the reason and parses the row', async () => {
    post.mockResolvedValue({ data: { ...notice, state: 'resolved' } });
    const row = await resolveEventOpsNotice(3, 7, 'done');
    expect(post).toHaveBeenCalledWith('/events/3/ops-notices/7/resolve/', {
      reason: 'done',
    });
    expect(row.state).toBe('resolved');
  });

  it('sends an empty body without a reason', async () => {
    post.mockResolvedValue({ data: notice });
    await resolveEventOpsNotice(3, 7);
    expect(post).toHaveBeenCalledWith('/events/3/ops-notices/7/resolve/', {});
  });
});
