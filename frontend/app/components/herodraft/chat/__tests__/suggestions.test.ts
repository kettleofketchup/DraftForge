import { describe, expect, it } from 'vitest';
import type { ChatMessage } from '../../types';
import { activeSuggestions } from '../suggestions';

const user = (pk: number) => ({
  pk,
  username: `u${pk}`,
  nickname: null,
  avatarUrl: null,
  discordId: null,
});

let seq = 0;
const m = (
  kind: ChatMessage['kind'],
  heroId: number | null,
  senderPk: number,
  channel: ChatMessage['channel'] = 'team',
): ChatMessage => ({
  id: `00000000-0000-4000-8000-${String(++seq).padStart(12, '0')}`,
  channel,
  team_id: channel === 'team' ? 12 : null,
  kind,
  hero_id: heroId,
  body: kind === 'text' ? 'hi' : '',
  created_at: '2026-11-22T00:00:00.000000Z',
  sender: user(senderPk),
});

const pks = (users: { pk: number }[] | undefined) => users?.map((u) => u.pk);

describe('activeSuggestions', () => {
  it('collects pick and ban suggesters per hero, deduped per user', () => {
    const map = activeSuggestions([
      m('suggest_pick', 74, 1),
      m('suggest_pick', 74, 2),
      m('suggest_pick', 74, 1),
      m('suggest_ban', 74, 3),
      m('suggest_ban', 5, 1),
      m('text', null, 1),
    ]);
    expect(pks(map.get(74)?.pick)).toEqual([2, 1]);
    expect(pks(map.get(74)?.ban)).toEqual([3]);
    expect(pks(map.get(5)?.ban)).toEqual([1]);
    expect(map.get(5)?.pick).toEqual([]);
  });

  it('drops a suggestion its sender withdrew, leaving others', () => {
    const map = activeSuggestions([
      m('suggest_pick', 74, 1),
      m('suggest_pick', 74, 2),
      m('suggest_ban', 74, 1),
      m('unsuggest_pick', 74, 1),
    ]);
    expect(pks(map.get(74)?.pick)).toEqual([2]);
    expect(pks(map.get(74)?.ban)).toEqual([1]);
  });

  it('forgets a hero once every suggestion is withdrawn', () => {
    const map = activeSuggestions([
      m('suggest_ban', 74, 1),
      m('unsuggest_ban', 74, 1),
    ]);
    expect(map.has(74)).toBe(false);
  });

  it('a later suggestion re-adds a withdrawn one', () => {
    const map = activeSuggestions([
      m('suggest_pick', 74, 1),
      m('unsuggest_pick', 74, 1),
      m('suggest_pick', 74, 1),
    ]);
    expect(pks(map.get(74)?.pick)).toEqual([1]);
  });

  it('ignores all-chat rows', () => {
    expect(activeSuggestions([m('suggest_pick', 74, 1, 'all')]).size).toBe(0);
  });
});
