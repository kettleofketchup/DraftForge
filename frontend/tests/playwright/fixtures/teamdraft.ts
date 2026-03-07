import type { BrowserContext } from '@playwright/test';

const API_URL = 'https://localhost/api';

/**
 * Kill all WebSocket connections for a team draft.
 *
 * Sends a force.disconnect message to the draft's channel group,
 * causing all connected DraftConsumer instances to close with code 1012.
 *
 * @param context - Playwright BrowserContext for making API requests
 * @param draftId - The Draft primary key
 * @returns true if the kill was successful
 */
export async function killDraftWebSocket(
  context: BrowserContext,
  draftId: number
): Promise<boolean> {
  const response = await context.request.post(
    `${API_URL}/tests/kill-draft-ws/${draftId}/`,
    { ignoreHTTPSErrors: true, failOnStatusCode: false }
  );
  return response.ok();
}

/**
 * Reset a tournament to its initial populate state.
 *
 * @param context - Playwright BrowserContext for making API requests
 * @param key - Tournament test key (e.g., 'draft_captain_turn')
 * @returns Tournament data after reset, or null if reset failed
 */
export async function resetTeamDraft(
  context: BrowserContext,
  key: string
): Promise<unknown | null> {
  const response = await context.request.post(
    `${API_URL}/tests/reset-tournament/${key}/`,
    { failOnStatusCode: false }
  );

  if (!response.ok()) {
    return null;
  }

  return response.json();
}
