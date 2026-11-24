// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {
  AxiosError,
  AxiosHeaders,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

import { getBotAccess, refreshBotAccess } from '../api';
import { BotAccessPanel } from '../BotAccessPanel';
import type { BotAccessSnapshot } from '../schemas';
import { makeRow, makeSnapshot } from './fixtures';

const { toastSuccess, toastError, logError, logWarn } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  logError: vi.fn(),
  logWarn: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: toastSuccess, error: toastError },
}));

vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    error: logError,
    warn: logWarn,
    info: vi.fn(),
    debug: vi.fn(),
  }),
}));

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  getBotAccess: vi.fn(),
  refreshBotAccess: vi.fn(),
}));

function axiosError(
  status: number,
  data: unknown = {},
  headers: Record<string, string> = {},
): AxiosError {
  const config = {
    headers: new AxiosHeaders(),
  } as InternalAxiosRequestConfig;
  const response = {
    status,
    statusText: '',
    data,
    headers: new AxiosHeaders(headers),
    config,
  } as AxiosResponse;
  return new AxiosError(
    `HTTP ${status}`,
    'ERR_BAD_RESPONSE',
    config,
    undefined,
    response,
  );
}

function renderPanel(enabled = true) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <BotAccessPanel leagueId={7} enabled={enabled} />
    </QueryClientProvider>,
  );
}

function serviceSnapshot(
  status: BotAccessSnapshot['service']['status'],
): BotAccessSnapshot {
  return makeSnapshot({
    service: { status, code: null, retryable: false },
    bots: [],
    held_count: 0,
  });
}

beforeEach(() => {
  vi.mocked(getBotAccess).mockReset();
  vi.mocked(refreshBotAccess).mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
  logError.mockReset();
  logWarn.mockReset();
});

afterEach(() => cleanup());

describe('BotAccessPanel service states', () => {
  it('renders summary, help, admins link, table and refresh when ok', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    renderPanel();

    expect(
      (await screen.findByTestId('bot-access-summary')).textContent,
    ).toContain('1 of 2 bots can host lobbies in Steam league 12345.');
    expect(screen.getByTestId('bot-access-table')).toBeTruthy();
    expect(screen.getByTestId('bot-access-row-1')).toBeTruthy();
    expect(screen.getByTestId('bot-access-row-2')).toBeTruthy();
    expect(screen.getByText('Steam profile')).toBeTruthy();
    expect(screen.getByText(/League Administrators section/)).toBeTruthy();
    const admins = screen.getByTestId('bot-access-admins-link');
    expect(admins.getAttribute('href')).toBe(
      'https://www.dota2.com/league/12345/admins',
    );
    expect(admins.getAttribute('target')).toBe('_blank');
    expect(admins.getAttribute('rel')).toBe('noopener noreferrer');
    expect(admins.textContent).toContain('Open league admins page');
    expect(screen.getByTestId('bot-access-refresh').textContent).toContain(
      'Refresh access',
    );
    expect(screen.getByTestId('bot-access-panel').textContent).not.toMatch(
      /invite/i,
    );
  });

  it('renders the not-linked message with no table or refresh', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      serviceSnapshot('league_not_linked'),
    );
    renderPanel();
    expect(
      (await screen.findByTestId('bot-access-service-message')).textContent,
    ).toBe(
      'This league has no Steam league ID. Add one in Edit League to check bot access.',
    );
    expect(screen.queryByTestId('bot-access-table')).toBeNull();
    expect(screen.queryByTestId('bot-access-refresh')).toBeNull();
  });

  it.each(['unavailable', 'error'] as const)(
    'renders the unreachable message with refresh for %s',
    async (status) => {
      vi.mocked(getBotAccess).mockResolvedValue(serviceSnapshot(status));
      renderPanel();
      expect(
        (await screen.findByTestId('bot-access-service-message')).textContent,
      ).toBe(
        "The lobby service couldn't be reached, so bot access is unknown. Try again shortly.",
      );
      expect(screen.queryByTestId('bot-access-table')).toBeNull();
      expect(screen.getByTestId('bot-access-refresh')).toBeTruthy();
      expect(screen.queryByText(/missing/i)).toBeNull();
    },
  );

  it.each(['disabled', 'not_configured'] as const)(
    'renders the not-enabled message for %s',
    async (status) => {
      vi.mocked(getBotAccess).mockResolvedValue(serviceSnapshot(status));
      renderPanel();
      expect(
        (await screen.findByTestId('bot-access-service-message')).textContent,
      ).toBe("Hosted lobbies aren't enabled on this site.");
      expect(screen.queryByTestId('bot-access-table')).toBeNull();
      expect(screen.queryByTestId('bot-access-refresh')).toBeNull();
    },
  );

  it('renders the unsupported message', async () => {
    vi.mocked(getBotAccess).mockResolvedValue({
      ...serviceSnapshot('unsupported'),
      provider: 'unsupported',
      supported: false,
      external_league_id: null,
      league_link: null,
    });
    renderPanel();
    expect(
      (await screen.findByTestId('bot-access-service-message')).textContent,
    ).toBe("Lobby bot management isn't available for this game yet.");
    expect(screen.queryByTestId('bot-access-table')).toBeNull();
    expect(screen.queryByTestId('bot-access-refresh')).toBeNull();
  });

  it('makes no request when disabled', () => {
    renderPanel(false);
    expect(screen.getByTestId('bot-access-panel')).toBeTruthy();
    expect(getBotAccess).not.toHaveBeenCalled();
  });
});

