import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, patch, put, post, del } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
}));

vi.mock('~/components/api/axios', () => ({
  default: { get, patch, put, post, delete: del },
}));

import {
  deleteReview,
  deleteTrait,
  getEventReviews,
  getLeadershipSettings,
  getMemberLeadership,
  getMyReviews,
  getPendingReviews,
  getReviewDmPreview,
  getTraits,
  patchLeadershipSettings,
  putReview,
  putTraits,
  releaseResults,
  unvoidReview,
  voidReview,
} from '../api';
import {
  eventReviews,
  leadershipSettings,
  memberLeadership,
  moderationReview,
  myReview,
  pendingReview,
  traits,
} from './fixtures';

const BASE = '/organizations/1/leadership';

beforeEach(() => {
  for (const fn of [get, patch, put, post, del]) fn.mockReset();
});

describe('leadership api', () => {
  it('reads the org review DM preview and validates its Discord components', async () => {
    const payload = {
      messages: [
        {
          content: null,
          embeds: [],
          flags: 32768,
          allowed_mentions: null,
          components: [{ type: 10, content: 'Communication' }],
        },
      ],
    };
    get.mockResolvedValueOnce({ data: payload });
    expect(await getReviewDmPreview(1)).toEqual(payload);
    expect(get).toHaveBeenCalledWith(`${BASE}/review-dm-preview/`);
    get.mockResolvedValueOnce({
      data: {
        messages: [{ ...payload.messages[0], components: [{ type: -1 }] }],
      },
    });
    await expect(getReviewDmPreview(1)).rejects.toThrow(ZodError);
  });

  it('gets a member', async () => {
    get.mockResolvedValue({ data: memberLeadership() });
    const result = await getMemberLeadership(1, 7);
    expect(get).toHaveBeenCalledWith(`${BASE}/members/7/`);
    expect(result.member.org_user_pk).toBe(7);
  });

  it('rejects a malformed member payload', async () => {
    get.mockResolvedValue({ data: { ...memberLeadership(), rating: 'x' } });
    await expect(getMemberLeadership(1, 7)).rejects.toBeInstanceOf(ZodError);
  });

  it('gets pending reviews filtered by event', async () => {
    get.mockResolvedValue({ data: [pendingReview()] });
    const result = await getPendingReviews(1, 5);
    expect(get).toHaveBeenCalledWith(`${BASE}/reviews/pending/`, {
      params: { event_id: 5 },
    });
    expect(result).toHaveLength(1);
    expect(result[0].scores).toBeNull();
  });

  it('omits event_id when null', async () => {
    get.mockResolvedValue({ data: [] });
    await getPendingReviews(1, null);
    const [url, config] = get.mock.calls[0];
    expect(url).toBe(`${BASE}/reviews/pending/`);
    expect(config?.params ?? {}).not.toHaveProperty('event_id');
  });

  it('gets my reviews', async () => {
    get.mockResolvedValue({ data: [myReview()] });
    const result = await getMyReviews(1);
    expect(get).toHaveBeenCalledWith(`${BASE}/reviews/mine/`);
    expect(result[0].scores.drafting).toBe(3);
  });

  it('puts a review with the scores body', async () => {
    const scores = { communication: 4, drafting: 3 };
    put.mockResolvedValue({
      data: {
        scores,
        submitted_at: '2026-11-02T10:00:00Z',
        updated_at: '2026-11-02T10:00:00Z',
      },
    });
    const result = await putReview(1, 5, 7, scores);
    expect(put).toHaveBeenCalledWith(`${BASE}/events/5/captains/7/review/`, {
      scores,
    });
    expect(result.scores).toEqual(scores);
  });

  it('deletes a review', async () => {
    del.mockResolvedValue({ status: 204, data: '' });
    await expect(deleteReview(1, 5, 7)).resolves.toBeUndefined();
    expect(del).toHaveBeenCalledWith(`${BASE}/events/5/captains/7/review/`);
  });

  it('gets the event reviews', async () => {
    get.mockResolvedValue({ data: eventReviews() });
    const result = await getEventReviews(1, 5);
    expect(get).toHaveBeenCalledWith(`${BASE}/events/5/reviews/`);
    expect(result.captains[0].reviews).toHaveLength(1);
  });

  it('voids a review with a reason', async () => {
    post.mockResolvedValue({
      data: moderationReview({
        voided_at: '2026-11-03T10:00:00Z',
        void_kind: 'moderated',
        void_reason: 'spam',
      }),
    });
    const result = await voidReview(1, 31, 'spam');
    expect(post).toHaveBeenCalledWith(`${BASE}/reviews/31/void/`, {
      reason: 'spam',
    });
    expect(result.void_kind).toBe('moderated');
  });

  it('unvoids a review with an empty body', async () => {
    post.mockResolvedValue({ data: moderationReview() });
    const result = await unvoidReview(1, 31);
    expect(post).toHaveBeenCalledWith(`${BASE}/reviews/31/unvoid/`, {});
    expect(result.void_kind).toBe('');
  });

  it('releases every pending captain of an event with an empty body', async () => {
    post.mockResolvedValue({ data: { released: [7, 9], skipped: [] } });
    const result = await releaseResults(1, 5);
    expect(post).toHaveBeenCalledWith(`${BASE}/events/5/release/`, {});
    expect(result.released).toEqual([7, 9]);
  });

  it('releases a captain list', async () => {
    post.mockResolvedValue({ data: { released: [7], skipped: [] } });
    await releaseResults(1, 5, [7]);
    expect(post).toHaveBeenCalledWith(`${BASE}/events/5/release/`, {
      captains: [7],
    });
  });

  it('rejects a malformed release result', async () => {
    post.mockResolvedValue({ data: { released: 'x', skipped: [] } });
    await expect(releaseResults(1, 5)).rejects.toBeInstanceOf(ZodError);
  });

  it('gets the settings', async () => {
    get.mockResolvedValue({ data: leadershipSettings() });
    const result = await getLeadershipSettings(1);
    expect(get).toHaveBeenCalledWith(`${BASE}/settings/`);
    expect(result.defaults.review_window_hours).toBe(72);
  });

  it('patches the settings with the body passed through', async () => {
    patch.mockResolvedValue({
      data: leadershipSettings({ review_window_hours: 48 }),
    });
    const body = { review_window_hours: 48, points: { captained: null } };
    const result = await patchLeadershipSettings(1, body);
    expect(patch).toHaveBeenCalledWith(`${BASE}/settings/`, body);
    expect(result.review_window_hours).toBe(48);
  });

  it('gets the traits unwrapped', async () => {
    get.mockResolvedValue({ data: traits() });
    const result = await getTraits(1);
    expect(get).toHaveBeenCalledWith(`${BASE}/traits/`);
    expect(result.map((t) => t.key)).toEqual([
      'communication',
      'drafting',
      'composure',
      'sportsmanship',
    ]);
  });

  it('puts the traits wrapped and unwraps the answer', async () => {
    const items = [
      { key: 'communication', label: 'Talk', order: 0, active: true },
    ];
    put.mockResolvedValue({ data: { traits: items } });
    const result = await putTraits(1, items);
    expect(put).toHaveBeenCalledWith(`${BASE}/traits/`, { traits: items });
    expect(result).toEqual(items);
  });

  it('deletes a trait', async () => {
    del.mockResolvedValue({ status: 204, data: '' });
    await expect(deleteTrait(1, 'drafting')).resolves.toBeUndefined();
    expect(del).toHaveBeenCalledWith(`${BASE}/traits/drafting/`);
  });
});
