import type { Browser, BrowserContext, Page } from '@playwright/test';
import { API_URL } from './base-url';
import { loginAsUser } from './auth';
import { postWithCsrf } from './events';
import { TournamentPage } from '../helpers/tournament';


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

export interface TimerTournament {
  pk: number;
  name: string;
  draft: {
    pk: number;
    state: string;
    latest_round: number | null;
    draft_rounds: Array<{
      pk: number;
      pick_number: number;
      captain: number | null;
      choice: number | null;
      skip_count?: number;
      started_at?: string | null;
    }>;
    users_remaining: number[];
  };
  teams: Array<{ pk: number; name: string; captain: number; draft_order: number }>;
}

type TimerRound = TimerTournament['draft']['draft_rounds'][number];

export async function resetTimerTournament(
  context: BrowserContext,
  key: string
): Promise<TimerTournament> {
  const response = await postWithCsrf(
    context,
    `${API_URL}/tests/reset-tournament/${key}/`
  );
  if (!response.ok()) {
    throw new Error(`resetTimerTournament(${key}) failed: ${response.status()}`);
  }
  return response.json();
}

export async function fetchTimerTournament(
  context: BrowserContext,
  key: string
): Promise<TimerTournament> {
  const response = await context.request.get(
    `${API_URL}/tests/tournament-by-key/${key}/`,
    { failOnStatusCode: false }
  );
  if (!response.ok()) {
    throw new Error(`fetchTimerTournament(${key}) failed: ${response.status()}`);
  }
  return response.json();
}

export async function expireDraftClock(
  context: BrowserContext,
  draftPk: number,
  ms = 120_000
): Promise<void> {
  const response = await postWithCsrf(
    context,
    `${API_URL}/tests/draft/${draftPk}/expire-clock/`,
    { ms }
  );
  if (!response.ok()) {
    throw new Error(`expireDraftClock(${draftPk}) failed: ${response.status()}`);
  }
}

export async function staleDraftHeartbeat(
  context: BrowserContext,
  draftPk: number,
  userPk: number,
  mode: 'delete' | 'backdate' = 'delete'
): Promise<void> {
  const response = await postWithCsrf(
    context,
    `${API_URL}/tests/draft/${draftPk}/stale-heartbeat/`,
    { user_pk: userPk, mode }
  );
  if (!response.ok()) {
    throw new Error(`staleDraftHeartbeat(${draftPk}) failed: ${response.status()}`);
  }
}

async function postDraftAction(
  context: BrowserContext,
  path: string,
  data?: Record<string, unknown>
): Promise<void> {
  const response = await postWithCsrf(context, `${API_URL}${path}`, data);
  if (!response.ok()) {
    throw new Error(`POST ${path} failed: ${response.status()} ${await response.text()}`);
  }
}

export async function readyUp(
  context: BrowserContext,
  draftPk: number,
  ready = true
): Promise<void> {
  await postDraftAction(context, `/draft/${draftPk}/ready/`, { ready });
}

export async function startDraftAsStaff(
  adminContext: BrowserContext,
  draftPk: number
): Promise<void> {
  await postDraftAction(adminContext, `/draft/${draftPk}/start/`);
}

export async function resumeDraftAsStaff(
  adminContext: BrowserContext,
  draftPk: number
): Promise<void> {
  await postDraftAction(adminContext, `/draft/${draftPk}/resume/`);
}

export async function staffPick(
  adminContext: BrowserContext,
  draftRoundPk: number,
  userPk: number
): Promise<void> {
  await postDraftAction(adminContext, '/tournaments/pick_player', {
    draft_round_pk: draftRoundPk,
    user_pk: userPk,
  });
}

export function captainsOf(t: TimerTournament): number[] {
  return [...t.teams]
    .sort((a, b) => a.draft_order - b.draft_order)
    .map((team) => team.captain);
}

export function activeRound(t: TimerTournament): TimerRound {
  const open = t.draft.draft_rounds
    .filter((r) => r.choice === null)
    .sort((a, b) => a.pick_number - b.pick_number);
  if (open.length === 0) {
    throw new Error(`activeRound: tournament ${t.pk} has no open round`);
  }
  return open[0];
}

export async function openDraftModal(page: Page, tournamentPk: number): Promise<void> {
  const tournamentPage = new TournamentPage(page);
  await tournamentPage.goto(tournamentPk, 'teams');
  await page
    .locator(
      '[data-testid="startTeamDraftButton"], [data-testid="liveTeamDraftButton"], [data-testid="viewTeamDraftButton"], [data-testid="viewCompletedTeamDraftButton"]'
    )
    .first()
    .click();
  await tournamentPage.waitForDraftModal();
}

export async function openCaptainPage(
  browser: Browser,
  captainPk: number,
  tournamentPk: number
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await loginAsUser(context, captainPk);
  const page = await context.newPage();
  await openDraftModal(page, tournamentPk);
  return { context, page };
}

export async function suppressDraftHeartbeats(page: Page): Promise<{ resume(): void }> {
  let suppressed = true;
  await page.routeWebSocket('**/api/draft/**', (ws) => {
    const server = ws.connectToServer();
    ws.onMessage((message) => {
      if (suppressed) {
        try {
          if (JSON.parse(String(message)).type === 'heartbeat') return;
        } catch {
          // non-JSON frames pass through
        }
      }
      server.send(message);
    });
  });
  return {
    resume(): void {
      suppressed = false;
    },
  };
}

export async function draftStateOf(context: BrowserContext, key: string): Promise<string> {
  return (await fetchTimerTournament(context, key)).draft.state;
}
