import { describe, expect, it } from 'vitest';

import {
  SIGNUP_LEDGER_ACTIONS,
  type SignupHistoryEntry,
  type SignupSnapshot,
} from '~/components/events/schemas';
import {
  actionLabel,
  actionTone,
  causePhrase,
  describeDiff,
  diffPartText,
  extraNotes,
  formatHistoryTime,
  meansLabel,
  originalSignupId,
  SIGNUP_ACTION_LABELS,
} from '~/components/events/signupHistory';

const snap = (over: Partial<SignupSnapshot> = {}): SignupSnapshot => ({
  status: 'waitlisted',
  commitment: 'main',
  rsvp_class: 'standard',
  signed_up_at: '2026-11-19T18:00:00Z',
  line_seq: 3,
  waitlist_position: 1,
  event_team_id: null,
  extra: {},
  ...over,
});

const subject = (userId: number, nickname: string) => ({
  user_id: userId,
  username: `user_${userId}`,
  nickname,
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
  discord_id: null,
});

const entry = (over: Partial<SignupHistoryEntry> = {}): SignupHistoryEntry => ({
  id: 1,
  occurred_at: '2026-11-20T18:03:00Z',
  action: 'approved',
  subject: subject(8, 'Cara'),
  actor: {
    user_id: null,
    username: null,
    nickname: null,
    discordNickname: null,
    guildNickname: null,
    avatarUrl: null,
    role: 'member',
  },
  means: 'web',
  on_behalf: false,
  reason: '',
  before: snap(),
  after: snap(),
  rules_overridden: [],
  caused_by: null,
  ...over,
});

describe('describeDiff', () => {
  it('created entry lists the after values', () => {
    const d = describeDiff(
      entry({
        action: 'signed_up',
        before: null,
        after: snap({ status: 'rsvp', waitlist_position: null }),
      }),
    );
    expect(d).toEqual([
      { field: 'status', from: null, to: 'rsvp' },
      { field: 'commitment', from: null, to: 'main' },
    ]);
  });

  it('after null is unavailable and does not throw', () => {
    expect(describeDiff(entry({ after: null }))).toEqual({ unavailable: true });
  });

  it('both null is unavailable', () => {
    expect(describeDiff(entry({ before: null, after: null }))).toEqual({
      unavailable: true,
    });
  });

  it('status change', () => {
    expect(
      describeDiff(
        entry({
          before: snap({ status: 'waitlisted', waitlist_position: null }),
          after: snap({ status: 'approved', waitlist_position: null }),
        }),
      ),
    ).toEqual([{ field: 'status', from: 'waitlisted', to: 'approved' }]);
  });

  it('commitment change', () => {
    expect(
      describeDiff(
        entry({
          action: 'switched_commitment',
          before: snap({ commitment: 'main' }),
          after: snap({ commitment: 'maybe' }),
        }),
      ),
    ).toEqual([{ field: 'commitment', from: 'main', to: 'maybe' }]);
  });

  it('waitlist position change', () => {
    expect(
      describeDiff(
        entry({
          before: snap({ waitlist_position: 3 }),
          after: snap({ waitlist_position: 2 }),
        }),
      ),
    ).toEqual([{ field: 'waitlist_position', from: 3, to: 2 }]);
  });

  it('line_seq-only change', () => {
    expect(
      describeDiff(
        entry({ before: snap({ line_seq: 3 }), after: snap({ line_seq: 9 }) }),
      ),
    ).toEqual([{ field: 'line_seq', from: 3, to: 9 }]);
  });

  it('omits unchanged fields', () => {
    expect(describeDiff(entry())).toEqual([]);
  });

  it('resigned_up moves to the end of the line without a sign-up time claim', () => {
    const e = entry({
      action: 'resigned_up',
      before: snap({
        status: 'cancelled',
        line_seq: 1,
        waitlist_position: null,
        signed_up_at: '2026-11-18T18:00:00Z',
      }),
      after: snap({
        status: 'waitlisted',
        line_seq: 7,
        waitlist_position: 2,
        signed_up_at: '2026-11-20T18:00:00Z',
      }),
    });
    const d = describeDiff(e);
    expect(Array.isArray(d)).toBe(true);
    const parts = d as Exclude<
      typeof d,
      { unavailable: true } | { note: string }
    >;
    expect(parts.map((p) => p.field)).toEqual([
      'status',
      'waitlist_position',
      'line_seq',
    ]);
    const texts = parts
      .filter((p) => p.field !== 'status')
      .map((p) => diffPartText(p, e.action));
    expect(texts).toContain('Moved to the end of the line');
    expect(texts.join(' ')).not.toMatch(/sign-up time|signed up at|kept/i);
  });

  it('account_merged duplicate returns the merge note', () => {
    expect(
      describeDiff(
        entry({
          action: 'account_merged',
          before: snap({
            status: 'rsvp',
            extra: {
              from_user_id: 4,
              discarded_duplicate: true,
              discarded_signup_id: 12,
            },
          }),
          after: snap({ status: 'approved' }),
        }),
      ),
    ).toEqual({
      note: 'Duplicate sign-up from merged account discarded; kept current sign-up',
    });
  });

  it('account_merged reassignment diffs normally', () => {
    expect(
      describeDiff(
        entry({
          action: 'account_merged',
          before: snap({ extra: { from_user_id: 4 } }),
          after: snap({ extra: { from_user_id: 4 } }),
        }),
      ),
    ).toEqual([]);
  });

  it('backfilled shows after.signed_up_at', () => {
    const e = entry({
      action: 'backfilled',
      before: null,
      after: snap({ status: 'approved', waitlist_position: null }),
    });
    const d = describeDiff(e);
    expect(d).toContainEqual({
      field: 'signed_up_at',
      from: null,
      to: '2026-11-19T18:00:00Z',
    });
  });
});

