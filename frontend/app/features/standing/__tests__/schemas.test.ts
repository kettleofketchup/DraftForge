import { describe, expect, it } from 'vitest';
import {
  defaultMetric,
  StandingLeaderboardSchema,
  TrackInfoSchema,
  type TrackInfo,
} from '../schemas';

const tracksPayload = [
  {
    key: 'contribution',
    label: 'Contributions',
    metrics: [
      {
        key: 'points',
        label: 'Points',
        format: 'int',
        periodic: true,
        default: true,
      },
      {
        key: 'entries',
        label: 'Entries',
        format: 'int',
        periodic: true,
        default: false,
      },
    ],
    can_view_rows: true,
    can_view_own: true,
    board_open: true,
    can_manage: false,
    can_moderate: false,
    own_private: false,
  },
  {
    key: 'conduct',
    label: 'Conduct',
    metrics: [
      {
        key: 'show_rate',
        label: 'Show rate',
        format: 'percent',
        periodic: false,
        default: true,
      },
    ],
    can_view_rows: false,
    can_view_own: true,
    board_open: false,
    can_manage: false,
    can_moderate: false,
    own_private: false,
  },
];

const member = (pk: number) => ({
  org_user_pk: pk,
  user_pk: pk + 100,
  username: `u${pk}`,
  nickname: null,
  avatarUrl: null,
});

describe('standing schemas', () => {
  it('parses a tracks payload', () => {
    const tracks = TrackInfoSchema.array().parse(tracksPayload);
    expect(tracks.map((t) => t.key)).toEqual(['contribution', 'conduct']);
    expect(tracks[0].metrics).toHaveLength(2);
    expect(tracks[1].metrics[0]).toEqual({
      key: 'show_rate',
      label: 'Show rate',
      format: 'percent',
      periodic: false,
      default: true,
    });
    expect(tracks[1].board_open).toBe(false);
  });

  it('parses a conduct leaderboard with a ranked and a new row', () => {
    const board = StandingLeaderboardSchema.parse({
      track: 'conduct',
      metric: tracksPayload[1].metrics[0],
      period: 'all',
      total: null,
      rows: [
        { member: member(1), value: 0.912, sample: 12, status: 'ranked' },
        { member: member(2), value: null, sample: 1, status: 'new' },
      ],
      rows_visible: true,
      own_row: { member: member(2), value: null, sample: 1, status: 'new' },
      own_private: false,
    });
    expect(board.rows[0].value).toBe(0.912);
    expect(board.rows[1].status).toBe('new');
    expect(board.own_row?.member.org_user_pk).toBe(2);
  });

  it('parses own_private on a track and a leaderboard', () => {
    const track = TrackInfoSchema.parse({
      ...tracksPayload[1],
      own_private: true,
    });
    expect(track.own_private).toBe(true);
    const board = StandingLeaderboardSchema.parse({
      track: 'leadership',
      metric: tracksPayload[1].metrics[0],
      period: 'all',
      total: null,
      rows: [],
      rows_visible: true,
      own_row: null,
      own_private: true,
    });
    expect(board.own_private).toBe(true);
  });

  it('requires own_private', () => {
    const { own_private: _own, ...rest } = tracksPayload[1];
    expect(TrackInfoSchema.safeParse(rest).success).toBe(false);
  });

  it('rejects an unknown metric format', () => {
    const bad = structuredClone(tracksPayload[1]);
    bad.metrics[0].format = 'stars';
    expect(TrackInfoSchema.safeParse(bad).success).toBe(false);
  });

  it('rejects a track with no metrics', () => {
    expect(
      TrackInfoSchema.safeParse({ ...tracksPayload[0], metrics: [] }).success,
    ).toBe(false);
  });

  it('defaultMetric picks the default metric, else the first', () => {
    const [contribution, conduct] =
      TrackInfoSchema.array().parse(tracksPayload);
    expect(defaultMetric(contribution).key).toBe('points');
    expect(defaultMetric(conduct).key).toBe('show_rate');
    const noDefault: TrackInfo = {
      ...contribution,
      metrics: contribution.metrics
        .map((m) => ({ ...m, default: false }))
        .reverse(),
    };
    expect(defaultMetric(noDefault).key).toBe('entries');
  });
});