describe('BotAccessPanel rows', () => {
  it('renders rows with withheld status', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        bots: [makeRow({ status: null, access: 'missing' })],
        held_count: 0,
      }),
    );
    renderPanel();
    const row = await screen.findByTestId('bot-access-row-1');
    expect(within(row).getByText('Bot 1')).toBeTruthy();
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0);
    expect(within(row).getByText(/Missing/)).toBeTruthy();
  });

  it('renders identity-null row', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        bots: [
          makeRow({ identity: null, status: 'offline', access: 'unknown' }),
        ],
      }),
    );
    renderPanel();
    const row = await screen.findByTestId('bot-access-row-1');
    expect(
      within(row).getByText('Not available until the bot logs on'),
    ).toBeTruthy();
    expect(screen.queryByTestId('bot-access-profile-link-1')).toBeNull();
    expect(screen.queryByTestId('bot-access-copy-1')).toBeNull();
  });

  it('renders status badges and access labels', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        bots: [
          makeRow({ position: 1, status: 'available', access: 'verified' }),
          makeRow({ position: 2, status: 'busy', access: 'unverified' }),
          makeRow({ position: 3, status: 'connecting', access: 'unknown' }),
        ],
      }),
    );
    renderPanel();
    const r1 = await screen.findByTestId('bot-access-row-1');
    expect(within(r1).getAllByText('Available').length).toBeGreaterThan(0);
    expect(within(r1).getByText(/Verified/)).toBeTruthy();
    const r2 = screen.getByTestId('bot-access-row-2');
    expect(within(r2).getAllByText('Busy').length).toBeGreaterThan(0);
    expect(within(r2).getByText(/Unverified/)).toBeTruthy();
    const r3 = screen.getByTestId('bot-access-row-3');
    expect(within(r3).getAllByText('Connecting').length).toBeGreaterThan(0);
    expect(within(r3).getByText(/Unknown/)).toBeTruthy();
  });

  it.each([
    [
      'not_rechecked',
      'not re-checked since the lobby service restarted',
    ] as const,
    [
      'allowed_unverified',
      "lobbies are still routed to it, but Valve doesn't list it as an admin",
    ] as const,
  ])('renders access note %s', async (note, text) => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        bots: [makeRow({ access: 'unverified', access_note: note })],
      }),
    );
    renderPanel();
    const row = await screen.findByTestId('bot-access-row-1');
    expect(row.textContent).toContain(text);
  });

  it('renders the profile link and copies it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    renderPanel();
    const link = await screen.findByTestId('bot-access-profile-link-1');
    expect(link.getAttribute('href')).toBe(
      'https://steamcommunity.com/profiles/76561197960265729',
    );
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');

    fireEvent.click(screen.getByTestId('bot-access-copy-1'));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        'https://steamcommunity.com/profiles/76561197960265729',
      ),
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it('toasts and logs a clipboard failure', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    renderPanel();
    fireEvent.click(await screen.findByTestId('bot-access-copy-1'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(logWarn).toHaveBeenCalled();
  });

  it('does not render disallowed profile host', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        bots: [
          makeRow({
            identity: {
              kind: 'steam',
              value: '76561197960265729',
              profile_url: 'https://evil.example/p',
            },
          }),
        ],
      }),
    );
    renderPanel();
    const row = await screen.findByTestId('bot-access-row-1');
    expect(screen.queryByTestId('bot-access-profile-link-1')).toBeNull();
    expect(screen.queryByTestId('bot-access-copy-1')).toBeNull();
    expect(within(row).getByText('76561197960265729')).toBeTruthy();
    expect(row.querySelector('a')).toBeNull();
  });

  it('renders unknown identity kind as text', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        bots: [
          makeRow({
            identity: { kind: 'riot', value: 'player#EUW', profile_url: null },
          }),
        ],
      }),
    );
    renderPanel();
    const row = await screen.findByTestId('bot-access-row-1');
    expect(within(row).getByText('player#EUW')).toBeTruthy();
    expect(screen.queryByTestId('bot-access-profile-link-1')).toBeNull();
    expect(screen.queryByTestId('bot-access-copy-1')).toBeNull();
  });

  it('does not render disallowed link host', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({
        league_link: {
          kind: 'league_admin_portal',
          url: 'https://evil.example/league/12345/admins',
        },
      }),
    );
    renderPanel();
    await screen.findByTestId('bot-access-summary');
    expect(screen.queryByTestId('bot-access-admins-link')).toBeNull();
  });

  it('falls back to base copy', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(
      makeSnapshot({ provider: 'other', league_link: null }),
    );
    renderPanel();
    await screen.findByTestId('bot-access-table');
    expect(screen.getByText('Profile')).toBeTruthy();
    expect(screen.getByTestId('bot-access-summary')).toBeTruthy();
    expect(screen.getByTestId('bot-access-profile-link-1')).toBeTruthy();
    expect(screen.queryByText(/Steam/)).toBeNull();
    expect(screen.getByTestId('bot-access-panel').textContent).not.toMatch(
      /Steam|Valve|Dota/,
    );
  });

  it('falls back to base copy for not linked', async () => {
    vi.mocked(getBotAccess).mockResolvedValue({
      ...serviceSnapshot('league_not_linked'),
      provider: 'other',
    });
    renderPanel();
    const msg = await screen.findByTestId('bot-access-service-message');
    expect(msg.textContent).not.toMatch(/Steam/);
  });
});