describe('diffPartText', () => {
  it('describes commitment, waitlist place and sign-up time', () => {
    expect(
      diffPartText({ field: 'commitment', from: 'main', to: 'maybe' }, 'x'),
    ).toBe('Main → Maybe');
    expect(
      diffPartText({ field: 'waitlist_position', from: null, to: 2 }, 'x'),
    ).toBe('#2 on the waitlist');
    expect(
      diffPartText({ field: 'waitlist_position', from: 2, to: null }, 'x'),
    ).toBe('Left the waitlist');
    expect(
      diffPartText(
        { field: 'signed_up_at', from: null, to: '2026-11-19T18:00:00Z' },
        'backfilled',
        'America/Chicago',
      ),
    ).toMatch(/^Signed up Nov 19.*12:00/);
  });
});

describe('originalSignupId', () => {
  it('marks a plain signed_up', () => {
    expect(
      originalSignupId([
        entry({ id: 3, action: 'withdrew' }),
        entry({ id: 2, action: 'signed_up' }),
      ]),
    ).toBe(2);
  });

  it('never marks a decline-only backfilled row', () => {
    expect(
      originalSignupId([
        entry({
          id: 1,
          action: 'backfilled',
          before: null,
          after: snap({ status: 'cancelled' }),
        }),
      ]),
    ).toBeNull();
  });

  it('declined then signed_up marks the signed_up', () => {
    expect(
      originalSignupId([
        entry({ id: 5, action: 'signed_up' }),
        entry({
          id: 1,
          action: 'backfilled',
          before: null,
          after: snap({ status: 'cancelled' }),
        }),
      ]),
    ).toBe(5);
  });

  it('marks a non-cancelled backfilled row', () => {
    expect(
      originalSignupId([
        entry({ id: 9, action: 'resigned_up' }),
        entry({
          id: 1,
          action: 'backfilled',
          before: null,
          after: snap({ status: 'approved' }),
        }),
      ]),
    ).toBe(1);
  });
});

describe('causePhrase', () => {
  const promoted = entry({ id: 10, action: 'promoted', caused_by: 4 });
  const cause = (action: string) =>
    new Map([[4, entry({ id: 4, action, subject: subject(5, 'Dane') })]]);

  it.each([
    ['withdrew', 'after Dane withdrew'],
    ['rejected', 'after Dane was rejected'],
    ['declined', 'after Dane declined'],
    ['switched_commitment', 'after Dane went tentative'],
    ['event_cancelled', 'after Dane: Event cancelled'],
  ])('%s', (action, text) => {
    expect(causePhrase(promoted, cause(action))).toBe(text);
  });

  it('null cause is automatic', () => {
    expect(causePhrase(entry({ action: 'promoted' }), new Map())).toBe(
      'automatic',
    );
  });

  it('cause not loaded is automatic', () => {
    expect(causePhrase(promoted, new Map())).toBe('automatic');
  });

  it('is null for rows that are not promotions', () => {
    expect(causePhrase(entry({ action: 'withdrew' }), new Map())).toBeNull();
  });
});

