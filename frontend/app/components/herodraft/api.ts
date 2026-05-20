import api from '~/components/api/axios';
import { getLogger } from '~/lib/logger';
import { getServerNowISO } from '~/store/heroDraftStore';
import type { HeroDraft } from './types';

const log = getLogger('herodraft:api');

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
  // `client_picked_at` is in SERVER-clock reference (via offset learned
  // from tick.server_time), not raw browser time. This way a client
  // with a skewed local clock still sends a timestamp the server can
  // trust. Server's 2s sanity window absorbs the residual one-way
  // network latency.
  const clientPickedAt = getServerNowISO();
  const startedAtMs = performance.now();
  log.info('pick_submit_started', {
    draft_id: draftId,
    hero_id: heroId,
    client_picked_at: clientPickedAt,
  });
  try {
    const response = await api.post(`/herodraft/${draftId}/submit-pick/`, {
      hero_id: heroId,
      client_picked_at: clientPickedAt,
    });
    log.info('pick_submit_succeeded', {
      draft_id: draftId,
      hero_id: heroId,
      duration_ms: Math.round(performance.now() - startedAtMs),
    });
    return response.data;
  } catch (err) {
    log.error('pick_submit_failed', {
      draft_id: draftId,
      hero_id: heroId,
      duration_ms: Math.round(performance.now() - startedAtMs),
      error: err instanceof Error ? err.message : String(err),
    });
    throw err;
  }
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

export async function resetDraft(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/reset/`);
  return response.data;
}

export async function pauseDraft(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/pause/`);
  return response.data;
}

export async function resumeDraft(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/resume/`);
  return response.data;
}