describe('BotAccessPanel query errors', () => {
  it('shows no-access on 404', async () => {
    vi.mocked(getBotAccess).mockRejectedValue(axiosError(404));
    renderPanel();
    expect(
      (await screen.findByTestId('bot-access-query-error')).textContent,
    ).toBe("You don't have access to lobby bots for this league.");
    expect(screen.queryByTestId('bot-access-table')).toBeNull();
    expect(screen.queryByTestId('bot-access-refresh')).toBeNull();
    expect(screen.queryByTestId('bot-access-retry')).toBeNull();
    expect(logError).not.toHaveBeenCalled();
  });

  it('shows retry-after on GET 429', async () => {
    vi.mocked(getBotAccess).mockRejectedValue(
      axiosError(
        429,
        { error: 'Too many requests. Try again shortly.', code: 'throttled' },
        { 'Retry-After': '12' },
      ),
    );
    renderPanel();
    expect(
      (await screen.findByTestId('bot-access-query-error')).textContent,
    ).toContain('Try again in 12 s');
    expect(screen.getByTestId('bot-access-retry')).toBeTruthy();
    expect(screen.queryByTestId('bot-access-table')).toBeNull();
  });

  it('shows load error on GET 500 and retry refetches', async () => {
    vi.mocked(getBotAccess).mockRejectedValue(
      axiosError(500, { detail: 'Server exploded.' }),
    );
    renderPanel();
    const err = await screen.findByTestId('bot-access-query-error');
    expect(err.textContent).toContain("Couldn't load lobby bots.");
    expect(err.textContent).toContain('Server exploded.');
    expect(screen.queryByTestId('bot-access-table')).toBeNull();
    expect(logError).toHaveBeenCalledTimes(1);

    const callsBeforeRetry = vi.mocked(getBotAccess).mock.calls.length;
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    fireEvent.click(screen.getByTestId('bot-access-retry'));
    expect(await screen.findByTestId('bot-access-table')).toBeTruthy();
    expect(getBotAccess).toHaveBeenCalledTimes(callsBeforeRetry + 1);
  });

  it('shows load error on Zod-invalid body', async () => {
    vi.mocked(getBotAccess).mockRejectedValue(new ZodError([]));
    renderPanel();
    const err = await screen.findByTestId('bot-access-query-error');
    expect(err.textContent).toBe("Couldn't load lobby bots.");
    expect(screen.getByTestId('bot-access-retry')).toBeTruthy();
    expect(logError).toHaveBeenCalledTimes(1);
  });
});

