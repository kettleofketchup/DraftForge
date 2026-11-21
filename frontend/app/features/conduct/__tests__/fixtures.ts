import type { ConductHistoryItem, MemberConduct } from '../schemas';

export const MEMBER = {
  org_user_pk: 7,
  user_pk: 11,
  username: 'alice',
  nickname: null,
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
};

export function historyItem(
  overrides: Partial<ConductHistoryItem> = {},
): ConductHistoryItem {
  return {
    event_id: 5,
    event_name: 'Inhouse night',
    event_starts_at: '2026-11-01T19:00:00Z',
    outcome: 'attended',
    source: 'ready_check',
    committed: true,
    finalized: true,
    voided: false,
    weight: 0.62,
    ...overrides,
  };
}

export function memberConduct(
  overrides: Partial<MemberConduct> = {},
): MemberConduct {
  return {
    member: MEMBER,
    show_rate: 0.91,
    status: 'scored',
    counted_events: 6,
    weighted_events: 4.37,
    totals: { attended: 5, no_show: 1, late_cancel: 0, excused: 1 },
    history: [historyItem()],
    ...overrides,
  };
}
