import api from '~/components/api/axios';
import type { HeroDraft } from './types';

export interface CreateHeroDraftOptions {
  radiantTeamId?: number;
  direTeamId?: number;
}

export async function createHeroDraft(
  gameId: number,
  options?: CreateHeroDraftOptions
): Promise<HeroDraft> {
  const response = await api.post(`/games/${gameId}/create-herodraft/`, {
    radiant_team_id: options?.radiantTeamId,
    dire_team_id: options?.direTeamId,
  });
  return response.data;
}

export async function getHeroDraft(draftId: number): Promise<HeroDraft> {
  const response = await api.get(`/herodraft/${draftId}/`);
  return response.data;
}

export async function setReady(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/set-ready/`);
  return response.data;
}

export async function triggerRoll(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/trigger-roll/`);
  return response.data;
}

export async function submitChoice(
  draftId: number,
  choiceType: 'pick_order' | 'side',
  value: 'first' | 'second' | 'radiant' | 'dire'
): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/submit-choice/`, {
    choice_type: choiceType,
    value,
  });
  return response.data;
}

export async function submitPick(
  draftId: number,
  heroId: number
): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/submit-pick/`, {
    hero_id: heroId,
  });
  return response.data;
}

export interface HeroDraftEventResponse {
  id: number;
  event_type: string;
  draft_team: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function listEvents(draftId: number): Promise<HeroDraftEventResponse[]> {
  const response = await api.get(`/herodraft/${draftId}/list-events/`);
  return response.data;
}

export async function listAvailableHeroes(
  draftId: number
): Promise<{ available_heroes: number[] }> {
  const response = await api.get(`/herodraft/${draftId}/list-available-heroes/`);
  return response.data;
}

export async function abandonDraft(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/abandon/`);
  return response.data;
}