describe('BotAccessPanel refresh', () => {
  it('disables refresh while pending', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    let resolve: (s: BotAccessSnapshot) => void = () => {};
    vi.mocked(refreshBotAccess).mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    renderPanel();
    const btn = await screen.findByTestId('bot-access-refresh');
    fireEvent.click(btn);
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(btn);
    expect(refreshBotAccess).toHaveBeenCalledTimes(1);
    await act(async () => resolve(makeSnapshot({ refresh_outcome: 'ok' })));
    await waitFor(() =>
      expect((btn as HTMLButtonElement).disabled).toBe(false),
    );
  });

  it('refresh updates rows and shows row refresh notes', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    vi.mocked(refreshBotAccess).mockResolvedValue(
      makeSnapshot({
        refresh_outcome: 'ok',
        held_count: 2,
        bots: [
          makeRow({ position: 1, refresh: 'not_ready' }),
          makeRow({
            position: 2,
            status: 'busy',
            access: 'verified',
            refresh: 'failed',
          }),
          makeRow({ position: 3, refresh: 'ok' }),
        ],
      }),
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId('bot-access-refresh'));
    expect(await screen.findByTestId('bot-access-row-3')).toBeTruthy();
    expect(screen.getByTestId('bot-access-summary').textContent).toContain(
      '2 of 3 bots',
    );
    expect(screen.getByTestId('bot-access-row-1').textContent).toContain(
      'bot not online, kept last result',
    );
    expect(screen.getByTestId('bot-access-row-2').textContent).toContain(
      'check failed, kept last result',
    );
    expect(screen.queryByTestId('bot-access-refresh-outcome')).toBeNull();
  });

  it.each([
    ['timed_out', 'The check is still running. Refresh again shortly.'],
    ['unavailable', "The lobby service couldn't be reached"],
    ['not_supported_upstream', "The lobby service can't re-check"],
  ] as const)('renders refresh outcome %s', async (outcome, text) => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    vi.mocked(refreshBotAccess).mockResolvedValue(
      makeSnapshot({ refresh_outcome: outcome }),
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId('bot-access-refresh'));
    expect(
      (await screen.findByTestId('bot-access-refresh-outcome')).textContent,
    ).toContain(text);
    expect(screen.getByTestId('bot-access-table')).toBeTruthy();
  });

  it('shows retry-after on 429', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    vi.mocked(refreshBotAccess).mockRejectedValue(
      axiosError(429, { code: 'throttled' }, { 'Retry-After': '9' }),
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId('bot-access-refresh'));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('Try again in 9 s'),
    );
    expect(screen.getByTestId('bot-access-row-1')).toBeTruthy();
    expect(screen.getByTestId('bot-access-row-2')).toBeTruthy();
  });

  it('toasts refresh 500 and keeps rows', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    vi.mocked(refreshBotAccess).mockRejectedValue(
      axiosError(500, { detail: 'Upstream broke.' }),
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId('bot-access-refresh'));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        "Couldn't re-check bot access. Upstream broke.",
      ),
    );
    expect(logError).toHaveBeenCalled();
    expect(screen.getByTestId('bot-access-table')).toBeTruthy();
    expect(screen.getByTestId('bot-access-row-2')).toBeTruthy();
  });

  it('toasts refresh 404 without detail and keeps rows', async () => {
    vi.mocked(getBotAccess).mockResolvedValue(makeSnapshot());
    vi.mocked(refreshBotAccess).mockRejectedValue(axiosError(404));
    renderPanel();
    fireEvent.click(await screen.findByTestId('bot-access-refresh'));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Couldn't re-check bot access."),
    );
    expect(screen.getByTestId('bot-access-row-1')).toBeTruthy();
  });
});
