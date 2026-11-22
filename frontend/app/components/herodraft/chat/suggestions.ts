import type { ChatMessage } from '../types';

export type Suggester = ChatMessage['sender'];

export interface HeroSuggestions {
  pick: Suggester[];
  ban: Suggester[];
}

export type SuggestionMap = ReadonlyMap<number, HeroSuggestions>;

export const NO_SUGGESTIONS: HeroSuggestions = { pick: [], ban: [] };

type Slot = 'pick' | 'ban';

function slotOf(kind: ChatMessage['kind']): [Slot, boolean] | null {
  switch (kind) {
    case 'suggest_pick':
      return ['pick', true];
    case 'suggest_ban':
      return ['ban', true];
    case 'unsuggest_pick':
      return ['pick', false];
    case 'unsuggest_ban':
      return ['ban', false];
    default:
      return null;
  }
}

/** Replays team chat into each hero's current suggesters, oldest first. */
export function activeSuggestions(
  messages: readonly ChatMessage[],
): Map<number, HeroSuggestions> {
  const live = new Map<number, Record<Slot, Map<number, Suggester>>>();
  for (const m of messages) {
    if (m.channel !== 'team' || m.hero_id === null) continue;
    const slot = slotOf(m.kind);
    if (!slot) continue;
    const [kind, added] = slot;
    let hero = live.get(m.hero_id);
    if (!hero) {
      hero = { pick: new Map(), ban: new Map() };
      live.set(m.hero_id, hero);
    }
    hero[kind].delete(m.sender.pk);
    if (added) hero[kind].set(m.sender.pk, m.sender);
  }
  const out = new Map<number, HeroSuggestions>();
  for (const [heroId, { pick, ban }] of live) {
    if (pick.size === 0 && ban.size === 0) continue;
    out.set(heroId, { pick: [...pick.values()], ban: [...ban.values()] });
  }
  return out;
}

export function isSuggestion(kind: ChatMessage['kind']): boolean {
  return kind === 'suggest_pick' || kind === 'suggest_ban';
}

export function isWithdrawal(kind: ChatMessage['kind']): boolean {
  return kind === 'unsuggest_pick' || kind === 'unsuggest_ban';
}
