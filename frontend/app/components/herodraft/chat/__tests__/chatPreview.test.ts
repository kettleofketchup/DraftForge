import { describe, expect, it } from 'vitest';
import {
  expirePreview,
  nextPreviewBoundary,
  PREVIEW_FADE_MS,
  PREVIEW_MAX_LINES,
  PREVIEW_TTL_MS,
  pushPreview,
  shouldPreview,
  teamRoster,
} from '~/components/herodraft/chat/chatPreview';
import type { ChatMessage, ChatViewer } from '~/components/herodraft/types';

const user = (pk: number) => ({
  pk,
  username: `u${pk}`,
  nickname: null,
  avatar: null,
});
const msg = (
  n: number,
  senderPk: number,
  extra: Partial<ChatMessage> = {},
): ChatMessage => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  channel: 'team',
  team_id: 12,
  kind: 'text',
  hero_id: null,
  body: `m${n}`,
  created_at: `2026-11-20T18:00:0${n}.000000Z`,
  sender: user(senderPk),
  ...extra,
});
const member: ChatViewer = {
  role: 'member',
  team_id: 12,
  can_post_team: true,
  can_post_all: true,
};
const spectator: ChatViewer = {
  role: 'spectator',
  team_id: null,
  can_post_team: false,
  can_post_all: false,
};
const roster = new Set([5, 6]);

describe('teamRoster', () => {
  it('collects captain and members of the viewer team', () => {
    const team = (
      tournament_team: number,
      captain: number,
      members: number[],
    ) =>
      ({
        tournament_team,
        captain: user(captain),
        members: members.map(user),
      }) as never;
    expect(teamRoster([team(11, 1, [2]), team(12, 5, [6, 7])], 12)).toEqual(
      new Set([5, 6, 7]),
    );
    expect(teamRoster([team(11, 1, [2])], 12)).toBeNull();
    expect(teamRoster(undefined, 12)).toBeNull();
    expect(teamRoster([team(12, 5, [])], null)).toBeNull();
  });
});

describe('shouldPreview', () => {
  const ctx = { viewer: member, selfId: 5, roster };

  it('member previews team chat from teammates', () => {
    expect(shouldPreview(msg(1, 6), ctx)).toBe(true);
  });

  it('member previews all chat only from their own team', () => {
    expect(
      shouldPreview(msg(1, 6, { channel: 'all', team_id: null }), ctx),
    ).toBe(true);
    expect(
      shouldPreview(msg(1, 9, { channel: 'all', team_id: null }), ctx),
    ).toBe(false);
  });

  it('member without a known roster drops all chat', () => {
    expect(
      shouldPreview(msg(1, 6, { channel: 'all', team_id: null }), {
        ...ctx,
        roster: null,
      }),
    ).toBe(false);
  });

  it('own suggestions preview, own text does not', () => {
    expect(shouldPreview(msg(1, 5), ctx)).toBe(false);
    expect(
      shouldPreview(msg(1, 5, { kind: 'suggest_pick', hero_id: 1 }), ctx),
    ).toBe(true);
  });

  it('spectators preview all chat from anyone', () => {
    expect(
      shouldPreview(msg(1, 9, { channel: 'all', team_id: null }), {
        viewer: spectator,
        selfId: 40,
        roster: null,
      }),
    ).toBe(true);
  });
});

describe('pushPreview / expirePreview', () => {
  it('collapses consecutive messages from one sender into a counted line', () => {
    let lines = pushPreview([], msg(1, 6), 0);
    lines = pushPreview(lines, msg(2, 6), 1000);
    lines = pushPreview(lines, msg(3, 6), 2000);
    expect(lines).toHaveLength(1);
    expect(lines[0].count).toBe(3);
    expect(lines[0].message.body).toBe('m3');
    expect(lines[0].expiresAt).toBe(2000 + PREVIEW_TTL_MS);
  });

  it('keeps at most two lines, newest replacing oldest', () => {
    let lines = pushPreview([], msg(1, 6), 0);
    lines = pushPreview(lines, msg(2, 7), 0);
    lines = pushPreview(lines, msg(3, 8), 0);
    expect(PREVIEW_MAX_LINES).toBe(2);
    expect(lines.map((l) => l.message.body)).toEqual(['m2', 'm3']);
  });

  it('does not merge with an expired line or a non-adjacent sender', () => {
    let lines = pushPreview([], msg(1, 6), 0);
    lines = pushPreview(lines, msg(2, 6), PREVIEW_TTL_MS);
    expect(lines.map((l) => l.count)).toEqual([1]);
    lines = pushPreview(lines, msg(3, 7), PREVIEW_TTL_MS);
    lines = pushPreview(lines, msg(4, 6), PREVIEW_TTL_MS);
    expect(lines.map((l) => l.message.body)).toEqual(['m3', 'm4']);
  });

  it('expires lines after the TTL and reports the next timer boundary', () => {
    const lines = pushPreview(pushPreview([], msg(1, 6), 0), msg(2, 7), 1000);
    expect(nextPreviewBoundary(lines, 0)).toBe(
      PREVIEW_TTL_MS - PREVIEW_FADE_MS,
    );
    expect(nextPreviewBoundary(lines, PREVIEW_TTL_MS - PREVIEW_FADE_MS)).toBe(
      PREVIEW_TTL_MS,
    );
    expect(expirePreview(lines, PREVIEW_TTL_MS)).toHaveLength(1);
    expect(expirePreview(lines, PREVIEW_TTL_MS + 1000)).toHaveLength(0);
    expect(nextPreviewBoundary([], 0)).toBeNull();
  });
});
