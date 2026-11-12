/**
 * dota_lobby E2E fixtures: the seeded lobby data and the simulated dota_lobby.
 *
 * Infrastructure (backend/tests/populate/dota_lobby.py, tests.data.dota_lobby):
 * - Lobby Test Org / Lobby Test League (steam league 17940, which the
 *   simulator's bots administer)
 * - Lobby Test Series: fixed password mode, one upcoming event and its
 *   tournament (Alpha vs Beta, Gamma vs Delta, then a final)
 * - Lobby Random Event: random password mode, one game
 * - Lobby Lifecycle Tournament: standalone, in progress, one game
 *
 * The simulator is the test stack's `dota-lobby` service
 * (`just test::dota-lobby up`). Specs reach its control API through the
 * backend (/api/tests/dota-lobby-sim/...), never directly, and skip when it
 * is not running (hasSimulator).
 *
 * Never hardcode PKs: read them from getDotaLobbyTestData / resetDotaLobbyData.
 */

import { expect, type APIResponse, type BrowserContext, type Locator, type Page } from '@playwright/test';

import { visitAndWaitForHydration } from '../helpers/utils';
import { API_URL } from './base-url';

export type DotaLobbyRole = 'staff' | 'rostered' | 'registered' | 'unregistered' | 'league-staff';

export interface LobbyGame {
  pk: number;
  round: number;
  position: number;
  bracket_type: string;
  radiant_team: string | null;
  dire_team: string | null;
  status: string;
}

export interface LobbyPlayer {
  pk: number;
  username: string;
  account_id: number;
}

export interface LobbyTournament {
  pk: number;
  name: string;
  games: LobbyGame[];
  /** Team name -> its players (captain first). */
  teams: Record<string, LobbyPlayer[]>;
}

export interface DotaLobbyTestData {
  org: { pk: number; name: string };
  league: { pk: number; name: string; steam_league_id: number };
  fixed_password: string;
  series: { pk: number; name: string };
  series_event: { pk: number; name: string; tournament: LobbyTournament };
  random_event: { pk: number; name: string; tournament: LobbyTournament };
  lifecycle_tournament: LobbyTournament;
  users: Record<DotaLobbyRole, { pk: number; username: string }>;
}

/** The game's latest lobby row (GET /api/tests/dota-lobby/games/<pk>/lobby/). */
export interface LobbyRow {
  id: number;
  lobby_id: string | null;
  gc_lobby_id: string | null;
  state: string;
  state_reason: string | null;
  ended: boolean;
  password: string;
  match_id: string | null;
  provisional_winner_side: 'radiant' | 'dire' | null;
  last_error_code: string | null;
}

/** A simulated game coordinator lobby (GET /v1/sim/lobbies/{id}). */
export interface SimLobby {
  gc_lobby_id: string;
  bot: string;
  state: string;
  name: string;
  password: string;
  league_id: number;
  match_id: string | null;
  members: { account_id: number; team: string; slot: number | null; host: boolean }[];
  pending_invites: number[];
  chat: { account_id: number; text: string; delivered: boolean }[];
}

const SIM = `${API_URL}/tests/dota-lobby-sim`;

async function json<T>(resp: APIResponse, what: string): Promise<T> {
  if (!resp.ok()) {
    throw new Error(`${what} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`);
  }
  return (await resp.json()) as T;
}

export async function getDotaLobbyTestData(context: BrowserContext): Promise<DotaLobbyTestData> {
  return json(await context.request.get(`${API_URL}/tests/dota-lobby/data/`), 'dota-lobby data');
}

/**
 * Close the lobbies earlier specs left open, end their rows, set the games
 * back to pending and restore the passwords. Returns the fresh lookup.
 */
export async function resetDotaLobbyData(context: BrowserContext): Promise<DotaLobbyTestData> {
  return json(await context.request.post(`${API_URL}/tests/dota-lobby/reset/`), 'dota-lobby reset');
}

/** Log in as a dota_lobby test user (the context's cookies hold the session). */
export async function loginDotaLobby(context: BrowserContext, role: DotaLobbyRole): Promise<void> {
  await json(
    await context.request.post(`${API_URL}/tests/login-dota-lobby/${role}/`),
    `login-dota-lobby ${role}`,
  );
}

export interface SimulatorStatus {
  available: boolean;
  /** The simulator answered (it may still be starting); false when nothing did. */
  reachable: boolean;
  ready?: boolean;
  simulation?: boolean;
  code?: string;
}

export async function simulatorStatus(context: BrowserContext): Promise<SimulatorStatus> {
  const resp = await context.request.get(`${API_URL}/tests/dota-lobby/simulator/`);
  if (resp.ok()) {
    return { ...((await resp.json()) as Omit<SimulatorStatus, 'reachable'>), reachable: true };
  }
  // 503: DOTA_LOBBY_URL is not set, or nothing answers there.
  const body = (await resp.json().catch(() => ({}))) as { code?: string };
  return { available: false, reachable: false, code: body.code ?? String(resp.status()) };
}

export const SIMULATOR_SKIP_REASON =
  'The simulated dota_lobby is not running: start it with `just test::dota-lobby up`';

/**
 * How long hasSimulator waits for a simulator that is still starting: the
 * container answers before its bots are ready and have verified the test
 * league. With DOTA_LOBBY_SIMULATOR_REQUIRED=1 it also waits for one that
 * does not answer yet (`up -d` returns before the service listens).
 */
const SIMULATOR_WAIT_MS = 60_000;

let simulatorSeen = false;