describe('meansLabel', () => {
  const actor = (role: string) => ({ ...entry().actor, role });

  it('staff role wins', () => {
    expect(meansLabel(entry({ actor: actor('staff'), means: 'web' }))).toBe(
      'Staff',
    );
  });
  it.each([
    ['web', 'Web'],
    ['discord_button', 'Discord button'],
    ['discord_reaction', 'Discord reaction'],
    ['system', 'System'],
  ])('%s', (means, label) => {
    expect(meansLabel(entry({ means }))).toBe(label);
  });
  it('system role', () => {
    expect(meansLabel(entry({ actor: actor('system'), means: 'web' }))).toBe(
      'System',
    );
  });
  it('unknown means is title-cased', () => {
    expect(meansLabel(entry({ means: 'carrier_pigeon' }))).toBe(
      'Carrier pigeon',
    );
  });
});

describe('action labels', () => {
  it('cover all 22 ledger actions', () => {
    expect(SIGNUP_LEDGER_ACTIONS).toHaveLength(22);
    expect(Object.keys(SIGNUP_ACTION_LABELS).sort()).toEqual(
      [...SIGNUP_LEDGER_ACTIONS].sort(),
    );
    for (const a of SIGNUP_LEDGER_ACTIONS) {
      expect(SIGNUP_ACTION_LABELS[a]).toBeTruthy();
      expect(actionTone(a)).toMatch(/^bg-(success|warning|error|info)\/20 /);
    }
  });

  it('uses the agreed wording', () => {
    expect(SIGNUP_ACTION_LABELS.resigned_up).toBe('Signed up again');
    expect(SIGNUP_ACTION_LABELS.staff_added).toBe('Added by staff');
    expect(SIGNUP_ACTION_LABELS.promoted).toBe('Promoted from waitlist');
    expect(SIGNUP_ACTION_LABELS.backfilled).toBe('Starting record');
    expect(SIGNUP_ACTION_LABELS.withdrew).toBe('Withdrew');
  });

  it('falls back for unknown actions', () => {
    expect(actionLabel('time_travelled')).toBe('Time travelled');
    expect(actionTone('time_travelled')).toMatch(/^bg-info\/20 /);
  });

  it('tones follow the spec groups', () => {
    expect(actionTone('promoted')).toMatch(/success/);
    expect(actionTone('demoted')).toMatch(/warning/);
    expect(actionTone('withdrew')).toMatch(/error/);
    expect(actionTone('swapped')).toMatch(/info/);
  });
});

describe('extraNotes', () => {
  it('reads from_user_id from before only', () => {
    expect(
      extraNotes(
        entry({
          action: 'account_merged',
          before: snap({ extra: { from_user_id: 4 } }),
          after: snap(),
        }),
      ),
    ).toEqual(['Merged from another account']);
  });

  it('moved_event', () => {
    expect(
      extraNotes(
        entry({
          action: 'moved_event',
          before: snap({ extra: { event_id: 1 } }),
          after: snap({ extra: { event_id: 2 } }),
        }),
      ),
    ).toEqual(['Moved between events']);
  });

  it('mmr_override', () => {
    expect(
      extraNotes(
        entry({ after: snap({ extra: { mmr_override: 4200, game_type: 1 } }) }),
      ),
    ).toEqual(['MMR set to 4200']);
  });

  it('staff_power', () => {
    expect(
      extraNotes(entry({ after: snap({ extra: { staff_power: true } }) })),
    ).toEqual(['Staff override on own sign-up']);
  });

  it('does not repeat the duplicate note and tolerates null sides', () => {
    expect(
      extraNotes(
        entry({
          before: snap({ extra: { discarded_duplicate: true } }),
          after: null,
        }),
      ),
    ).toEqual([]);
    expect(extraNotes(entry({ before: null, after: null }))).toEqual([]);
  });
});

describe('formatHistoryTime', () => {
  const iso = '2026-11-20T18:03:00Z';

  it('formats in the event timezone', () => {
    const t = formatHistoryTime(iso, 'America/Chicago');
    expect(t.short).toMatch(/Nov 20/);
    expect(t.short).toMatch(/12:03/);
    expect(t.full).toMatch(/2026/);
    expect(t.full).toMatch(/CST|GMT-6|Central/);
  });

  it('falls back to the browser zone', () => {
    const expected = new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(iso));
    expect(formatHistoryTime(iso).short).toBe(expected);
    expect(formatHistoryTime(iso, 'Not/AZone').short).toBe(expected);
  });

  it('returns the raw value for an invalid date', () => {
    expect(formatHistoryTime('nope')).toEqual({ short: 'nope', full: 'nope' });
  });
});