/**
 * Whether the simulator can take lobbies. Waits, up to SIMULATOR_WAIT_MS,
 * for one that answers but is not available yet, and skips at once when
 * nothing answers (the CI stack, which does not start it).
 *
 * DOTA_LOBBY_SIMULATOR_REQUIRED=1 (just test::pw::dota-lobby sets it when
 * this slot's simulator is running) makes a simulator that never becomes
 * available an error, never a skip, so a misconfigured one (a league ID
 * mismatch, a bad secret) cannot pass as a green run.
 */
export async function hasSimulator(context: BrowserContext): Promise<boolean> {
  if (simulatorSeen) return true;
  const required = process.env.DOTA_LOBBY_SIMULATOR_REQUIRED === '1';
  const deadline = Date.now() + SIMULATOR_WAIT_MS;
  let status = await simulatorStatus(context);
  while (!status.available && (status.reachable || required) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    status = await simulatorStatus(context);
  }
  if (!status.available && required) {
    throw new Error(`${SIMULATOR_SKIP_REASON} (status: ${JSON.stringify(status)})`);
  }
  simulatorSeen = status.available;
  return status.available;
}

/** Request helpers for the simulator's control API (/v1/sim/<path>). */
export const sim = {
  get: (context: BrowserContext, path: string) => context.request.get(`${SIM}/${path}`),
  post: (context: BrowserContext, path: string, data?: Record<string, unknown>) =>
    context.request.post(`${SIM}/${path}`, { data: data ?? {} }),
  patch: (context: BrowserContext, path: string, data: Record<string, unknown>) =>
    context.request.patch(`${SIM}/${path}`, { data }),
  delete: (context: BrowserContext, path: string) => context.request.delete(`${SIM}/${path}`),
};

export async function getSimLobby(context: BrowserContext, lobbyId: string): Promise<SimLobby> {
  return json(await sim.get(context, `lobbies/${lobbyId}`), `sim lobby ${lobbyId}`);
}

export async function getLobbyRow(context: BrowserContext, gamePk: number): Promise<LobbyRow | null> {
  const body = await json<{ lobby: LobbyRow | null }>(
    await context.request.get(`${API_URL}/tests/dota-lobby/games/${gamePk}/lobby/`),
    `lobby row for game ${gamePk}`,
  );
  return body.lobby;
}

/**
 * Give the game a `waiting` lobby row without dota_lobby
 * (POST /api/tests/dota-lobby/games/<pk>/lobby/seed/), for specs that check
 * what DraftForge shows of a lobby where the simulator does not run. Never
 * with the simulator running: its reconcile would end the row.
 */
export async function seedLobbyRow(context: BrowserContext, gamePk: number): Promise<LobbyRow> {
  const body = await json<{ lobby: LobbyRow }>(
    await context.request.post(`${API_URL}/tests/dota-lobby/games/${gamePk}/lobby/seed/`),
    `seed lobby for game ${gamePk}`,
  );
  return body.lobby;
}

/**
 * Wait until the game's latest lobby row matches `ready` (by default: a new
 * row, other than `previousId`, that dota_lobby accepted and created in the
 * simulated game coordinator).
 */
export async function waitForLobbyRow(
  context: BrowserContext,
  gamePk: number,
  ready: (row: LobbyRow) => boolean = (row) => !!row.lobby_id && !!row.gc_lobby_id,
  { previousId, timeout = 30_000 }: { previousId?: number; timeout?: number } = {},
): Promise<LobbyRow> {
  let latest: LobbyRow | null = null;
  await expect
    .poll(
      async () => {
        latest = await getLobbyRow(context, gamePk);
        return !!latest && latest.id !== previousId && ready(latest);
      },
      { timeout, intervals: [250, 500, 1000] },
    )
    .toBe(true);
  return latest!;
}

/** Staff request a lobby for the game through the organizer API. */
export async function requestLobby(
  context: BrowserContext,
  gamePk: number,
  body: Record<string, unknown> = {},
): Promise<void> {
  const cookies = await context.cookies();
  const csrf = cookies.find((c) => c.name === 'csrftoken')?.value ?? '';
  const resp = await context.request.post(`${API_URL}/games/${gamePk}/lobby/`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
  });
  expect(resp.status(), await resp.text()).toBe(202);
}

/** The bracket page of a tournament, loaded. */
export async function openBracket(page: Page, tournamentPk: number): Promise<void> {
  await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);
  await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({ timeout: 20_000 });
}

export function bracketNode(page: Page, gamePk: number): Locator {
  return page.locator(`[data-testid="bracket-match-node"][data-game-pk="${gamePk}"]`);
}

/** Open the Match Details dialog of a game from the bracket. */
export async function openMatchModal(page: Page, gamePk: number): Promise<Locator> {
  const node = bracketNode(page, gamePk);
  await expect(node).toBeVisible({ timeout: 15_000 });
  await node.click({ force: true });
  const dialog = page.locator('[data-testid="matchStatsModal"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  return dialog;
}

export async function closeMatchModal(page: Page): Promise<void> {
  const dialog = page.locator('[data-testid="matchStatsModal"]');
  await dialog.locator('[data-testid="dialog-close-button"]').click();
  await expect(dialog).toBeHidden({ timeout: 5_000 });
}

/** The lobby state badge in the dialog reaches one of `states`. */
export async function expectLobbyState(
  dialog: Locator,
  states: string | string[],
  timeout = 30_000,
): Promise<void> {
  const wanted = Array.isArray(states) ? states : [states];
  const badge = dialog.locator('[data-testid="lobby-state-badge"]');
  await expect
    .poll(async () => (await badge.count()) && (await badge.getAttribute('data-lobby-state')), {
      timeout,
      intervals: [250, 500, 1000],
    })
    .toEqual(expect.stringMatching(new RegExp(`^(${wanted.join('|')})$`)));
}
